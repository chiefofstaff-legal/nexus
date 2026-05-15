# Nexus POC → Friday Demo Sprint Plan

**Author:** Lourens Cornelius Scheepers (V>>)
**Drafted:** 2026-04-14 (Tuesday evening SAST)
**Demo:** Friday 2026-04-17 (Zurich afternoon, ≈ 14:00 CET / 12:00 UTC)
**Effective working hours:** ~18–20h across Wed + Thu + Fri morning
**Audience:** Craig Miller, chiefofstaff.pro — signed Phase 1 deposit trigger

## Objective

Harden the 5 existing engine prototypes with four critical upgrades so Friday's demo lands as a credible Phase 1 kickoff validation for the signed 397,600 CHF engagement.

## What is NOT in scope (explicitly parked to Phase B)

- Multi-channel ingestion (Slack/Discord/WhatsApp auto-upload) — Tralala/grip-channel exists, leverage post-demo
- `/raw` folder with watchdog background scanner — Phase B
- Full Jaccard de-duplication (only fingerprint dedupe in W4 for near-duplicates, not full set-theoretic Jaccard)
- DIP/DRY/async refactors from tracked issues #5/#6/#7 — not demo-visible
- VPS cutover of `try.grip-web.com` (parked per user direction) — nexus-staging.grip-web.com is the demo URL until cutover
- Right-sized Swiss VPS for on-prem Ollama — Phase B (GPU-backed box)

## The four non-negotiable upgrades

| # | Upgrade | Why it matters for Friday | Reference |
|---|---|---|---|
| A | **Sensitivity classification fix** — replace density-regex with council-based LLM classifier, every decision logged as an IDR | Proposal page 9 commits to "privacy-aware model selection based on PII content. Confidential data never leaves the firm's network." — this is the FADP spine of the value prop and currently demonstrably wrong | Prototype 2 |
| B | **IDRs + council + Popperian falsification** | The killer differentiator Craig doesn't know he wants yet — auditable trail of "what the AI decided and why" with honest confidence levels. This is what "legal-grade evidence" means beyond the HMAC chain | NEW |
| C | **Novel PDF ingestion: local vision OCR + concurrent semantic analysis + NER** | "On-premises LLM option: Yes" (page 11) is a key competitive differentiator. Difficult scanned Swiss legal PDFs must work. | Prototype 1 (harden), NEW vision path |
| D | **Swiss Nihilism frontend polish + IDR visualisation + knowledge graph rework** | Craig is Swiss. Aesthetic signals competence. Multiple theme variants. Knowledge graph must show legal entity types distinctly. | Prototypes 3, all UI |

## Architecture overview

```
┌───────────────────────────────────────────────────────────────────┐
│                        NEXUS DEMO STACK                           │
│                                                                   │
│  Frontend (Next.js 16, Swiss Nihilism tokens, multiple themes)    │
│    │                                                              │
│    ▼                                                              │
│  /api/* (FastAPI)                                                 │
│    │                                                              │
│    ├── /api/documents/upload                                      │
│    │    └── DocumentProcessor                                     │
│    │         ├── Text-density check → pymupdf4llm (fast path)     │
│    │         └── Image/scanned → Vision pipeline                  │
│    │              ├── LOCAL: Qwen2.5-VL-7B via Ollama (primary)   │
│    │              └── API:   Claude Sonnet Vision (fallback)      │
│    │         │                                                    │
│    │         ├─(concurrent)─ spaCy NER                            │
│    │         ├─(concurrent)─ Semantic labelling via council       │
│    │         └─ IDR per decision                                  │
│    │                                                              │
│    ├── /api/routing/route                                         │
│    │    └── SensitivityClassifier (council-based)                 │
│    │         ├── fan-out → Claude + Groq (+ optional Ollama)      │
│    │         ├── synthesis → decision + confidence + falsification│
│    │         └── IDR per classification                           │
│    │                                                              │
│    ├── /api/idrs/*                                                │
│    │    └── IDR query endpoints (list, detail, by-input-hash)     │
│    │                                                              │
│    └── /api/entities/extract (existing, tighten)                  │
│         └── IDR per extraction                                    │
│                                                                   │
│  Core                                                             │
│    ├── audit_chain.py (existing, HMAC-SHA256)                     │
│    ├── intent_decision_record.py (NEW)                            │
│    └── config.py (existing Pydantic Config)                       │
└───────────────────────────────────────────────────────────────────┘
```

## Fibonacci wave plan

| Wave | Name | Precision | Budget | Branch | Hypothesis (H#) |
|---|---|---|---|---|---|
| **W0** | Sprint bootstrap: plan file, hypothesis pre-registration, Qwen2.5-VL pull | FAST | 30 min | main (this plan) | N/A (setup) |
| **W1** | IDR substrate: `intent_decision_record.py` Pydantic model, HMAC signing, chain helpers, `/api/idrs/*` endpoints | FAST | 2h | `feat/w1-idr-substrate` | **H1** |
| **W2** | Council primitive: parallel fan-out Claude + Groq (+ opt Ollama), synthesis, devil's advocate, confidence calc | CAREFUL | 3h | `feat/w2-council` | **H2** |
| **W3** | Sensitivity classifier overhaul: council-based, IDR logging, Popper falsification criterion, replace density-regex | CAREFUL | 3h | `feat/w3-sensitivity` | **H3** |
| **W4** | Vision OCR pipeline: Qwen2.5-VL local primary, Claude Vision fallback, concurrent NER + labelling, IDR per step | CAREFUL | 4h | `feat/w4-vision-ocr` | **H4** |
| **W5** | Swiss Nihilism frontend + IDR visualisation page + knowledge graph rework + multi-theme system | CAREFUL | 4h | `feat/w5-frontend` | **H5** |
| **W6** | Demo rehearsal: push to nexus-staging, full 5-prototype walkthrough, screen capture, CLAUDE.md update | FAST | 1h | main | **H6** |

**Total: ~17.5 hours** (leaves ~2h buffer for unforeseen).

## Pre-registered hypotheses (Popper falsification criteria)

### H1 — IDR substrate is round-trippable and chain-verifiable
- **Claim**: An IDR written through `idr_chain.append()` can be read back, signature-verified, and the chain's integrity demonstrated to break detectably on tamper.
- **Metric**: `pytest test_idr_chain.py::test_tamper_detection` passes.
- **Prediction**: 100% of valid IDRs round-trip; 100% of tampered IDRs are detected.
- **Falsification**: If any tampered IDR passes verification, or any valid IDR fails round-trip, H1 refuted.
- **Deadline**: Wed 2026-04-15 end-of-day.

### H2 — Multi-LLM council produces honest confidence
- **Claim**: For a held-out test set of 10 documents, the council-based classifier's reported confidence correlates with accuracy (high confidence → usually right, low confidence → sometimes wrong).
- **Metric**: Spearman correlation between confidence and correctness across the test set.
- **Prediction**: Correlation ≥ 0.4 (meaningful positive but not suspicious perfection).
- **Falsification**: Correlation < 0.2 (council confidence is noise) OR > 0.95 (suspicious overfit, dishonest claims).
- **Deadline**: Wed 2026-04-15 end-of-day.

### H3 — Sensitivity classification is honest on edge cases
- **Claim**: The new council-based sensitivity classifier correctly routes clearly-PII docs to `confidential`, clearly-clean docs to `public`, AND reports low confidence (< 0.7) on genuinely ambiguous edge cases like "the client's new strategy" without hard opinions.
- **Metric**: On a 5-doc test set (2 clearly confidential, 2 clearly public, 1 ambiguous), correct classifications + honest uncertainty on ambiguous.
- **Prediction**: 4/5 clear cases correct, 1/5 ambiguous case has reported confidence < 0.7 regardless of chosen label.
- **Falsification**: Any clear case misclassified with high confidence (≥ 0.8) OR ambiguous case classified with > 0.8 confidence in either direction.
- **Deadline**: Thu 2026-04-16 end-of-day.

### H4 — Vision OCR handles difficult PDFs without freezing demo machine
- **Claim**: Qwen2.5-VL-7B local inference on M1 Pro 16 GB extracts readable text from a scanned legal PDF in < 45 s per page, with memory peak under 10 GB unified memory, and automatically falls back to Claude Vision API on failure.
- **Metric**: Time-to-extract + peak memory usage + fallback trigger test.
- **Prediction**: 3 difficult test PDFs extract successfully; at least 1 triggers fallback (for fallback path coverage); no macOS freeze or swap thrash observed.
- **Falsification**: Any test PDF causes macOS freeze (memory pressure spinwait) OR all 3 extractions fail even with fallback OR per-page time > 120 s.
- **Deadline**: Thu 2026-04-16 end-of-day.

### H5 — Swiss Nihilism frontend reads as "Swiss designed" to a first-time viewer
- **Claim**: A cold viewer (playing Craig) completes the demo journey (upload → classify → route → entities → IDR → graph) in < 10 minutes without explanation, and the visual language reads as intentional, not template-generated.
- **Metric**: Visual walkthrough + subjective "would a Swiss lawyer take this seriously" check.
- **Prediction**: All 5 prototypes visually coherent under the new theme system; IDR page shows council votes + confidence bars + falsification criterion visibly; graph renders legal entity types distinctly.
- **Falsification**: Any visual regression vs. current state OR theme switching breaks layout OR IDR page is unreadable.
- **Deadline**: Fri 2026-04-17 morning.

### H6 — Demo is reproducible from cold state on nexus-staging
- **Claim**: Starting from `git clone` + `pip install` + `npm ci` + `pm2 start`, the full demo works on `nexus-staging.grip-web.com` with no manual patches required.
- **Metric**: `./start-demo.sh` completes without error, all 5 routes return expected content externally.
- **Prediction**: Green.
- **Falsification**: Any route returns 5xx or shows broken state after a cold deploy.
- **Deadline**: Fri 2026-04-17 morning, pre-demo.

## Known risks

- **M1 Pro 16 GB memory pressure** during W4 vision inference — mitigated by `OLLAMA_MAX_LOADED_MODELS=1`, explicit `ollama stop` of other models, single-PDF-at-a-time, and Claude Vision API fallback.
- **Council latency** — 3 parallel LLM calls per classification adds wall time. Acceptable for demo (it's a FEATURE that the system is deliberate, not a bug), but must stay < 5 s total per classification. Mitigation: parallel fan-out (asyncio.gather), 5 s timeout per call, partial-council verdict if one model fails.
- **Cloudflared remote-managed tunnel gotcha** (already burned once) — all VPS deploy changes will test on nexus-staging.grip-web.com, no cutover until user explicit-greenlights.
- **Demo machine freeze during live walkthrough** — Pre-warm Qwen2.5-VL at start-demo, ensure only needed Ollama models loaded, test rehearsal Thursday.

## Ship discipline

- Each wave = own feature branch + small PR + fast merge. No council review gate per wave (we're under time pressure and I'm solo on nexus-poc).
- Smoke test each wave before moving on.
- Anti-drift "what's up next" after each wave merge.
- 85% context gate triggers /save + fresh session (HITL confirm).
- All WIP changes committed at end of each work session.

## Parking lot (post-demo, Phase B)

- Full Jaccard de-duplication pipeline
- /raw folder with watchdog + periodic scanner
- Slack/Discord/WhatsApp auto-ingestion via Tralala/grip-channel
- Right-sized Swiss-hosted VPS for true on-prem confidential routing
- Dependabot high-severity vulns (2 in requirements)
- Issues #5 (DIP), #6 (_build_messages DRY), #7 (async-safety for Groq/Anthropic), #8 (groq dep explicit)
- Full test suite (pytest backend, Vitest frontend, Playwright e2e)
