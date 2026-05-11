"""
W4 — Vision OCR fallback chain tests.

Hypothesis H4 claim: local Qwen2.5-VL is the primary on-prem path and
Claude Haiku Vision is the API fallback, with mechanical enforcement of
both ordering and the kill-switch flag.

These tests do NOT hit Ollama or Anthropic. They exercise the orchestrator
wiring by mocking ``_ocr_via_qwen_vl`` and ``_ocr_via_claude_vision`` so
that a CI box with no network and no Ollama can still verify the branch
structure. The actual vision quality is a separate empirical test run
manually on real scanned PDFs before the Friday demo (see runbook).
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.config import NexusConfig
from services.document_processor import DocumentProcessor


@pytest.fixture
def scanned_pdf(tmp_path: Path) -> Path:
    """Build a minimal PDF with a rasterised page (forces vision path)."""
    import pymupdf  # type: ignore

    pdf_path = tmp_path / "scanned.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)  # blank -> text extraction < 50 chars
    page.insert_text((10, 10), " ")  # whitespace to keep pymupdf happy
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def processor(tmp_path: Path) -> DocumentProcessor:
    fake_anthropic = AsyncMock()
    return DocumentProcessor(data_dir=tmp_path, anthropic_client=fake_anthropic)


def _patch_config(**overrides):
    """Return a cache-busting patched NexusConfig for get_config()."""
    defaults = dict(
        ollama_enabled=False,
        ollama_base_url="http://localhost:11434",
        ollama_confidential_model="gemma4:e4b",
        vision_ocr_enabled=True,
        vision_ocr_model="qwen2.5vl:7b",
        vision_ocr_max_pages=2,
        vision_ocr_timeout_s=5,
    )
    defaults.update(overrides)
    return patch(
        "services.document_processor.get_config",
        return_value=NexusConfig(**defaults),
    )


@pytest.mark.asyncio
async def test_vision_primary_path_uses_qwen(processor, scanned_pdf):
    """When Qwen succeeds, method is 'qwen_vl:<model>' and Claude is NOT called."""
    with _patch_config(), \
         patch.object(processor, "_ocr_via_qwen_vl",
                      new=AsyncMock(return_value="QWEN TEXT")) as qwen, \
         patch.object(processor, "_ocr_via_claude_vision",
                      new=AsyncMock(return_value="CLAUDE TEXT")) as claude:
        result = await processor._extract_pdf_via_vision(scanned_pdf)

    assert result.text == "QWEN TEXT"
    assert result.method.startswith("qwen_vl:")
    assert qwen.await_count == 1
    assert claude.await_count == 0


@pytest.mark.asyncio
async def test_vision_falls_back_to_claude_on_qwen_failure(processor, scanned_pdf):
    """Qwen raising -> Claude fires and method is 'claude_haiku_vision'."""
    with _patch_config(), \
         patch.object(processor, "_ocr_via_qwen_vl",
                      new=AsyncMock(side_effect=RuntimeError("ollama down"))), \
         patch.object(processor, "_ocr_via_claude_vision",
                      new=AsyncMock(return_value="CLAUDE FALLBACK")) as claude:
        result = await processor._extract_pdf_via_vision(scanned_pdf)

    assert result.text == "CLAUDE FALLBACK"
    assert result.method == "claude_haiku_vision"
    assert claude.await_count == 1


@pytest.mark.asyncio
async def test_vision_disabled_skips_qwen_entirely(processor, scanned_pdf):
    """vision_ocr_enabled=False -> Qwen never called, straight to Claude."""
    with _patch_config(vision_ocr_enabled=False), \
         patch.object(processor, "_ocr_via_qwen_vl",
                      new=AsyncMock(return_value="SHOULD_NOT_RUN")) as qwen, \
         patch.object(processor, "_ocr_via_claude_vision",
                      new=AsyncMock(return_value="DIRECT CLAUDE")) as claude:
        result = await processor._extract_pdf_via_vision(scanned_pdf)

    assert result.text == "DIRECT CLAUDE"
    assert result.method == "claude_haiku_vision"
    assert qwen.await_count == 0
    assert claude.await_count == 1


@pytest.mark.asyncio
async def test_vision_both_fail_when_no_anthropic_client(tmp_path, scanned_pdf):
    """Qwen dead + no Anthropic key -> failed method, pages still counted."""
    processor = DocumentProcessor(data_dir=tmp_path, anthropic_client=None)
    with _patch_config(), \
         patch.object(processor, "_ocr_via_qwen_vl",
                      new=AsyncMock(side_effect=RuntimeError("no ollama"))):
        result = await processor._extract_pdf_via_vision(scanned_pdf)

    assert result.method == "failed"
    assert result.page_count == 1  # one page in the fixture
    assert "requires" in result.text.lower()
