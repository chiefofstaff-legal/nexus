# Sprint C — Engine Extraction + Public OSS Push

**Author:** V>> (LaurieScheepers / architext1)
**Drafted:** 2026-05-11
**Status:** HALT — pending V>> approval before any irreversible public push
**Branch:** `feat/sprint-c-oss-prep`

## Goal

Complete the Option X consolidation by making `nexus-poc` the canonical OSS reference implementation of the donna-legal substrate, while preserving the proprietary NEXUS engine pieces.

Concrete deliverables:

1. `github.com/chiefofstaff-legal/nexus` — new public repo under AGPL-3.0, holding the OSS-able surface of nexus-poc.
2. `nexus_engine` — private Python package (CodeTonight-SA) holding the proprietary pieces, imported by nexus-poc at runtime.
3. `donna-legal/README.md` — updated to link nexus as the "first reference implementation".
4. `free.donnaoss.com` — Vercel deployment of the public nexus repo (already wired in Sprint A).

## Inverted Red Hat boundary

Per `donna-legal/README.md`: **"open surface, proprietary substrate"**. The Sprint B happi/1.1 alignment already separates protocol from engine. Sprint C draws the same line at the module level.

| Module | Decision | Rationale |
|---|---|---|
| `frontend/` (all UI) | **OSS** | Marketing surface; brand consistency requires it to be visible. Demo password gates access. |
| `backend/app/` (routes, FastAPI app) | **OSS** | API contract is part of the protocol surface. |
| `backend/core/audit_chain.py` | **OSS** | Generic HMAC chain. Algorithm is textbook-public. |
| `backend/core/idr_happi.py` | **OSS** | OSS happi/1.1 wire format (Sprint B). |
| `backend/core/idr_store.py` | **OSS** | Storage layer; no proprietary logic. |
| `backend/core/intent_decision_record.py` | **OSS** | Schema. The richness of IDR fields is a public protocol extension, not IP. |
| `backend/core/persistence.py` | **OSS** | SQLite store; commodity. |
| `backend/services/document_processor.py` | **OSS** | PyMuPDF4LLM wrapper; vendor SDK use, no novel IP. |
| `backend/services/embedding_service.py` | **OSS** | MiniLM + ChromaDB wrapper. |
| `backend/services/entity_extractor.py` | **OSS** | spaCy NER wrapper. |
| `backend/services/sop_engine.py` | **OSS** | YAML-driven workflow engine. |
| `backend/services/drafting_service.py` | **OSS** | Template-based drafting. |
| `backend/services/matter_service.py` etc. | **OSS** | CRUD on SQLite. |
| `backend/services/redaction.py` | **OSS** | Regex floor + entity-driven masking; well-known pattern. |
| `backend/services/llm_router.py` | **PROPRIETARY** → extract to `nexus_engine` | Sensitivity-aware routing across multiple providers with cost optimisation. NEXUS-tier value. |
| `backend/services/sensitivity_classifier.py` | **PROPRIETARY** → extract | Swiss FADP-aware council classifier. The "judgement engine". |
| `backend/services/council.py` | **PROPRIETARY** → extract | Multi-model deliberation pattern. |
| `backend/services/pii_detector.py` | **PROPRIETARY** → extract | Dual-layer regex + NER PII detection (part of council). |
| `backend/services/sensitivity_scorer.py` | **PROPRIETARY** → extract | Scoring heuristics that feed the router. |
| `deploy/` | **OSS** | Docker Compose stack for self-hosting. |
| `test_corpus/` | **OSS** (after sanitisation) | Sample legal documents — must be either public-domain or sanitised before push. |

## Engine extraction strategy

Create a separate **private** Python package `nexus_engine` at `github.com/CodeTonight-SA/nexus-engine` containing:

```
nexus_engine/
├── pyproject.toml          (private PyPI or git URL install)
├── nexus_engine/
│   ├── __init__.py
│   ├── router.py           (formerly services/llm_router.py)
│   ├── classifier.py       (formerly services/sensitivity_classifier.py)
│   ├── council.py          (formerly services/council.py)
│   ├── pii.py              (formerly services/pii_detector.py)
│   └── scorer.py           (formerly services/sensitivity_scorer.py)
└── tests/
```

Public nexus-poc imports:

```python
# requirements.txt — public version
# Internal CodeTonight tooling resolves this from private GitHub:
nexus-engine @ git+https://github.com/CodeTonight-SA/nexus-engine.git@v0.1.0
```

External self-hosters who don't have the private package see a **fallback path**: `services/llm_router_simple.py` (NEW, OSS) that does single-model routing with no sensitivity classification. The app still functions; the NEXUS tier just isn't active.

This satisfies all three of V>>'s constraints:
- **(a) OSS has no proprietary IP** — `nexus_engine` is private; public repo has only the protocol + UI + commodity services.
- **(b) Self-hostable** — fallback router lets external firms run the full UI on their own infra without the proprietary engine.
- **(c) First implementation** — the public `nexus` repo IS the running MVP at `free.donnaoss.com`; it just runs with the NEXUS engine layered on for hosted users.

## OSS-push audit (this PR completes most of it)

| Item | Status |
|---|---|
| LICENSE file (AGPL-3.0) | ✓ Added in this PR |
| Test fixtures sanitised (no real client/employee names) | ✓ Done in this PR (`test_redaction.py`, `test_idr_review.py`) |
| `.gitignore` covers data/, .env, signing keys | ✓ Already correct |
| No API keys / tokens in source | ✓ Audited clean |
| README.md updated for OSS positioning | ⚠ Pending (Sprint C wave 2 below) |
| CONTRIBUTING.md | ⚠ Pending |
| SECURITY.md | ⚠ Pending |
| Code of Conduct | ⚠ Pending (optional but good) |

## Execution plan (post-approval)

Once V>> approves the public push, the irreversible steps are:

1. **Create private `nexus-engine` repo** at `github.com/CodeTonight-SA/nexus-engine`. Move the 5 proprietary services into it. Add `pyproject.toml`. Tag v0.1.0.
2. **Update `nexus-poc/backend/requirements.txt`** to import nexus_engine (private).
3. **Add fallback router** `services/llm_router_simple.py` for self-hosters without the engine.
4. **Create public `nexus` repo** at `github.com/chiefofstaff-legal/nexus`. Push current nexus-poc state (minus the now-extracted engine) as `architext1`. Tag v0.1.0-alpha.
5. **Mirror to private repo**: keep `github.com/CodeTonight-SA/nexus-poc` as a fork that adds the engine import (production deploy target). Or: deprecate nexus-poc and switch deploy target to public nexus + private engine.
6. **Update donna-legal/README.md**: add "Production reference implementation: github.com/chiefofstaff-legal/nexus".
7. **Update Vercel project** to deploy from `chiefofstaff-legal/nexus` repo instead of CodeTonight-SA/nexus-poc.

## HALT criteria

This PR (Sprint C prep) is **safe to merge**. It adds LICENSE + sanitises test fixtures + documents the plan. No public push, no engine extraction.

The IRREVERSIBLE steps above happen only after V>> explicit approval, since:

- Open-sourcing is **one-way** — once pushed, mirrored forever.
- Extracting the engine to a private package adds a CI/CD dependency on private GitHub access.
- Switching Vercel deploy target to the public repo affects the production URL.

## Open questions for V>>

1. **AGPL-3.0 vs Apache-2.0 for nexus public repo?** donna-legal is AGPL. Apache-2.0 would allow more permissive adoption (proprietary forks). Recommend AGPL for narrative consistency.
2. **Should `nexus-engine` be findable (private repo names visible) or completely hidden (organisation-level secret)?** Default: private but findable, so the architecture story makes sense.
3. **Sanitisation level for `test_corpus/`?** The sample legal docs may have identifying details. Should we replace with fully synthetic documents?
4. **Brand for the public repo:** `nexus`, `nexus-mvp`, `chiefofstaff-nexus`? Recommendation: `nexus`.

## Falsification criteria (for the strategic move)

This consolidation succeeds iff:

1. `free.donnaoss.com` runs the same code as `github.com/chiefofstaff-legal/nexus` (no surprise drift).
2. A third party can clone the public repo + `docker compose up -d` and have a working MVP within 10 minutes.
3. Donna OSS narrative survives the move (no client confusion about what's free vs paid).
4. Within 90 days of public launch, at least 5 unique cloners of the public repo (GitHub traffic stats).

If any of these fails: the consolidation was the wrong move and we revert to dual-URL (Option B).
