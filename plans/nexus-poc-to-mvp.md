# NEXUS POC -> MVP Hardening Sprint

**Author:** Lourens Cornelius Scheepers (V>>)
**Drafted:** 2026-04-15 — post-VPS-deploy browser walkthrough
**Trigger:** V>> walked the staging demo and surfaced a bug list + feature
gaps that separate a polished POC from an MVP Craig can hand to a lawyer.

## Scope

Two classes of work:

1. **Bugs** — user-visible defects found during the walkthrough
2. **Enhancements** — missing capability that turns the POC into an MVP

The sprint plan's original 6-wave arc (IDR substrate -> vision OCR -> frontend)
is complete and shipped on nexus-staging. This is the NEXT arc — take the
live system and make it trustworthy, coherent, and demo-proof under scrutiny.

## Inventory

### Bugs (user-visible defects)

| # | Location | Defect | Root cause |
|---|---|---|---|
| B1 | `/idr`, `/` ingestion cards | Text truncated at ~120 chars with "…" | `truncate()` helper + fixed char limits; should expand or wrap |
| B2 | `/routing` audit trail | AUDIT TRAIL section requires manual "LOAD" click | No auto-load on mount |
| B3 | `/routing` council | Groq errors with `Connection error.` on large docs | Groq free tier rate limit OR context overflow on 20k+ char prompts |
| B4 | `/routing` "Classify Only" | Private doc mis-classified as `public` 29.2% | Classify Only still uses the OLD density-regex heuristic, not the W3 council |
| B5 | `/` ingestion | Doc 3 / 10 fails with 500 | Unknown — needs log dive |
| B6 | `/graph` | `R45,000,000.00` labelled `ORGANISATION` | spaCy `en_core_web_sm` mis-types SA Rand currency as proper noun; no MONEY post-processing |
| B7 | `/idr` copy | "Popper falsification criterion" labelled as such | V>> wants Popper name removed from UX copy |
| B8 | `/idr` falsification criterion text | Current "same or more-restrictive" is an acceptance zone, not a falsification | Conceptual defect — any different label should refute; both directions are failure modes |

### Enhancements (POC -> MVP)

| # | Capability | Current state | Target |
|---|---|---|---|
| E1 | Document viewer | Clicking documents does nothing | Modal or `/docs/[id]` page with raw + redacted toggle, PII highlighted, export redacted |
| E2 | Semantic search | Returns mixed / wrong results | Real vector DB path (ChromaDB already in stack), highlighted terms, click-through to viewer |
| E3 | IDRs everywhere | Only routing test queries write IDRs | Every system decision writes an IDR: ingestion classification, entity extraction, semantic search, vision OCR provider selection, redaction policy |
| E4 | Graph NER quality | 6 greyscale categories, currency = ORG | Legal-specific NER (money regex pre/post-process, case-number extractor, legal-entity rules), more distinct hues |
| E5 | Graph usability | 727 nodes, 1106 edges — visually overwhelming | Filters (by type, by document, by date), smart clustering, focus mode |

## Fibonacci wave plan

| W | Name | Precision | Budget | Hypothesis | Covers |
|---|---|---|---|---|---|
| W1 | Trust fixes — text, Popper, falsification criterion, audit auto-load | FAST | 1 h | H-MVP-1 | B1, B2, B7, B8 |
| W2 | Routing resilience — Groq error handling, retire or retarget Classify Only | FAST | 1 h | H-MVP-2 | B3, B4 |
| W3 | IDR ubiquity + review endpoint — every decision writes an IDR, PENDING can transition | CAREFUL | 3 h | H-MVP-3 | E3 (+ decision_point enum expansion + review path) |
| W4 | NER hardening — legal entity rules, currency post-processing, ingestion 500 fix | CAREFUL | 3 h | H-MVP-4 | B5, B6 (+ graph colours) |
| W5 | Document viewer + redaction export | CAREFUL | 5 h | H-MVP-5 | E1 |
| W6 | Semantic search rebuild + graph usability | CAREFUL | 8 h | H-MVP-6, H-MVP-7 | E2, E5 |

Total: ~20 h. Context-gate breathing pauses between W3 and W4 (expected mid-
session compact) and between W5 and W6 (context will be heavy by then).

## Pre-registered hypotheses

### H-MVP-1 — Trust fixes are visible without regression
- **Claim**: After W1, (a) no user-visible text is cut off in the /idr council vote rows, reasoning line, or ingestion summary cards; (b) the /routing audit trail renders without a manual load click on page mount; (c) the word "Popper" no longer appears in any user-facing copy; (d) the falsification criterion statement names both under-classification and over-classification failure modes as refutations.
- **Metric**: Visual diff against the screenshots V>> sent + grep -c "Popper" in frontend/src = 0.
- **Prediction**: All four green, no regression on existing green routes (/graph, /sops, /).
- **Falsification**: Any bullet above still fails OR /graph /sops / regress visually.
- **Deadline**: 2026-04-15 end-of-day.

### H-MVP-2 — Routing stays honest when a provider fails
- **Claim**: Groq failure on a large document (a) no longer blocks the Anthropic vote from rendering, (b) surfaces a clear provider-level error in the UI (not a cryptic stack trace), and (c) still writes an IDR capturing which provider errored so the audit chain remains intact.
- **Metric**: Manual test with the 20,583-char test document; council deliberation returns a valid synthesis with Groq marked `error` and Anthropic still voting; IDR recorded.
- **Prediction**: Anthropic vote visible, Groq row shows "error: context length exceeded" or equivalent, synthesis_method = "single_model_fallback", IDR logged.
- **Falsification**: Any of the three fails.
- **Deadline**: 2026-04-15 end-of-day.

### H-MVP-3 — IDRs cover every decision the system makes, and PENDING can transition
- **Claim**: After W3, (a) the decision_point enum includes at least: sensitivity_classification, document_classification, entity_extraction, semantic_search, vision_ocr_provider, redaction_policy; (b) a test ingestion of 5 documents produces >= 5 document_classification IDRs, >= 5 entity_extraction IDRs, and the existing sensitivity_classification IDRs; (c) a new endpoint `POST /api/idrs/{seq}/review` accepts `{status, reviewer_id, reviewer_label, notes}`, writes an append-only REVIEW IDR with `decision_point=falsification_review` referencing the reviewed sequence, and updates the chain such that the original IDR's `falsification_status` is re-derived from the review chain on read (not mutated in place); (d) the /idr page shows a review control that lets a human mark any PENDING IDR as confirmed / refuted / inconclusive.
- **Metric**: After ingestion + one manual review via the UI, `curl /api/idrs/recent?limit=100` shows >= 15 IDRs across >= 3 decision_points, the reviewed IDR's effective status is the non-PENDING value, and the chain still verifies.
- **Prediction**: >= 15 IDRs across >= 3 distinct decision_points, >= 1 review IDR, effective status derivation correct, chain verified.
- **Falsification**: < 15 IDRs OR any decision_point missing OR review endpoint missing OR review mutates past entries OR chain breaks.
- **Deadline**: 2026-04-16 morning.

### H-MVP-4 — NER no longer miscategorises currency and the ingestion 500 is fixed
- **Claim**: `R45,000,000.00` and similar currency tokens (ZAR, USD, CHF, EUR, GBP) are classified `MONEY` not `ORGANISATION` by the entity extraction pipeline. The specific file that failed doc 3/10 ingestion returns a DocumentRecord on retry.
- **Metric**: Unit test with currency strings; retry ingestion of the failing file.
- **Prediction**: 100% of currency tokens typed MONEY; failing file ingests successfully.
- **Falsification**: Any currency token still typed as ORG OR the 500 error persists.
- **Deadline**: 2026-04-16 afternoon.

### H-MVP-5 — Document viewer reads the document and respects the redaction toggle
- **Claim**: Clicking a document card on `/` opens a viewer (modal or `/docs/[id]`). The viewer has a redaction toggle that greys out or replaces PII spans. An export button downloads a redacted copy with PII replaced by `[REDACTED]`.
- **Metric**: Manual walkthrough on a test document containing a known name + phone + email.
- **Prediction**: Viewer opens, toggle switches state visibly, export produces a file where the three PII tokens are masked.
- **Falsification**: Viewer fails to open OR toggle has no visible effect OR export leaks PII.
- **Deadline**: 2026-04-16 end-of-day.

### H-MVP-6 — Semantic search returns relevant chunks fast
- **Claim**: A query "git lock architecture" returns the GRIP Git-Lock memo in the top 3 results in under 500 ms with the matched phrase highlighted.
- **Metric**: Wall time + top-k result list + visible highlight.
- **Prediction**: <= 500 ms, GRIP memo at position 1, "git lock" highlighted.
- **Falsification**: Any of the three fails.
- **Deadline**: 2026-04-17 morning.

### H-MVP-7 — Graph is legible at 700+ nodes
- **Claim**: A filter control lets the user hide all node types except one (e.g. "show only documents"), reducing the visible node count by >= 80%. Legal entity type colours are distinct enough that red-green colour-blind users can still tell Person from Organisation.
- **Metric**: Click filter, count visible nodes; run the palette through a Coblis simulator.
- **Prediction**: Filter functional, colour-blind check passes.
- **Falsification**: Filter has no effect OR palette fails colour-blind contrast.
- **Deadline**: 2026-04-17 morning.

## Ship discipline

- Each wave -> own feature branch + small PR + admin-merge + VPS deploy
- Anti-drift "what's up next" after each wave merge
- VPS deploy via same pattern as W4/W5/W6 (git pull + rebuild + pm2 restart)
- Context gate: if we hit 80%, checkpoint + /save + continue in fresh session
- Hypothesis verification after each wave, with the falsification sentence stated
  plainly in each commit message

## Parking lot

- Full Jaccard dedupe (already parked from the first sprint)
- Replacement of ChromaDB with Weaviate (prod consideration, not MVP)
- Neo4j migration from in-memory Cytoscape (prod consideration)
- Demo screen capture for Friday
- Multi-theme system (dark/high-contrast variants beyond the token layer)
