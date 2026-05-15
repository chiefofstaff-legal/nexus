# ChiefOfStaff.pro — NEXUS Engine POC

Voice-first AI platform for Swiss law firms. Document management, entity analysis,
sensitivity-based LLM routing, and workflow automation.

## Architecture

```
backend/          FastAPI (Python) — document processing, LLM routing, entity extraction
frontend/         Next.js 16 (TypeScript) — dashboard, entity graph, SOP interface
docs/             Technical proposal and architecture diagrams
test_corpus/      Sample legal documents for testing
```

## Quick Start

### Backend
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8100
```

### Frontend
```bash
cd frontend
npm run dev  # http://localhost:3100
```

### First-time setup
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
cp ../.env.example ../.env  # Fill in API keys (optional — heuristic fallbacks work without)
```

## Ports

| Service | Port |
|---------|------|
| Frontend (Next.js) | 3100 |
| Backend (FastAPI) | 8100 |
| Ollama (on-prem LLM) | 11434 |

## Prototypes

| # | Prototype | Status |
|---|-----------|--------|
| 1 | Document Ingestion + Auto Filing | Complete |
| 2 | LLM Orchestration Agent | Complete |
| 3 | Entity Graph Visualisation | Complete |
| 4 | SOP Agent | Complete |
