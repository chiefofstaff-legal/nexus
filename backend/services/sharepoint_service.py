"""
SharePoint Integration Service
================================

Connects to SharePoint Online via Microsoft Graph API with OAuth2
client-credentials flow (app-only auth). Stub mode (``SHAREPOINT_ENABLED=false``)
returns deterministic mock data so the demo works offline.

Live mode requires an Entra ID (Azure AD) app registration with:
  - Application (not delegated) permissions: Sites.Read.All, Files.ReadWrite.All
  - A client secret issued under the registered app

Auth flow: client_credentials -> access token (cached with 60-second buffer).
Graph tokens expire in 60 min; the buffer prevents in-flight expiry.

Token cache is module-level and process-scoped. In production this should
move to Redis or a shared store when multiple uvicorn workers run.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field


def sharepoint_enabled() -> bool:
    """Read the SHAREPOINT_ENABLED env var. Default: off (stub mode)."""
    return os.getenv("SHAREPOINT_ENABLED", "false").lower() in ("true", "1", "yes")


class SharePointConfig(BaseModel):
    """Connection details for a SharePoint Online tenant."""

    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    site_url: str = ""
    library_name: str = "Documents"


class SharePointDocument(BaseModel):
    """A single document entry in a SharePoint library."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    document_type: str = "other"
    modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    size_bytes: int = 0
    author: str = ""
    web_url: str = ""


# Stub library — realistic legal document set Swiss firms would have.
_MOCK_LIBRARY: list[SharePointDocument] = [
    SharePointDocument(
        title="Müller Family Office — Trust Deed 2024.pdf",
        document_type="contract",
        size_bytes=284_000,
        author="C. Zimmermann",
        web_url="https://contoso.sharepoint.com/sites/Legal/Documents/muller-trust-deed.pdf",
    ),
    SharePointDocument(
        title="ACME AG v. Credit Suisse — Reply Brief.docx",
        document_type="brief",
        size_bytes=142_000,
        author="V. Scheepers",
        web_url="https://contoso.sharepoint.com/sites/Legal/Documents/acme-reply.docx",
    ),
    SharePointDocument(
        title="NDA — Project Helvetia (counterparty draft).pdf",
        document_type="nda",
        size_bytes=68_000,
        author="M. Toop",
        web_url="https://contoso.sharepoint.com/sites/Legal/Documents/helvetia-nda.pdf",
    ),
    SharePointDocument(
        title="Invoice 2026-04-Miller.pdf",
        document_type="invoice",
        size_bytes=24_000,
        author="Billing",
        web_url="https://contoso.sharepoint.com/sites/Legal/Documents/inv-0442.pdf",
    ),
    SharePointDocument(
        title="Correspondence — Zurich Cantonal Bank 2026-04-12.pdf",
        document_type="correspondence",
        size_bytes=86_000,
        author="A. Theart",
        web_url="https://contoso.sharepoint.com/sites/Legal/Documents/zkb-letter.pdf",
    ),
]

# Name-keyword -> document_type for live library items.
_NAME_KEYWORDS: dict[str, str] = {
    "nda": "nda",
    "non-disclosure": "nda",
    "brief": "brief",
    "invoice": "invoice",
    "billing": "invoice",
    "correspondence": "correspondence",
    "letter": "correspondence",
    "motion": "motion",
    "statute": "statute",
    "contract": "contract",
    "agreement": "contract",
    "deed": "contract",
}


def _infer_type(name: str, _ext: str) -> str:
    """Infer document_type from the filename using keyword lookup."""
    lower = name.lower()
    for keyword, dtype in _NAME_KEYWORDS.items():
        if keyword in lower:
            return dtype
    return "other"


# --- Token cache ------------------------------------------------------------

@dataclass
class _TokenEntry:
    access_token: str
    expires_at: float  # Unix timestamp


_token_cache: dict[str, _TokenEntry] = {}
_TOKEN_BUFFER_SECS = 60


def _cache_key(config: SharePointConfig) -> str:
    return f"{config.tenant_id}:{config.client_id}"


# --- Connector --------------------------------------------------------------

class SharePointConnector:
    """Facade for SharePoint operations.

    Stub mode returns deterministic mock data (offline-safe demo).
    Live mode authenticates via Microsoft Graph client-credentials and
    reads from real SharePoint Online document libraries.
    """

    def __init__(self, stub_mode: Optional[bool] = None):
        self.stub_mode = not sharepoint_enabled() if stub_mode is None else stub_mode
        self._synced_ids: set[str] = set()

    # --- Auth helpers -------------------------------------------------------

    async def _get_token(self, config: SharePointConfig) -> str:
        """Obtain a Graph API bearer token, reusing the cache when valid."""
        import httpx

        key = _cache_key(config)
        entry = _token_cache.get(key)
        if entry and time.time() < entry.expires_at - _TOKEN_BUFFER_SECS:
            return entry.access_token

        url = (
            f"https://login.microsoftonline.com/{config.tenant_id}"
            "/oauth2/v2.0/token"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data={
                "grant_type": "client_credentials",
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            })
        resp.raise_for_status()
        body = resp.json()
        token = body["access_token"]
        expires_in = int(body.get("expires_in", 3600))
        _token_cache[key] = _TokenEntry(token, time.time() + expires_in)
        return token

    async def _graph_get(self, config: SharePointConfig, path: str) -> dict:
        """GET a Graph v1.0 endpoint and return parsed JSON."""
        import httpx

        token = await self._get_token(config)
        url = f"https://graph.microsoft.com/v1.0/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {token}"}
            )
        resp.raise_for_status()
        return resp.json()

    async def _resolve_site_id(self, config: SharePointConfig) -> str:
        """Resolve a Graph site ID from the human-readable SharePoint site URL."""
        parsed = urlparse(config.site_url)
        hostname = parsed.hostname
        path = parsed.path.rstrip("/")
        data = await self._graph_get(config, f"sites/{hostname}:{path}")
        return data["id"]

    async def _get_drive_id(self, config: SharePointConfig, site_id: str) -> str:
        """Find the document library drive that matches ``config.library_name``."""
        data = await self._graph_get(config, f"sites/{site_id}/drives")
        target = (config.library_name or "Documents").lower()
        for drive in data.get("value", []):
            if drive.get("name", "").lower() == target:
                return drive["id"]
        drives = data.get("value", [])
        if not drives:
            raise ValueError(f"No drives found on site {site_id}")
        return drives[0]["id"]

    # --- Public API ---------------------------------------------------------

    async def test_connection(self, config: SharePointConfig) -> dict:
        """Verify credentials and return site metadata."""
        if self.stub_mode:
            site = config.site_url or "https://contoso.sharepoint.com/sites/Legal"
            return {
                "connected": True,
                "stub_mode": True,
                "site_url": site,
                "library_name": config.library_name or "Documents",
                "message": f"Connected to {site} (stub mode)",
                "sample_documents": [d.title for d in _MOCK_LIBRARY[:3]],
                "tested_at": datetime.now(timezone.utc).isoformat(),
            }

        site_id = await self._resolve_site_id(config)
        drive_id = await self._get_drive_id(config, site_id)
        site_url = config.site_url
        library = config.library_name
        return {
            "connected": True,
            "stub_mode": False,
            "site_url": site_url,
            "library_name": library,
            "message": f"Connected to {site_url}",
            "site_id": site_id,
            "drive_id": drive_id,
            "sample_documents": [],
            "tested_at": datetime.now(timezone.utc).isoformat(),
        }

    async def list_documents(
        self, config: SharePointConfig, folder: str = ""
    ) -> list[dict]:
        """List documents in the configured library."""
        if self.stub_mode:
            return [
                {**d.model_dump(mode="json"), "synced": d.id in self._synced_ids}
                for d in _MOCK_LIBRARY
            ]

        site_id = await self._resolve_site_id(config)
        drive_id = await self._get_drive_id(config, site_id)
        base = f"drives/{drive_id}"
        endpoint = (
            f"{base}/root:/{folder}:/children"
            if folder
            else f"{base}/root/children"
        )
        select = "id,name,lastModifiedDateTime,size,webUrl,lastModifiedBy,file"
        data = await self._graph_get(
            config, f"{endpoint}?$select={select}&$top=100"
        )

        docs: list[dict] = []
        for item in data.get("value", []):
            if "file" not in item:  # skip folders
                continue
            name = item.get("name", "")
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            modified_by = (
                (item.get("lastModifiedBy") or {})
                .get("user", {})
                .get("displayName", "")
            )
            docs.append({
                "id": item["id"],
                "title": name,
                "document_type": _infer_type(name, ext),
                "modified": item.get("lastModifiedDateTime", ""),
                "size_bytes": item.get("size", 0),
                "author": modified_by,
                "web_url": item.get("webUrl", ""),
                "synced": item["id"] in self._synced_ids,
            })
        return docs

    async def sync_document(
        self, config: SharePointConfig, doc_id: str
    ) -> dict:
        """Mark a document as imported into NEXUS."""
        if self.stub_mode:
            doc = next((d for d in _MOCK_LIBRARY if d.id == doc_id), None)
            if doc is None:
                return {
                    "synced": False,
                    "reason": "document not found",
                    "doc_id": doc_id,
                }
            self._synced_ids.add(doc_id)
            return {
                "synced": True,
                "doc_id": doc_id,
                "title": doc.title,
                "message": f"{doc.title} queued for ingestion (stub mode)",
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }

        site_id = await self._resolve_site_id(config)
        drive_id = await self._get_drive_id(config, site_id)
        item = await self._graph_get(
            config,
            f"drives/{drive_id}/items/{doc_id}?$select=id,name,webUrl",
        )
        title = item.get("name", doc_id)
        self._synced_ids.add(doc_id)
        return {
            "synced": True,
            "doc_id": doc_id,
            "title": title,
            "message": f"{title} queued for ingestion",
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

    async def export_document(
        self,
        config: SharePointConfig,
        content: str,
        filename: str,
        folder: str = "NEXUS Drafts",
    ) -> dict:
        """Upload a text draft back into SharePoint Online.

        Uses the simple upload API (PUT < 4 MB). Legal drafts are well
        within that limit. Graph creates the target folder automatically
        when it does not exist.
        """
        if self.stub_mode:
            return {
                "exported": True,
                "stub_mode": True,
                "filename": filename,
                "folder": folder,
                "web_url": "",
                "message": f"{filename} would be uploaded to {folder} (stub mode)",
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }

        import httpx

        token = await self._get_token(config)
        site_id = await self._resolve_site_id(config)
        drive_id = await self._get_drive_id(config, site_id)
        upload_path = f"drives/{drive_id}/root:/{folder}/{filename}:/content"
        url = f"https://graph.microsoft.com/v1.0/{upload_path}"
        encoded = content.encode("utf-8")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.put(
                url,
                content=encoded,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "text/plain; charset=utf-8",
                },
            )
        resp.raise_for_status()
        item = resp.json()
        return {
            "exported": True,
            "stub_mode": False,
            "filename": filename,
            "folder": folder,
            "web_url": item.get("webUrl", ""),
            "message": f"{filename} uploaded to {folder}",
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def synced_count(self) -> int:
        """How many documents have been marked as synced this session."""
        return len(self._synced_ids)
