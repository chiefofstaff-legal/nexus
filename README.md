# nexus

**Voice-first AI for law firms.** Open-source reference implementation of the [donna-legal](https://github.com/chiefofstaff-legal/donna) substrate. Production deployment: [free.donnaoss.com](https://free.donnaoss.com).

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%20v3-b35e15.svg)](LICENSE)
[![Status: alpha](https://img.shields.io/badge/Status-alpha-grey.svg)](#status)
[![Substrate: donna-legal](https://img.shields.io/badge/Substrate-donna--legal-b35e15.svg)](https://github.com/chiefofstaff-legal/donna)

> *"DONNA handles the work around the work — so judgement stays with the lawyer."*

This is the running MVP at [free.donnaoss.com](https://free.donnaoss.com). The lawyer speaks the intent — *"send Sarah the M&A precedent we used for Dubrovnik, ask her to redline by Tuesday, copy Marcus when she replies"* — and nexus routes it: to the right person, the right system, the right tool. Every delegated decision is captured as a structured **IDR (Intent Decision Record)** signed with HMAC-SHA256 per the open [happi/1.1 protocol](https://github.com/chiefofstaff-legal/donna), chained, replayable, exportable in regulator-ready formats.

## Inverted Red Hat boundary

This repo is the **open surface**. The proprietary NEXUS-tier engine (sensitivity-aware multi-provider routing + council deliberation + IDR-engine integration) lives in a separate private package — [CodeTonight-SA/nexus-engine](https://github.com/CodeTonight-SA/nexus-engine) — that this repo optionally imports at runtime.

| What ships open (this repo, AGPL-3.0) | What ships proprietary (`nexus-engine`) |
|---|---|
| Full UI (Next.js 16 + React 19) | LLM router (`LLMRouter`) |
| FastAPI backend (60+ endpoints) | Sensitivity classifier (FADP-aware council) |
| happi/1.1 IDR chain (`backend/core/idr_happi.py`) | Council deliberation pattern |
| Audit chain (HMAC-SHA256) | PII detection (dual-layer regex + NER) |
| Document processing (PyMuPDF4LLM + Claude Haiku Vision) | Sensitivity scorer |
| Embeddings + semantic search (MiniLM + ChromaDB) | |
| Entity extraction (spaCy NER + Cytoscape.js graph) | |
| SOP engine + drafting + matters + redaction (24 services) | |
| Docker Compose self-host stack | |

A firm can clone this repository, run it on its own infrastructure, point it at a local model, and never touch our servers. The proprietary engine is **optional** — the OSS clone runs with single-model routing.

> **Status v0.1.0-alpha** — extracted-but-not-yet-pluggable. The 5 proprietary modules have been removed from `backend/services/`; the public clone needs a v0.2.0 fallback router (`llm_router_simple.py`) before the OSS-only path runs end-to-end. Until then, the running deployment at [free.donnaoss.com](https://free.donnaoss.com) imports nexus-engine; this repo demonstrates the architectural boundary and the open protocol surface (happi/1.1, PROBAT.md, audit chain).

## What you can verify today

Even before the v0.2.0 fallback router lands, the **open protocol substrate** verifies end-to-end:

```bash
# Clone the OSS donna-legal substrate that defines happi/1.1
git clone https://github.com/chiefofstaff-legal/donna.git ~/donna-legal

# Verify this repo's PROBAT.md chain using the OSS verifier
export DONNA_NOTARISE_KEY=nexus-public-demo-key-2026-05-11
python3 ~/donna-legal/bin/notarise verify --chain PROBAT.md
# expected: OK: 3 record(s) verified (HMAC-SHA256)
```

That single command demonstrates the load-bearing claim: **nexus emits records that any happi/1.1 verifier can validate.** The OSS protocol and the NEXUS-tier engine speak the same wire format.

## Architecture

```
nexus/                              ◀── this repo (AGPL-3.0)
├── frontend/                       Next.js 16 + React 19 + Tailwind 4
│   └── src/app/(main)/             14 feature pages
├── backend/                        FastAPI + Python 3.12
│   ├── app/                        Routes, middleware, lifespan
│   ├── core/
│   │   ├── audit_chain.py          HMAC-SHA256 generic audit chain
│   │   ├── idr_happi.py            happi/1.1 IDR wire format
│   │   ├── idr_store.py            Dual-write store (legacy + happi)
│   │   └── intent_decision_record.py
│   └── services/                   27 OSS services (document, search, NER, SOPs, …)
├── deploy/                         Docker Compose self-host stack
├── PROBAT.md                       Self-notarising 3-entry chain demo
└── LICENSE                         AGPL-3.0

CodeTonight-SA/nexus-engine/        ◀── private companion (proprietary)
└── nexus_engine/
    ├── router.py                   LLMRouter
    ├── classifier.py               SensitivityClassifier
    ├── council.py                  Council deliberation
    ├── pii.py                      PII detection
    └── scorer.py                   Sensitivity scoring

chiefofstaff-legal/donna/           ◀── OSS substrate (AGPL-3.0)
├── bin/notarise                    happi/1.1 protocol reference
├── mcp-servers/donna/              MCP scaffolding
└── skills/donna/                   Voice + skill files
```

## Self-host (v0.2.0 — coming once `llm_router_simple.py` lands)

```bash
git clone https://github.com/chiefofstaff-legal/nexus.git
cd nexus
cp .env.example .env  # fill in GROQ_API_KEY at minimum
cd deploy && docker compose up -d
# → http://localhost:3000
```

## License

[AGPL-3.0](LICENSE). The proprietary NEXUS-tier engine is licensed separately under terms documented at [chiefofstaff.pro](https://chiefofstaff.pro). Open surface, proprietary substrate — the **Inverted Red Hat** model.

## Status

- **2026-05-11** — v0.1.0-alpha. Initial OSS extraction from `CodeTonight-SA/nexus-poc`. happi/1.1 IDR chain proven cross-tool verifiable via donna-legal/bin/notarise. 5 proprietary services extracted to private nexus-engine; OSS-only fallback router pending v0.2.0.
- **2026-05-11** — Sprint A + B shipped to production. Live at [free.donnaoss.com](https://free.donnaoss.com).

## Companion repositories

- [chiefofstaff-legal/donna](https://github.com/chiefofstaff-legal/donna) — OSS protocol substrate (AGPL-3.0)
- [CodeTonight-SA/nexus-engine](https://github.com/CodeTonight-SA/nexus-engine) — proprietary engine (private)
