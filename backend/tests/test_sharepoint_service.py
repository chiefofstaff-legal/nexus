"""
SharePoint service falsification tests.

H-SP-1: stub test_connection returns connected=True and stub_mode=True.
H-SP-2: stub list_documents returns all 5 mock documents with 'synced' key.
H-SP-3: stub sync_document marks a known document as synced.
H-SP-4: stub sync_document returns synced=False for an unknown id.
H-SP-5: stub export_document returns exported=True and stub_mode=True.
H-SP-6: synced_count tracks correctly across multiple syncs.
H-SP-7: _infer_type resolves keyword patterns in filenames.
H-SP-8: SharePointConfig accepts client_secret field.
H-SP-9: _cache_key is composed of tenant_id and client_id.
H-SP-10: identical configs produce the same cache key.
"""

import asyncio

import pytest

from services.sharepoint_service import (
    SharePointConfig,
    SharePointConnector,
    _MOCK_LIBRARY,
    _cache_key,
    _infer_type,
)


@pytest.fixture
def stub():
    return SharePointConnector(stub_mode=True)


# ---------------------------------------------------------------------------
# H-SP-1 — test_connection stub
# ---------------------------------------------------------------------------

def test_test_connection_stub_returns_connected(stub):
    result = asyncio.run(stub.test_connection(SharePointConfig()))
    assert result["connected"] is True
    assert result["stub_mode"] is True
    assert "sample_documents" in result


def test_test_connection_stub_uses_provided_site_url(stub):
    cfg = SharePointConfig(site_url="https://example.sharepoint.com/sites/test")
    result = asyncio.run(stub.test_connection(cfg))
    assert result["site_url"] == "https://example.sharepoint.com/sites/test"


# ---------------------------------------------------------------------------
# H-SP-2 — list_documents stub
# ---------------------------------------------------------------------------

def test_list_documents_stub_returns_five(stub):
    docs = asyncio.run(stub.list_documents(SharePointConfig()))
    assert len(docs) == 5


def test_list_documents_stub_each_has_required_keys(stub):
    docs = asyncio.run(stub.list_documents(SharePointConfig()))
    for doc in docs:
        for key in ("id", "title", "document_type", "size_bytes", "synced"):
            assert key in doc, f"Missing key '{key}' in {doc}"


def test_list_documents_stub_all_unsynced_initially(stub):
    docs = asyncio.run(stub.list_documents(SharePointConfig()))
    assert all(not d["synced"] for d in docs)


# ---------------------------------------------------------------------------
# H-SP-3 — sync_document marks known doc as synced
# ---------------------------------------------------------------------------

def test_sync_document_stub_marks_synced(stub):
    doc_id = _MOCK_LIBRARY[0].id
    result = asyncio.run(stub.sync_document(SharePointConfig(), doc_id))
    assert result["synced"] is True
    assert result["doc_id"] == doc_id
    assert "title" in result


def test_sync_document_stub_reflects_in_list(stub):
    doc_id = _MOCK_LIBRARY[0].id
    asyncio.run(stub.sync_document(SharePointConfig(), doc_id))
    docs = asyncio.run(stub.list_documents(SharePointConfig()))
    synced_doc = next(d for d in docs if d["id"] == doc_id)
    assert synced_doc["synced"] is True


# ---------------------------------------------------------------------------
# H-SP-4 — sync_document unknown id
# ---------------------------------------------------------------------------

def test_sync_document_stub_unknown_id_returns_not_synced(stub):
    result = asyncio.run(stub.sync_document(SharePointConfig(), "not-a-real-id"))
    assert result["synced"] is False
    assert "not found" in result["reason"]


# ---------------------------------------------------------------------------
# H-SP-5 — export_document stub
# ---------------------------------------------------------------------------

def test_export_document_stub_returns_exported(stub):
    result = asyncio.run(
        stub.export_document(SharePointConfig(), "Draft content here.", "draft.txt")
    )
    assert result["exported"] is True
    assert result["stub_mode"] is True
    assert result["filename"] == "draft.txt"
    assert result["folder"] == "NEXUS Drafts"


def test_export_document_stub_custom_folder(stub):
    result = asyncio.run(
        stub.export_document(SharePointConfig(), "Content", "report.txt", folder="Legal")
    )
    assert result["folder"] == "Legal"


# ---------------------------------------------------------------------------
# H-SP-6 — synced_count
# ---------------------------------------------------------------------------

def test_synced_count_starts_at_zero(stub):
    assert stub.synced_count() == 0


def test_synced_count_increments_per_sync(stub):
    asyncio.run(stub.sync_document(SharePointConfig(), _MOCK_LIBRARY[0].id))
    assert stub.synced_count() == 1
    asyncio.run(stub.sync_document(SharePointConfig(), _MOCK_LIBRARY[1].id))
    assert stub.synced_count() == 2


def test_synced_count_not_incremented_for_unknown_id(stub):
    asyncio.run(stub.sync_document(SharePointConfig(), "bad-id"))
    assert stub.synced_count() == 0


# ---------------------------------------------------------------------------
# H-SP-7 — _infer_type
# ---------------------------------------------------------------------------

def test_infer_type_nda():
    assert _infer_type("NDA Project Helvetia.pdf", "pdf") == "nda"


def test_infer_type_invoice():
    assert _infer_type("Invoice 2026-Q2.pdf", "pdf") == "invoice"


def test_infer_type_brief():
    assert _infer_type("Reply Brief ACME AG.docx", "docx") == "brief"


def test_infer_type_contract_via_agreement():
    assert _infer_type("Service Agreement v3.pdf", "pdf") == "contract"


def test_infer_type_deed():
    assert _infer_type("Trust Deed 2024.pdf", "pdf") == "contract"


def test_infer_type_unknown_falls_back_to_other():
    assert _infer_type("random_scan_001.pdf", "pdf") == "other"


# ---------------------------------------------------------------------------
# H-SP-8 — SharePointConfig has client_secret
# ---------------------------------------------------------------------------

def test_sharepoint_config_accepts_client_secret():
    cfg = SharePointConfig(
        tenant_id="t-id",
        client_id="c-id",
        client_secret="very-secret",
        site_url="https://example.sharepoint.com/sites/legal",
    )
    assert cfg.client_secret == "very-secret"


def test_sharepoint_config_client_secret_defaults_empty():
    cfg = SharePointConfig()
    assert cfg.client_secret == ""


# ---------------------------------------------------------------------------
# H-SP-9 / H-SP-10 — _cache_key
# ---------------------------------------------------------------------------

def test_cache_key_contains_tenant_and_client():
    cfg = SharePointConfig(tenant_id="my-tenant", client_id="my-client")
    key = _cache_key(cfg)
    assert "my-tenant" in key
    assert "my-client" in key


def test_cache_key_identical_configs_produce_same_key():
    cfg1 = SharePointConfig(tenant_id="t", client_id="c")
    cfg2 = SharePointConfig(tenant_id="t", client_id="c")
    assert _cache_key(cfg1) == _cache_key(cfg2)


def test_cache_key_different_tenants_differ():
    cfg1 = SharePointConfig(tenant_id="tenant-a", client_id="same")
    cfg2 = SharePointConfig(tenant_id="tenant-b", client_id="same")
    assert _cache_key(cfg1) != _cache_key(cfg2)
