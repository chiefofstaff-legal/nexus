# NEXUS POC — Deployment

Reproducible Docker Compose stack for the NEXUS Phase 1 POC.

## Prerequisites

- Docker 24+ and Docker Compose v2
- 8 GB free disk for the ollama model cache
- The Anthropic and Groq API keys
- An Azure AD app registration with `Mail.Send` and `Calendars.ReadWrite`
  application permissions (for the W6 email + calendar integration)

## Configure

1. Copy the example env file and fill in real values:
   ```
   cp deploy/.env.example deploy/.env
   $EDITOR deploy/.env
   ```
2. Never commit `deploy/.env` — it contains secrets.

## Start the stack

```
cd deploy
docker compose up -d
```

The first start will:
- Build `nexus-backend` (Python 3.12-slim + dependencies, ~3 min)
- Build `nexus-frontend` (Next.js 16 production build, ~2 min)
- Pull `ollama/ollama:latest` and provision a persistent volume

After it finishes:
- Backend API: <http://localhost:8000>
- Frontend: <http://localhost:3000>
- Ollama: <http://localhost:11434>

## Verify

```
curl -fsS http://localhost:8000/api/health
```

The frontend's matter dashboard should be browsable at `/matters`.

## Public URL routing (production VPS)

For the live demo, the VPS routes:

| Hostname                       | Service          | Port |
|-------------------------------|------------------|------|
| `nexus-staging.grip-web.com`  | nexus-frontend   | 3201 |
| `api.grip-web.com` (HAPPI)    | other services   | n/a  |

Demo password for the staging site: see operational-runbook.md.

## Update + redeploy

```
git pull origin main
cd deploy
docker compose up -d --build nexus-backend nexus-frontend
```

The ollama service does not need a rebuild on app updates.

## Tear down (preserves volumes)

```
docker compose down
```

Add `--volumes` to also drop persistent SQLite + ollama data — only do this in dev.

## Troubleshooting

- **Port already in use**: change the port mappings in `docker-compose.yml`.
- **MS Graph 401**: regenerate the client secret in Azure and update `.env`.
- **Frontend build OOM**: build the frontend image with `--memory=4g`.
