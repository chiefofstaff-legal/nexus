# Changelog

All notable changes to ChiefOfStaff.pro (NEXUS Engine) are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Fixed

- **Voice multilingual autodetect** — the `/api/voice/transcribe` endpoint now
  accepts an optional `?lang=` query parameter (e.g. `?lang=de`). When omitted,
  Whisper uses automatic language detection instead of always defaulting to
  English. Swiss lawyers dictating in German, French, or Italian no longer
  receive English-only transcriptions. Two regression tests verify that (a) a
  `?lang=de` request forwards `language="de"` to Groq exactly, and (b) omitting
  `?lang` passes `language=None` to enable Whisper's multilingual detection.

---

## [0.2.0] — 2026-04-22

### Added

- **Voice transcript persistence** — raw Groq Whisper transcriptions are now
  stored on every time entry and delegated task. A click-through detail view
  on time entries shows the transcript, AI summary, duration, and CHF value.
  Task Kanban cards have an expandable transcript panel. All transcripts are
  editable post-capture to correct STT errors (acronyms, mishears).
- **Drafting voice mic** — the AI drafting page now has a Groq Whisper mic
  button; lawyers can dictate draft instructions without typing. The original
  dictated instruction is preserved alongside each generated draft.
- **Multi-intent voice drafting** — one dictation can request multiple
  documents (e.g. "draft an NDA and a cover letter"); the AI detects multiple
  intents and generates each draft in a single call.
- **SharePoint Graph API integration** — real Microsoft Graph connection
  replacing the stub implementation; documents sync from live SharePoint
  document libraries.
- **Semantic search with source citations** — search results now include the
  source document name, page reference, and matching excerpt for each hit.
- **Voice task assignee extraction** — spaCy NER pipeline improved with a
  roster-supplement pass to reliably resolve short first names ("Mia",
  "Fabio") and phonetic near-misses produced by Whisper.
- **Animated ingestion progress + folder picker** — SSE progress bar with
  per-file status animation and a native OS folder browser for bulk ingestion.

### Fixed

- **Task delegation double-create** — `POST /api/tasks/delegate` was storing
  the task immediately; `POST /api/tasks/create` (confirm step) stored it
  again, producing 2 tasks per delegation. Delegate is now parse-only;
  `/create` is the sole storage point. Regression test added (TDD).
- **Entity graph crash on large corpora** — Cytoscape renderer capped at 200
  nodes; IDR audit panel restored after a regression in the same wave.
- **Groq credential guard** — missing API key now returns 503 with a
  diagnostic message instead of an unhandled 500.
- **SharePoint export endpoint missing** — `sharepointExport` was called by
  the UI but not wired in the API client.
- **Drafting SDK errors** — Anthropic client errors now surface as 502 with
  a user-readable message instead of a raw exception.
- **Mobile horizontal scroll** — search page no longer overflows on small
  screens; flex layout corrected, input min-width set, hit text word-wrapped.
- **Null timestamp on time entries** — "INVALID DATE" no longer rendered when
  a time entry carries a null or unparseable timestamp.

### Changed

- **STT backend** — all voice pages migrated from Web Speech API (silently
  blocked by Brave and Firefox privacy shields) to Groq Whisper large-v3 via
  MediaRecorder + server-side transcription.

### Quality

- 8 new backend tests: voice transcription, task NER, semantic search,
  double-create regression guard.
- Production hardening: sidebar sticky positioning, footer cleanup, computed
  field aliasing (`total_value_chf`), CORS origin tightening.

---

## [0.1.0] — 2026-04-19

### Added

- Document ingestion with auto-classification (8 legal document types)
- LLM sensitivity routing: Groq (public) → Claude (caution) → Ollama (confidential)
- FADP-aware council classifier with HMAC-SHA256 tamper-evident audit chain
- Entity knowledge graph (spaCy NER + Cytoscape.js force-directed layout)
- SOP step-by-step execution engine (YAML-defined gated workflows)
- Semantic search over ingested corpus (MiniLM-L6-v2 + ChromaDB)
- Intent Decision Records (IDR) with Popper falsification criterion
- Voice time capture (speak billable hours, Claude Haiku parses to structured entry)
- Voice task delegation (speak a task, NER extracts assignee + deadline + matter)
- AI drafting from templates (7 legal document types, British English, Swiss law)
- SharePoint stub integration (document listing, sync, export placeholders)
- Password-gated demo at nexus-staging.grip-web.com

---

[Unreleased]: https://github.com/CodeTonight-SA/nexus-poc/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/CodeTonight-SA/nexus-poc/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/CodeTonight-SA/nexus-poc/releases/tag/v0.1.0
