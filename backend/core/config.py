"""
NEXUS POC — typed application configuration.

All application-wide settings that code needs to READ through a single
source of truth live here. Environment variables that are read directly
by third-party SDK constructors (Groq, Anthropic) are NOT mirrored into
this module — the SDKs own that contract.

Precedence (pydantic-settings default): actual environment variables
always win over the ``.env`` file fallback. This lets pm2 inject secrets
via its ``env_file`` directive on the VPS without conflicting with a
developer's local ``.env`` at the project root.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class NexusConfig(BaseSettings):
    """Typed application config — environment variables + ``.env`` fallback."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # On-prem confidential path — DISABLED by default.
    #
    # When False, LLMRouter never probes or calls Ollama, regardless of
    # what is listening on the Ollama port. CONFIDENTIAL sensitivity falls
    # through to Groq or Anthropic. This is the prod default: the shared
    # VPS does not have the RAM or CPU headroom to run on-prem inference.
    #
    # When True (opt-in for local dev with real headroom), the router
    # probes ``ollama_base_url`` and, if healthy, routes CONFIDENTIAL to
    # ``ollama_confidential_model``.
    ollama_enabled: bool = Field(default=False, alias="NEXUS_OLLAMA_ENABLED")
    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )
    ollama_confidential_model: str = Field(
        default="gemma4:e4b", alias="NEXUS_OLLAMA_MODEL"
    )

    # Local vision OCR path — independent of confidential LLM routing.
    #
    # When True (default), image-only PDFs route first to a local
    # vision model via Ollama (``vision_ocr_model``). On failure the
    # extractor falls back to Claude Haiku Vision. When False, the
    # Qwen primary is skipped and the extractor goes straight to
    # Claude Vision — used on VPS / constrained boxes where loading
    # a 7B vision model would thrash memory.
    vision_ocr_enabled: bool = Field(default=True, alias="NEXUS_VISION_OCR_ENABLED")
    vision_ocr_model: str = Field(
        default="qwen2.5vl:7b", alias="NEXUS_VISION_MODEL"
    )
    vision_ocr_max_pages: int = Field(default=5, alias="NEXUS_VISION_MAX_PAGES")
    vision_ocr_timeout_s: int = Field(default=120, alias="NEXUS_VISION_TIMEOUT_S")


@lru_cache(maxsize=1)
def get_config() -> NexusConfig:
    """Return the cached, validated application config."""
    return NexusConfig()
