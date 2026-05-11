"""
Drafting service falsification tests.

H-DS-1: list_templates returns all 8 registered templates.
H-DS-2: get_template resolves by id; returns None for unknown ids.
H-DS-3: _compose_matter_block builds the correct matter context block.
H-DS-4: _reading_minutes computes at 200 wpm.
H-DS-5: _parse_voice_json falls back to "letter" for unknown template ids.
H-DS-6: generate_draft raises ValueError for unknown template_id (no LLM hit).
H-DS-7: summarise_document raises ValueError for empty text (no LLM hit).
H-DS-8: parse_voice_request raises ValueError for empty transcript (no LLM hit).
H-DS-9: SummariseRequest rejects invalid summary_type at Pydantic validation.
H-DS-10: _call_anthropic raises RuntimeError when client is None.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from services.drafting_service import (
    CCH,
    DraftRequest,
    DRAFTING_MODEL,
    SummariseRequest,
    SUMMARY_MODEL,
    _call_anthropic,
    _compose_matter_block,
    _parse_multi_intent_json,
    _parse_voice_json,
    _reading_minutes,
    generate_draft,
    get_template,
    list_templates,
    parse_multi_voice_request,
    parse_voice_request,
    summarise_document,
)


# ---------------------------------------------------------------------------
# H-DS-1 — template catalogue completeness
# ---------------------------------------------------------------------------

def test_list_templates_returns_all_eight():
    templates = list_templates()
    ids = {t["id"] for t in templates}
    expected = {"contract", "brief", "nda", "motion", "letter", "summary", "invoice_letter", "custody_petition"}
    assert ids == expected, f"Missing templates: {expected - ids}"


def test_list_templates_each_has_required_keys():
    for t in list_templates():
        assert "id" in t
        assert "name" in t
        assert "base_prompt" in t


# ---------------------------------------------------------------------------
# H-DS-2 — get_template resolution
# ---------------------------------------------------------------------------

def test_get_template_known_id():
    t = get_template("nda")
    assert t is not None
    assert t.id == "nda"
    assert "non-disclosure" in t.base_prompt.lower()


def test_get_template_unknown_id_returns_none():
    assert get_template("does_not_exist") is None


# ---------------------------------------------------------------------------
# H-DS-3 — _compose_matter_block
# ---------------------------------------------------------------------------

def test_compose_matter_block_all_fields():
    req = DraftRequest(
        template_id="nda",
        matter_name="Richter Divorce",
        client_name="Maria Richter",
        key_facts=["Settlement of CHF 500,000", "Joint custody"],
        additional_instructions="Include liquidated damages clause.",
    )
    block = _compose_matter_block(req)
    assert "Richter Divorce" in block
    assert "Maria Richter" in block
    assert "CHF 500,000" in block
    assert "liquidated damages" in block


def test_compose_matter_block_empty_request_returns_empty():
    req = DraftRequest(template_id="letter")
    assert _compose_matter_block(req) == ""


def test_compose_matter_block_blank_facts_filtered():
    req = DraftRequest(template_id="contract", key_facts=["", "  ", "Real fact"])
    block = _compose_matter_block(req)
    assert "Real fact" in block
    # Blank items should not produce empty bullet points
    assert "- \n" not in block


# ---------------------------------------------------------------------------
# H-DS-4 — _reading_minutes
# ---------------------------------------------------------------------------

def test_reading_minutes_200_words():
    text = " ".join(["word"] * 200)
    assert _reading_minutes(text) == 1.0


def test_reading_minutes_empty_text():
    assert _reading_minutes("") == 0.0


def test_reading_minutes_rounds_to_one_decimal():
    text = " ".join(["word"] * 100)  # 100 words = 0.5 min
    assert _reading_minutes(text) == 0.5


# ---------------------------------------------------------------------------
# H-DS-5 — _parse_voice_json fallback
# ---------------------------------------------------------------------------

_TEMPLATE_IDS = ["contract", "brief", "nda", "motion", "letter", "summary", "invoice_letter", "custody_petition"]


def test_parse_voice_json_valid_template():
    raw = '{"template_id": "nda", "matter_name": "Test", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": "NDA requested."}'
    plan = _parse_voice_json(raw, _TEMPLATE_IDS)
    assert plan.template_id == "nda"
    assert plan.matter_name == "Test"


def test_parse_voice_json_unknown_template_falls_back_to_letter():
    raw = '{"template_id": "unicorn", "matter_name": "", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": ""}'
    plan = _parse_voice_json(raw, _TEMPLATE_IDS)
    assert plan.template_id == "letter"
    assert "not in catalogue" in plan.rationale


def test_parse_voice_json_no_json_raises_value_error():
    with pytest.raises(ValueError, match="no JSON found"):
        _parse_voice_json("Sorry, I cannot help.", _TEMPLATE_IDS)


def test_parse_voice_json_with_llm_preamble():
    raw = 'Here is the JSON you requested:\n{"template_id": "motion", "matter_name": "Case X", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": "Motion."}'
    plan = _parse_voice_json(raw, _TEMPLATE_IDS)
    assert plan.template_id == "motion"


# ---------------------------------------------------------------------------
# H-DS-6 — generate_draft input guard (no LLM hit needed)
# ---------------------------------------------------------------------------

def test_generate_draft_unknown_template_raises():
    with pytest.raises(ValueError, match="unknown template_id"):
        asyncio.run(generate_draft(None, DraftRequest(template_id="nonexistent")))


# ---------------------------------------------------------------------------
# H-DS-7 — summarise_document input guard (no LLM hit needed)
# ---------------------------------------------------------------------------

def test_summarise_document_empty_text_raises():
    with pytest.raises(ValueError, match="document_text is empty"):
        asyncio.run(summarise_document(None, ""))


def test_summarise_document_invalid_type_raises():
    with pytest.raises(ValueError, match="summary_type must be one of"):
        asyncio.run(summarise_document(None, "some text", summary_type="haiku"))


# ---------------------------------------------------------------------------
# H-DS-8 — parse_voice_request input guard (no LLM hit needed)
# ---------------------------------------------------------------------------

def test_parse_voice_request_empty_transcript_raises():
    with pytest.raises(ValueError, match="transcript is empty"):
        asyncio.run(parse_voice_request(None, ""))


def test_parse_voice_request_whitespace_only_raises():
    with pytest.raises(ValueError, match="transcript is empty"):
        asyncio.run(parse_voice_request(None, "   "))


# ---------------------------------------------------------------------------
# H-DS-9 — SummariseRequest Pydantic validation
# ---------------------------------------------------------------------------

def test_summarise_request_valid():
    req = SummariseRequest(document_text="Hello.", summary_type="detailed")
    assert req.summary_type == "detailed"


def test_summarise_request_default_summary_type():
    req = SummariseRequest(document_text="Hello.")
    assert req.summary_type == "brief"


def test_summarise_request_invalid_type_raises():
    with pytest.raises(ValidationError):
        SummariseRequest(document_text="Hello.", summary_type="invalid")


# ---------------------------------------------------------------------------
# H-DS-10 — _call_anthropic None-client guard
# ---------------------------------------------------------------------------

def test_call_anthropic_none_client_raises_runtime_error():
    with pytest.raises(RuntimeError, match="Anthropic client unavailable"):
        asyncio.run(_call_anthropic(None, "model", "system", "prompt"))


# ---------------------------------------------------------------------------
# H-DS-11 — CCH model constant integrity (falsified if wrong model is used)
# ---------------------------------------------------------------------------

def test_cch_constant_is_haiku():
    assert CCH == "claude-haiku-4-5-20251001", (
        f"CCH must be claude-haiku-4-5-20251001, got {CCH!r}"
    )


def test_drafting_model_uses_cch():
    assert DRAFTING_MODEL == CCH, (
        f"DRAFTING_MODEL must equal CCH ({CCH!r}), got {DRAFTING_MODEL!r}"
    )


def test_summary_model_uses_cch():
    assert SUMMARY_MODEL == CCH, (
        f"SUMMARY_MODEL must equal CCH ({CCH!r}), got {SUMMARY_MODEL!r}"
    )


# ---------------------------------------------------------------------------
# H-DS-12 — generate_draft with mock client returns valid DraftResponse
# ---------------------------------------------------------------------------

def _make_mock_client(text: str = "Draft text here."):
    """Build a minimal AsyncMock that mimics anthropic.AsyncAnthropic."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=msg)
    return client


def test_generate_draft_mock_client_returns_response():
    client = _make_mock_client("This is the drafted NDA content.")
    req = DraftRequest(template_id="nda", matter_name="Test Matter", client_name="Test Client")
    result = asyncio.run(generate_draft(client, req))
    assert result.template_id == "nda"
    assert result.draft_text == "This is the drafted NDA content."
    assert result.word_count == 6
    assert result.model_used == CCH


def test_generate_draft_calls_correct_model():
    client = _make_mock_client("draft")
    req = DraftRequest(template_id="contract")
    asyncio.run(generate_draft(client, req))
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == CCH, (
        f"generate_draft must call CCH model, got {call_kwargs['model']!r}"
    )


# ---------------------------------------------------------------------------
# H-DS-13 — _call_anthropic wraps SDK errors as RuntimeError → 502 path
# ---------------------------------------------------------------------------

def test_call_anthropic_sdk_error_raises_runtime_error():
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=Exception("API rate limit"))
    with pytest.raises(RuntimeError, match="Anthropic API error"):
        asyncio.run(_call_anthropic(client, CCH, "system", "prompt"))


# ---------------------------------------------------------------------------
# H-DS-14 — summarise_document mock client returns expected shape
# ---------------------------------------------------------------------------

def test_summarise_document_mock_client():
    client = _make_mock_client("Action item 1. Action item 2.")
    result = asyncio.run(summarise_document(client, "Some contract text.", "action_items"))
    assert result["summary_type"] == "action_items"
    assert "Action item" in result["summary"]
    assert result["model_used"] == CCH


# ---------------------------------------------------------------------------
# H-DS-15 — parse_voice_request mock client extracts valid plan
# ---------------------------------------------------------------------------

def test_parse_voice_request_mock_client():
    raw_json = '{"template_id": "nda", "matter_name": "BigCo deal", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": "NDA for acquisition."}'
    client = _make_mock_client(raw_json)
    plan = asyncio.run(parse_voice_request(client, "Draft an NDA for the BigCo deal"))
    assert plan.template_id == "nda"
    assert plan.matter_name == "BigCo deal"


# ---------------------------------------------------------------------------
# H-DS-16 — _parse_multi_intent_json: single and compound intents
# ---------------------------------------------------------------------------

def test_parse_multi_intent_json_single():
    raw = '[{"template_id": "nda", "matter_name": "Alpine", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": "NDA."}]'
    plans = _parse_multi_intent_json(raw, _TEMPLATE_IDS)
    assert len(plans) == 1
    assert plans[0].template_id == "nda"
    assert plans[0].matter_name == "Alpine"


def test_parse_multi_intent_json_compound():
    raw = (
        '[{"template_id": "nda", "matter_name": "Alpine Corp", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": "NDA requested."},'
        ' {"template_id": "invoice_letter", "matter_name": "Müller", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": "Billing."}]'
    )
    plans = _parse_multi_intent_json(raw, _TEMPLATE_IDS)
    assert len(plans) == 2
    assert plans[0].template_id == "nda"
    assert plans[1].template_id == "invoice_letter"


def test_parse_multi_intent_json_unknown_template_falls_back():
    raw = '[{"template_id": "unicorn", "matter_name": "X", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": ""}]'
    plans = _parse_multi_intent_json(raw, _TEMPLATE_IDS)
    assert plans[0].template_id == "letter"
    assert "not in catalogue" in plans[0].rationale


def test_parse_multi_intent_json_no_array_falls_back_to_single():
    raw = '{"template_id": "motion", "matter_name": "Court X", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": "Motion."}'
    plans = _parse_multi_intent_json(raw, _TEMPLATE_IDS)
    assert len(plans) == 1
    assert plans[0].template_id == "motion"


def test_parse_multi_intent_json_empty_array_returns_default():
    plans = _parse_multi_intent_json("[]", _TEMPLATE_IDS)
    assert len(plans) == 1
    assert plans[0].template_id == "letter"


# ---------------------------------------------------------------------------
# H-DS-17 — parse_multi_voice_request: empty transcript guard
# ---------------------------------------------------------------------------

def test_parse_multi_voice_request_empty_raises():
    with pytest.raises(ValueError, match="transcript is empty"):
        asyncio.run(parse_multi_voice_request(None, ""))


def test_parse_multi_voice_request_mock_compound():
    raw_array = (
        '[{"template_id": "nda", "matter_name": "Alpine", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": "NDA."},'
        ' {"template_id": "letter", "matter_name": "Müller", "client_name": "", "key_facts": [], "additional_instructions": "", "rationale": "Letter."}]'
    )
    client = _make_mock_client(raw_array)
    plans = asyncio.run(parse_multi_voice_request(client, "Draft NDA for Alpine and letter to Müller"))
    assert len(plans) == 2
    assert plans[0].template_id == "nda"
    assert plans[1].template_id == "letter"
