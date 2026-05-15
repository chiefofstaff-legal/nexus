# Leandro Phase 1 — W3-W6 Sprint Preplan

**Author:** Lourens Cornelius Scheepers (V>>)
**Drafted:** 2026-04-29 (handoff at end of session that shipped PR #35)
**Predecessor PR:** #35 (`ac1dd22`) — W1 persistence + W2 Matter entity + UI matter dashboard, MERGED + DEPLOYED to https://nexus-staging.grip-web.com
**Validation source:** `/Users/lauriescheepers/.claude/drafts/leandro-phase1-validation-2026-04-29.md`
**Predecessor plan:** `plans/leandro-phase1-implementation.md` (W1 + W2 sprint, completed)

## Sprint identity

| Property | Value |
|----------|-------|
| Goal | Close remaining gaps from validation matrix so Craig can sign Leandro at CHF 200/month with confidence |
| Scope | W3 (roster + cost meter), W4 (summary service + snapshots + filters), W5-backend (hybrid search + DE multilingual + voice DE), W6 (email + calendar + IaC + runbook + tier vocabulary + AbaPlato stub) |
| Branch | `feat/leandro-phase1-w3-w6` |
| Branch shape | Skip checkout, push HEAD per Gate O documented mitigation (`feedback_gate_o_external_repos.md`) |
| Method | `/auto wave-mode 5h "Phase 1 W3-W6"` (or `/sprint` for single-PR shape) |
| Hypothesis count | 4 (H226–H229), one per wave |
| Effort estimate | ~30 dev days compressed; expect 1-3 waves per session, multi-session sprint |

## Inherited foundation (from PR #35)

These exist on `main` and the new sprint builds on them — DO NOT re-implement:

- **Persistence layer**: `backend/core/persistence.py` (stdlib SQLite + WAL + lazy schema). Tables: `time_entries`, `tasks`, `matters`, `matter_documents`. Use `get_connection()` and `init_schema()` for any new tables.
- **Matter entity**: `backend/models/matter.py` (Matter + MatterDocument), `backend/services/matter_service.py` (MatterStore CRUD with ISP-split documents sub-object). `/api/matters` routes with seven endpoints. The `matter_id` FK is already on `TimeEntry` and `Task` (alongside legacy `matter` string).
- **Frontend matter dashboard**: `frontend/src/app/(main)/matters/` (list, detail, create dialog, document membership). API client at `_lib/matters-client.ts`. 49 frontend tests passing.
- **Test infrastructure**: 205 backend tests passing; `tests/test_persistence.py` and `tests/test_matter.py` are reference patterns for new SQLite-backed services.

## Wave plan

### W3 — Roster externalisation + ingestion cost meter (FAST, depth 1, ~1 dev day)

**Hypothesis H226**: After W3, the assignee roster is configurable per tenant via a YAML file (no code change to onboard a new firm), AND every ingestion run logs its token cost to a JSONL audit file.

**Falsification**: roster still hardcoded; ingestion cost still untracked; or YAML schema requires backend code changes per tenant.

**Files to touch**:
- `backend/services/task_manager.py:40` — replace hardcoded `KNOWN_ASSIGNEES` tuple with loader from `config/roster.yaml`. The alias map at line 44 (`_ASSIGNEE_ALIASES`) should also externalise; consider `config/roster.yaml` shape:
  ```yaml
  assignees:
    - canonical: "Andre"
      aliases: [andray, andré, andrew, andrei]
    - canonical: "Arnold"
      ...
  ```
- NEW `backend/core/roster_config.py` — load + validate YAML, return `(KNOWN_ASSIGNEES, _ASSIGNEE_ALIASES)`.
- NEW `config/roster.yaml` — current NEXUS team as default; document that each Leandro tenant gets their own copy.
- NEW `backend/services/ingestion_cost.py` — track tokens per Claude classification + embedding call. Persist to `data/ingestion-costs.jsonl` (gitignored, per existing `data/` rule).
- `backend/services/document_processor.py` — wrap Claude calls to record cost.
- NEW `backend/tests/test_roster_config.py` (3+ tests) and `backend/tests/test_ingestion_cost.py` (3+ tests).

**Goodhart guard**: roster test must verify `_match_known_assignee` still resolves "Andray" → "Andre" after externalisation; cost meter test must verify cost > 0 for non-trivial input.

### W4 — SummaryService + SummarySnapshot + draft/media/version filters (CAREFUL, depth 2, ~5 dev days)

**Hypothesis H227**: After W4, every matter has an automated summary that regenerates whenever a new document is associated; previous versions are retrievable by `(matter_id, version_id)`; the ingestion pipeline filters out drafts, media files, and superseded versions before indexing.

**Falsification**: summary doesn't regenerate on doc-add; old snapshots not retrievable; filters miss obvious draft markers (`_draft`, `v1`, `.mp4`).

**Files to touch**:
- NEW `backend/models/summary.py` — `SummarySnapshot` Pydantic (matter_id, version_id, content, created_at, source_citations). Reuse the v0.2.0 source-citation pattern.
- NEW `backend/services/summary_service.py` — `SummaryStore` SQLite-backed (mirror `MatterStore` shape); `regenerate(matter_id) -> SummarySnapshot` calls Claude with all matter docs.
- `backend/core/persistence.py` — add `summary_snapshots` table to `_SCHEMA_DDL`:
  ```sql
  CREATE TABLE IF NOT EXISTS summary_snapshots (
      matter_id TEXT NOT NULL,
      version_id INTEGER NOT NULL,
      content TEXT NOT NULL,
      source_citations TEXT NOT NULL,  -- JSON array
      created_at TEXT NOT NULL,
      PRIMARY KEY (matter_id, version_id),
      FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
  );
  ```
- `backend/services/document_processor.py` — add `_should_skip(filename)` heuristic: skip `*.mp4`, `*.mov`, `*.avi`, files containing `_draft` or `_v[0-9]+_old` or `_superseded`. Also size-cap already at `routes.py:81` (20 MB).
- `backend/app/routes.py` — wire ingestion-completion hook to enqueue summary regeneration; add `/api/matters/{id}/summary` (current) and `/api/matters/{id}/summary/{version_id}` (historical).
- `frontend/src/app/(main)/matters/[id]/page.tsx` — add summary section with version dropdown.
- NEW `backend/tests/test_summary_service.py` (5+ tests including snapshot retrieval).
- NEW `backend/tests/test_ingestion_filters.py` (5+ tests covering drafts, media, supersession).

**Dependency**: depends on W3 cost meter (each summary regeneration is a Claude call; cost should be logged).

**Goodhart guard**: snapshot test must verify content actually differs between version_id=1 and version_id=2 after a doc is added (not just that two rows exist).

### W5 — Hybrid search + DE multilingual + voice DE (CAREFUL, depth 3, ~5 dev days)

**Hypothesis H228**: After W5, the search interface supports keyword + semantic + hybrid (RRF) modes; German queries return German documents with comparable recall to English-on-English; the voice transcription endpoint detects language instead of being hard-locked to English.

**Falsification**: keyword search missing or returns wrong matches; hybrid scoring not better than either alone on a benchmark; DE→DE recall < 0.7 of EN→EN baseline; voice still locked to English.

**Files to touch**:
- NEW `backend/services/keyword_search.py` — SQLite FTS5 over chunk text + filename. Schema additions in `persistence.py`:
  ```sql
  CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
      doc_id, chunk_index, filename, content,
      tokenize = 'porter unicode61'
  );
  ```
- `backend/services/embedding_service.py:105-137` — add `hybrid_search(query, alpha=0.5)` combining `keyword_search.search(query)` and existing semantic search via Reciprocal Rank Fusion (`score = sum(1 / (k + rank_i))` for k=60 default).
- `backend/services/embedding_service.py` — replace `all-MiniLM-L6-v2` with `paraphrase-multilingual-MiniLM-L12-v2` (50 supported languages including DE). REQUIRES one-time corpus re-index — add `scripts/reindex_corpus.py` that drops existing embeddings and re-embeds.
- `backend/app/routes.py:1212` — drop `language="en"` Whisper lock; use `language=None` for autodetect, OR add `?lang=` query param.
- `backend/app/routes.py:493-508` — `/api/documents/search` accepts `mode=keyword|semantic|hybrid` query param.
- `frontend/src/app/(main)/search/page.tsx:163-176` — add mode toggle in UI.
- NEW `backend/tests/test_keyword_search.py` (4+ tests).
- NEW `backend/tests/test_hybrid_search.py` (3+ tests including RRF math sanity check).
- NEW `backend/tests/test_multilingual_search.py` (use a synthetic DE corpus of 5 documents; assert DE query returns DE doc at top-3).

**Goodhart guard**: hybrid test must show RRF beats either alone on at least one query; multilingual test must use ACTUAL German legal vocabulary (e.g. `Bundesgericht`, `Strafgesetzbuch`), not just German cognates of English words.

**Dependency**: this wave is heavier than W3/W4 — embedding model swap requires re-index of any test fixtures + production corpus.

### W6 — Email + calendar + IaC + runbook + tier vocab + AbaPlato stub (CAREFUL, depth 5+, ~10 dev days, bg-dispatch Shape A)

**Hypothesis H229**: After W6, lawyers can send emails and create calendar meetings via voice; the VPS deploy is reproducible from a Docker Compose file (no manual runbook); the document classifier recognises Swiss legal tier vocabulary (DEC/RSE/RSG with documented placeholders); time entries can be exported to AbaPlato CSV.

**Falsification**: voice email or calendar absent; deploy still requires manual runbook; classifier doesn't recognise tier vocabulary; AbaPlato export missing or malformed CSV.

**This wave is bg-dispatch Shape A territory** — the items don't share files, so spawn 6+ parallel agents:

#### Agent W6-A: Email integration (~3 dev days)
- NEW `backend/services/email_service.py` — MS Graph mail wrapper (use `msgraph-sdk-python` or direct REST). Document Microsoft authentication setup in docstring.
- NEW `backend/services/voice_to_email.py` — Claude Haiku parses transcript into `{recipient, subject, body}`.
- `backend/app/routes.py` — `POST /api/emails/voice` route.
- `frontend/src/app/(main)/email/` — voice mic + draft preview UI.
- NEW `backend/tests/test_email_service.py` (mock MS Graph) and `test_voice_to_email.py`.

#### Agent W6-B: Calendar integration (~3 dev days)
- NEW `backend/services/calendar_service.py` — MS Graph calendar wrapper.
- NEW `backend/services/voice_to_event.py` — Claude Haiku parses transcript into `{title, start, end, attendees, location}`.
- `backend/app/routes.py` — `POST /api/calendar/voice` route.
- `frontend/src/app/(main)/calendar/` — voice mic + event preview UI.
- NEW tests.

#### Agent W6-C: Task notifications (~1 dev day)
- `backend/services/task_manager.py` — after `delegate_from_transcript`, post to Slack DM or send MS Graph email to assignee. Configurable via `config/notification-channels.yaml`.
- NEW `backend/tests/test_task_notifications.py`.

#### Agent W6-D: Docker Compose IaC (~2 dev days)
- NEW `deploy/docker-compose.yml` — services: nexus-backend, nexus-frontend, ollama (for confidential routing path).
- NEW `deploy/.env.example` — all required env vars documented.
- NEW `deploy/Dockerfile.backend` and `deploy/Dockerfile.frontend`.
- NEW `deploy/README.md` — `docker compose up -d` reproduces the stack on any Linux VPS.

#### Agent W6-E: Operational runbook (~1 dev day)
- NEW `docs/operational-runbook.md` — covers deploy, monitoring, backup/restore, incident response, on-call rotation.
- NEW `docs/sla.md` — fully-managed SLA template (5 nines, 24-hour incident response, etc.) — **REQUIRES Leandro clarification before pricing**.

#### Agent W6-F: DEC/RSE/RSG schema extension (~1 dev day, BLOCKED PARTIAL)
- `backend/models/document.py:11-19` — extend `DocumentType` enum with three new values:
  ```python
  class DocumentType(str, Enum):
      ...existing 8 values...
      DECISION = "dec"        # TODO: Leandro to confirm DEC = Entscheidung/Décision/Decisione
      REGULATION = "rse"      # TODO: Leandro to confirm RSE = Recueil Systématique?
      JUDGMENT = "rsg"        # TODO: Leandro to confirm RSG = Recueil Systématique Geltend?
  ```
- `backend/services/document_processor.py:241-260` — extend classifier prompt with the three new types; mark TODO.
- Document the placeholder semantics in code comments + the proposal validation matrix.

#### Agent W6-G: AbaPlato CSV export stub (~1 dev day)
- NEW `backend/services/abaplato_export.py` — function `export_time_entries_to_csv(entries: list[TimeEntry]) -> str`.
- Documented assumption (CSV columns based on common Swiss timesheet shape):
  ```
  date,duration_minutes,matter,description,billable,hourly_rate_chf,total_chf
  ```
- `backend/app/routes.py` — `GET /api/time/export?format=abaplato` returns CSV.
- NEW `backend/tests/test_abaplato_export.py` — verify CSV shape, escaping, headers.
- Comment block flags TODO: confirm actual AbaPlato import schema with Leandro.

## Hypothesis registration commands

At sprint start, register all four:

```bash
PYTHONPATH=$HOME/.claude $HOME/.claude/venv/bin/python $HOME/.claude/lib/hypothesis_engine.py register \
  --pr 0 --claim "After W3, assignee roster externalised to YAML and ingestion cost logged" \
  --metric "pytest test_roster_config.py + test_ingestion_cost.py pass" \
  --prediction "Roster swap requires no code change; cost > 0 for typical doc" \
  --deadline "2026-05-06"
# Repeat for H227, H228, H229 with appropriate claims and deadlines.
```

## Items blocked on Leandro clarification

Implement against documented assumptions, mark TODO clearly, send clarification request via Craig:

| Item | Blocking what | Documented assumption |
|------|---------------|------------------------|
| AbaPlato actual CSV/XML schema | W6-G stub completeness | Standard timesheet CSV: date,duration_minutes,matter,description,billable,hourly_rate_chf,total_chf |
| RSE / RSG actual definitions | W6-F enum semantic accuracy | RSE = Regulation/Recueil Systématique; RSG = Judgment/Recueil Systématique Geltend |
| Swiss-region hosting decision | "Swiss data sovereignty" claim in proposal | NOT a code item — operational/contractual; flag for Sonnet Advisors |
| Fully-managed SLA scope | "Zero IT overhead" claim and pricing | NOT a code item — needs SLA template + monitoring/oncall — flag for Sonnet Advisors |

The first two block specific code paths; the second two are pure operational decisions that Sonnet Advisors must make.

## Deploy protocol (just confirmed working 2026-04-29 19:37 UTC)

```bash
# From local machine:
ssh -o ConnectTimeout=10 -o BatchMode=yes root@100.80.130.33

# Once on VPS, switch to grip user:
su grip -s /bin/bash

# Deploy commands:
cd /home/grip/nexus-poc
git pull origin main
cd backend && source venv/bin/activate && pip install -q -r requirements.txt
cd ../frontend && npm ci --silent && npm run build
pm2 restart nexus-backend nexus-frontend
```

**Tailscale auth refresh** is periodically required — if SSH hangs, visit `https://login.tailscale.com/a/...` (URL appears in stderr).

## Test URL

> **https://nexus-staging.grip-web.com** — demo password: `nexus-craig-2026`

NOT `try.grip-web.com` (that's grip-server's sprint dashboard).

## Closeout protocol

After each wave (or at sprint end if `--no-ship`):
1. Verify all tests pass (`pytest backend/tests/` + `npm run test`)
2. Commit on `feat/leandro-phase1-w3-w6` (or local main with skip-checkout pattern)
3. Push: `git push origin HEAD:refs/heads/feat/leandro-phase1-w3-w6`
4. Open PR via `gh pr create --head feat/leandro-phase1-w3-w6 --base main`
5. Admin-merge once CI green: `gh pr merge <N> --squash --admin --delete-branch`
6. Sync local: `git fetch && git reset --hard origin/main`
7. Deploy via the protocol above
8. Verify `nexus-staging.grip-web.com` carries the new HEAD
9. Verify hypotheses (CONFIRMED/FALSIFIED/INCONCLUSIVE) via `lib/hypothesis_engine.py status`
10. Anti-drift Rule 11 4-line summary

## Falsification of this preplan

This preplan is wrong if:
- The hypothesis IDs (H226-H229) collide with concurrent work in another sprint (check `lib/hypothesis_engine.py status` before registering)
- The file path assumptions drift before next session (e.g. another PR refactors `task_manager.py` away from line 40)
- W3 (roster) turns out to depend on W4 (summary) due to a missed coupling
- The deploy command stops working because Tailscale rotates auth or the path changes again

Track: how much of the preplan is reusable vs needs re-discovery in the next session. Goal: ≥80% direct reuse.

## Anti-drift "What's Up Next" snapshot at handoff

- **Done**: PR #35 merged + deployed (W1+W2 + UI matter dashboard at https://nexus-staging.grip-web.com)
- **Remaining**: W3 (roster + cost), W4 (summary + filters), W5 (hybrid + DE), W6 (email + calendar + IaC + runbook + tier + AbaPlato) — this preplan
- **Open**: 4 items blocked on Leandro clarification; PR #35 hypotheses H224 + H225 deadline 2026-04-30 (auto-verify next session)
- **Next**: fresh session loads this preplan + `drafts/leandro-phase1-validation-2026-04-29.md` + `plans/leandro-phase1-implementation.md`; runs `/auto wave-mode 5h "Phase 1 W3-W6 from leandro-phase1-w3-w6.md"`; implements W3 + W4 + W5 sequentially, W6 via Shape A parallel agents
