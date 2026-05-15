# Leandro Phase 1 — Implementation Sprint

**Author:** Lourens Cornelius Scheepers (V>>)
**Drafted:** 2026-04-29
**Trigger:** Validation matrix at `~/.claude/drafts/leandro-phase1-validation-2026-04-29.md` identified 17 tractable gap-closure items + 4 blocked-on-Leandro items. Craig is preparing CHF 200/month proposal to Leandro.

## Sprint context

This plan layers on top of two prior nexus-poc sprints:

1. `plans/nexus-friday-sprint.md` (2026-04-14) — original 6-wave demo, complete + deployed
2. `plans/nexus-poc-to-mvp.md` (2026-04-15) — MVP hardening (H-MVP-1 through H-MVP-7), shipped to `try.grip-web.com`

The Leandro Phase 1 sprint is the third arc: take the live MVP and extend it to cover Craig's Phase 1 capability spec (A through E) at a level that lets him commit to CHF 200/month with confidence.

## Scope

**In scope (15 tractable items):**

- **W1** — Persistence migration: `TimeEntryStore` + `TaskStore` from in-memory list to SQLite (Capability B foundation)
- **W2** — `Matter` entity + `MatterDocument` membership table + `/api/matters` CRUD (Capability C+D foundation)
- **W3** *(deferred to follow-up sprint)* — Roster externalisation, cost meter, summary service, snapshots, draft filters, hybrid search, multilingual, voice email/calendar, IaC, runbook

**Out of scope (blocked on Leandro clarification):**

- AbaPlato CSV/XML schema — needs Leandro to share AbaPlato import format
- DEC/RSE/RSG vocabulary — needs Leandro to define Swiss tier abbreviations
- Swiss-soil VPS migration — operational decision, not code
- "Fully managed" SLA — operational decision, not code

## Why W1 + W2 only in this session

The validation matrix identifies 4-6 weeks of work (31-40 dev days). One ultrado session cannot ship that. The pragmatic move is to ship the two **foundational** waves that unblock everything else:

- **W1 persistence** — without it, every Capability B improvement is on quicksand (RAM-only stores lose data on restart, cannot be trusted for billing)
- **W2 Matter entity** — without it, Capabilities C (matter summary), D (selective 5-matter ingestion) cannot be built; "matter" is currently a free-text string

Waves 3 onwards need a fresh session and depend on W1 + W2 being merged first.

## Hypotheses (pre-registered via `lib/hypothesis_engine.py`)

### H300 — Time entries and tasks survive process restart
- **Claim**: After W1, restarting the FastAPI process preserves all time entries and tasks created in the previous session.
- **Metric**: integration test `pytest backend/tests/test_persistence.py::test_time_entries_survive_restart` passes; same for tasks.
- **Prediction**: 100% retention across restart for both stores.
- **Falsification**: any entry or task lost; or chain corruption detected after restart; or schema migration fails.
- **Deadline**: 2026-04-29 end-of-day.

### H301 — Matter entity is first-class and integrates with existing domain
- **Claim**: After W2, `Matter` exists as a SQLAlchemy model; `MatterDocument` join table associates documents with matters; `/api/matters` supports POST/GET/PATCH/DELETE; existing `matter_reference` strings on TimeEntry/Task migrate to `matter_id` foreign keys without data loss.
- **Metric**: `pytest backend/tests/test_matter.py` passes; manual test creates matter, ingests 3 docs against it, retrieves them via `/api/matters/{id}/documents`.
- **Prediction**: All assertions green; existing TimeEntry/Task records remain queryable post-migration.
- **Falsification**: any test fails; or migration loses data; or string-to-FK conversion causes orphaned records.
- **Deadline**: 2026-04-29 end-of-day.

## Wave plan

| Wave | Name | Precision | Budget | Branch | Hypothesis |
|------|------|-----------|--------|--------|------------|
| W1 | Persistence migration (SQLite) | FAST | 1.5 h | `feat/leandro-phase1-gap-closure` | H300 |
| W2 | Matter entity + membership | CAREFUL | 2 h | same branch | H301 |

Single feature branch, accumulated commits, single PR at end (sprint shape, not per-wave PRs — closer to /sprint than default /ultrado per-wave). Fits the autonomous-merge protocol better for this scope.

## Anti-patterns to avoid

- Do NOT skip IDR coverage for new persistence operations — every TimeEntry/Task save must continue writing an audit-chain entry (per H-MVP-3 from prior sprint).
- Do NOT introduce a separate database — reuse the existing audit-chain SQLite or add a sibling SQLite under `data/` (gitignored), not Postgres.
- Do NOT speculate on AbaPlato CSV format — that work is genuinely blocked.
- Do NOT modify `nexus-friday-sprint.md` or `nexus-poc-to-mvp.md` — those are historical records.

## Falsification of this plan

This plan is wrong if:
- The W1 + W2 changes break any existing test in `backend/tests/`
- The schema migration cannot be applied to the live VPS database without data loss
- The Matter entity foundation does not, in fact, unblock Capability C and D as the validation matrix claimed (i.e. a separate blocker emerges that wasn't visible at audit time)

Track outcome in commit messages and verify hypotheses at session end.

## Handoff for follow-up sprint

After this sprint ships W1 + W2:

1. Open follow-up sprint plan at `plans/leandro-phase1-implementation-w3-onwards.md`
2. Cover: roster + cost meter (W3), summary service + snapshots + draft filters (W4), hybrid search + multilingual + matter dashboard (W5), email + calendar + IaC + DEC/RSE/RSG schema + AbaPlato stub (W6)
3. Send Craig a clarification request for the 4 blocked items
4. Resume after Leandro responds OR proceed with documented assumptions
