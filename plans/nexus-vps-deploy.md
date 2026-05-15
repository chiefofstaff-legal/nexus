# Nexus POC → VPS Deployment Preplan

**Author:** Laurie Scheepers (V>>)
**Date drafted:** 2026-04-14 (during live meeting with Craig Miller)
**Execution window:** After the Craig meeting ends (same day or next business day)
**Driver memory:** `feedback_no_litellm.md` — direct SDKs only, never LiteLLM

## Goal (single sentence)

Move the Nexus POC from `localhost:3200` on V>>'s MacBook to the `grip-remote` VPS, and re-point the `try.grip-web.com` Cloudflare tunnel at it so Craig Miller (and any future prospect) can reach the POC from anywhere without V>>'s laptop being on.

## Decisions locked in (during the Craig meeting, 2026-04-14)

1. **Timing:** Prep + plan now; cutover executes after the meeting ends.
2. **GRIP Sprint Dashboard fate:** Retires its public URL. After cutover, it remains reachable *only* via Tailscale at `http://100.66.66.92:3847`. No new public subdomain.
3. **Confidential-path LLM:** Install Ollama + `gemma4:e4b` on the VPS itself. No Tailscale-back-to-MacBook fragility, no "disable confidential path" downgrade.

## Known facts (from session-context.md + `deploy/deploy.sh` + `start-demo.sh`)

| Fact | Source |
|---|---|
| VPS: `grip-remote`, Tailscale IP `100.66.66.92`, Ubuntu 24.04 | `rules/session-context.md` |
| SSH access: `root@grip-remote` via **Tailscale SSH only** (no raw ssh) | `deploy/deploy.sh:10`, `lib/gates/patterns.py:382` |
| VPS pm2 services: `grip-channel(:3101 STOPPED)`, `grip-server(:3847)`, `guild-dashboard(:3849)`, `tralala(:9999)`, `pm2-logrotate` | `rules/session-context.md` |
| VPS Docker services: `grip-metrics(:9100)`, `grip-grafana(:3000)`, `grip-gate(:9300)` | `rules/session-context.md` |
| `try.grip-web.com` currently routes to pm2 `grip-server` (port 3847 on VPS — confirmed by HTML title probe on 2026-04-14) | Live probe this session |
| Cloudflare tunnel is running on the VPS (not on MacBook — local cloudflared uninstalled) | `rules/session-context.md` |
| Nexus stack: FastAPI backend `:8100`, Next.js frontend (prod `next start`), Ollama `:11434`, ChromaDB (local file), spaCy `en_core_web_sm` | `~/nexus-poc/CLAUDE.md`, `start-demo.sh` |
| Nexus frontend uses `next.config.ts` rewrites to proxy `/api/*` and `/health` to `localhost:8100` | `frontend/next.config.ts` |
| Demo password: `NEXUS_DEMO_PASSWORD=nexus-craig-2026` | `frontend/.env.local:1` |

## Unknowns — MUST be verified once Tailscale is up

These are listed here so the execution session probes them *before* doing anything destructive. **Do not skip.**

| # | Unknown | How to check | Why it matters |
|---|---|---|---|
| U1 | VPS total RAM and current free RAM | `free -h` | `gemma4:e4b` needs ~5–6 GB RAM for inference; existing pm2/Docker stack already consumes some. If RAM is insufficient, fall back to the "disable confidential path on prod" option (revisit Q3 from the meeting). |
| U2 | VPS free disk on `/` (and `/var/lib/ollama`) | `df -h /` | `gemma4:e4b` manifest + weights ≈ 9 GB. Plus `node_modules` (~400 MB), Python venv + spaCy (~500 MB), ChromaDB data. Budget ≥ 12 GB free. |
| U3 | VPS CPU architecture + core count | `uname -m`, `nproc` | Ollama CPU inference on < 4 cores is painfully slow for a prospect demo. Confirm before committing. |
| U4 | Existing tools: `node`, `python3.12`, `pm2`, `ollama`, `cloudflared`, `git`, `git-crypt`, `uv` | `command -v <tool>` loop | Every missing tool becomes a sub-task in PREP. |
| U5 | Exact cloudflared config path and format | `ls /etc/cloudflared/`, `cat /etc/cloudflared/config.yml` — or if running as `cloudflared service install`, check `/etc/systemd/system/cloudflared.service` for `--config` path | Determines how the tunnel ingress rule for `try.grip-web.com` is rewritten. Could be a single `config.yml` OR a named-tunnel YAML under `~/.cloudflared/<tunnel-id>.yml`. |
| U6 | Which Cloudflare tunnel owns `try.grip-web.com` (tunnel ID, credentials file, route type: hostname ingress vs CNAME vs DNS record) | `cloudflared tunnel list`, `cloudflared tunnel route ip show` | Without this, the cutover command is guesswork. |
| U7 | Ports currently in use on VPS: `:8100`, `:3201`, `:11434` | `ss -tlnp` | Backend wants `:8100`, frontend needs *any* free internal port (plan suggests `:3201`), Ollama wants `:11434`. |
| U8 | Does `nexus-poc` have a git remote? If yes, can the VPS clone it? If no, rsync from MacBook over Tailscale is the deploy path | `cd ~/nexus-poc && git remote -v` | Chooses between `git clone` vs `rsync -avz` for file delivery. |
| U9 | Does the VPS already have a `GROQ_API_KEY` / `ANTHROPIC_API_KEY` env loader (e.g. `/etc/grip.env` or similar)? | `ls /etc/grip* /etc/nexus* 2>/dev/null; env \| grep -iE 'groq\|anthropic'` | Determines whether secrets are added to an existing loader or a new `/etc/nexus.env` is created. |

## Target architecture on the VPS

```
                     ┌────────────────────────────────────┐
Cloudflare Edge      │             grip-remote            │
(try.grip-web.com)   │            Ubuntu 24.04            │
        │            │                                    │
        ▼            │  cloudflared (existing, reloaded)  │
   ┌────────┐        │          │                         │
   │ Tunnel │────────┼──────────┤                         │
   └────────┘        │          ▼                         │
                     │   localhost:3201 (pm2 nexus-fe)    │
                     │          │                         │
                     │          │ next rewrites /api/*    │
                     │          ▼                         │
                     │   localhost:8100 (pm2 nexus-be)    │
                     │          │                         │
                     │          ▼                         │
                     │   localhost:11434 (ollama)         │
                     │          │                         │
                     │          ▼                         │
                     │    gemma4:e4b (on-disk)            │
                     │                                    │
                     │  (Sprint Dashboard pm2 grip-server │
                     │   still runs on :3847 but is       │
                     │   no longer in cloudflared ingress │
                     │   — Tailscale-only access)         │
                     └────────────────────────────────────┘
```

- **Backend:** FastAPI on `127.0.0.1:8100`, pm2 process `nexus-backend`.
- **Frontend:** `next start --port 3201`, pm2 process `nexus-frontend`. Why 3201? — avoids clashing with the 3200 used by the local dev server on the MacBook, gives a visually distinct "not the local dev server" port to anyone SSHing in.
- **Ollama:** default `127.0.0.1:11434`, systemd unit (comes with the Ollama installer).
- **ChromaDB:** file-backed under `/srv/nexus-poc/data/` (gitignored locally, so deploy must create the dir and provision any existing corpus).
- **Secrets:** `/etc/nexus.env`, `chmod 600 root:root`, loaded into both pm2 processes via their ecosystem file.
- **Frontend `next.config.ts`:** no change — its rewrites already point `/api/*` → `localhost:8100`, which is correct on the VPS too.

## Phase 1 — PREP (zero-blast-radius, do BEFORE any meetings depend on it)

Executed via `tailscale ssh root@grip-remote` from the MacBook. Tailscale must be up first (`sudo tailscale up`).

1. **Start Tailscale locally** — `sudo tailscale up`. Confirms the MacBook has a route to `100.66.66.92`.
2. **Run the probe script** (resolves U1–U9 in one round-trip):
   ```bash
   tailscale ssh root@grip-remote "
     uname -a; free -h; df -h /; nproc; uname -m;
     for t in node python3 python3.12 pm2 ollama cloudflared docker git git-crypt uv rsync; do
       command -v $t >/dev/null && echo \"$t: $(command -v $t)\" || echo \"$t: MISSING\";
     done;
     ss -tlnp 2>/dev/null | awk 'NR==1 || /:(3100|3200|3201|3847|8100|11434|3849|9999|80|443):/';
     ls -la /etc/cloudflared/ 2>&1;
     cat /etc/cloudflared/config.yml 2>/dev/null || echo '(no /etc/cloudflared/config.yml)';
     cloudflared tunnel list 2>&1 || true;
     pm2 list;
     ls /etc/grip* /etc/nexus* 2>/dev/null || true"
   ```
3. **Decision gate on U1/U2/U3:** if RAM < 5 GB free, or disk < 12 GB free, or CPU < 4 cores → HALT, re-ask V>> to reconsider the "disable confidential path on prod" fallback from the meeting's Q3. Do not silently downgrade.
4. **Install Ollama** (if missing): `curl -fsSL https://ollama.com/install.sh | sh`. Pulls ~50 MB binary, creates `ollama` systemd unit, starts it on `127.0.0.1:11434`.
5. **Pull `gemma4:e4b`**: `ollama pull gemma4:e4b`. Size ~9 GB. Can take 10–30 min depending on VPS bandwidth. Non-destructive; the pm2/Docker stack is unaffected.
6. **Warm the model**: `ollama run gemma4:e4b "Reply with the single word OK"`. First inference is slow (weights load into RAM); subsequent are fast.
7. **Install missing tooling:** whatever U4 flagged — typically `apt install python3.12-venv`, Node 20 LTS via NodeSource, etc. `pm2` and `cloudflared` are already present (they run the existing GRIP stack).
8. **Deliver the Nexus source** to the VPS. Two paths depending on U8:
   - **If `nexus-poc` has a GitHub/GitLab remote:** `cd /srv && git clone <remote>/nexus-poc.git`.
   - **If not:** rsync from MacBook over Tailscale:
     ```bash
     rsync -avz --delete \
       --exclude='node_modules' --exclude='venv' --exclude='.next' \
       --exclude='data/audit' --exclude='data/chroma' \
       --exclude='tsconfig.tsbuildinfo' \
       ~/nexus-poc/ root@100.66.66.92:/srv/nexus-poc/
     ```
     Run from `~/nexus-poc/`, not from `~/`.
9. **Strip LiteLLM** — in `/srv/nexus-poc/backend/requirements.txt`, remove the `litellm>=1.55.0` line. This is a hard constraint from the security feedback memory saved earlier today. Do it before `pip install` so the vulnerable package never lands on the VPS.
10. **Backend build:**
    ```bash
    cd /srv/nexus-poc/backend
    python3.12 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python -m spacy download en_core_web_sm
    ```
11. **Frontend build** (prod, not dev):
    ```bash
    cd /srv/nexus-poc/frontend
    npm ci
    npm run build
    ```
    Fix the `package.json` `start` script port from `3100` → `3201` OR rely on `next start --port 3201` directly in pm2 config.
12. **Create `/etc/nexus.env`** (root:root, mode 600):
    ```
    GROQ_API_KEY=<from V>>>
    ANTHROPIC_API_KEY=<from V>>>
    NEXUS_DEMO_PASSWORD=nexus-craig-2026
    OLLAMA_HOST=http://127.0.0.1:11434
    DATA_DIR=/srv/nexus-poc/data
    ```
    V>> supplies the API key values at execution time — **never commit them to this preplan**.
13. **pm2 ecosystem file** at `/srv/nexus-poc/ecosystem.config.js`:
    ```js
    module.exports = {
      apps: [
        {
          name: "nexus-backend",
          cwd: "/srv/nexus-poc/backend",
          script: "venv/bin/uvicorn",
          args: "app.main:app --host 127.0.0.1 --port 8100",
          env_file: "/etc/nexus.env",
          max_restarts: 5,
        },
        {
          name: "nexus-frontend",
          cwd: "/srv/nexus-poc/frontend",
          script: "npx",
          args: "next start --port 3201",
          env_file: "/etc/nexus.env",
          max_restarts: 5,
        },
      ],
    };
    ```
    Note: `env_file` is a pm2 extension — if the installed pm2 version doesn't support it, fall back to `env: { ...require('dotenv').parse(fs.readFileSync('/etc/nexus.env')) }`.
14. **Start nexus-backend + nexus-frontend under pm2:**
    ```bash
    pm2 start /srv/nexus-poc/ecosystem.config.js
    pm2 save
    ```
    `pm2 save` persists to disk so they survive reboot via the existing pm2 systemd unit.
15. **Internal smoke test** (NO public URL yet):
    ```bash
    curl -sf http://localhost:8100/health           # expect 200
    curl -sf -o /dev/null -w '%{http_code}\n' http://localhost:3201/     # expect 307 → /login
    ```
16. **Staged external test** — add a *secondary* cloudflared ingress rule for `nexus-staging.grip-web.com` (the existing `try.grip-web.com` rule is left untouched at this point) pointing to `http://localhost:3201`. Reload cloudflared. Open `https://nexus-staging.grip-web.com/login` in Brave. Log in with `nexus-craig-2026`. Click through all 5 prototypes. If any fail, fix before Phase 2.

At the end of Phase 1: Sprint Dashboard is still live at `try.grip-web.com`, nothing for Craig has changed, but Nexus is running and verified at `nexus-staging.grip-web.com`.

## Phase 2 — CUTOVER (execute when V>> says "go")

1. **Final sanity check** — `nexus-staging.grip-web.com` still healthy.
2. **Back up the cloudflared config** before editing:
   ```bash
   cp /etc/cloudflared/config.yml /etc/cloudflared/config.yml.bak-$(date +%s)
   ```
   (Or the equivalent path discovered in U5.)
3. **Edit the ingress rule** for `try.grip-web.com`:
   - Change `service: http://localhost:3847` → `service: http://localhost:3201`.
   - Leave every other hostname (`guild.grip-web.com`, `tralala.grip-web.com`, the `nexus-staging.grip-web.com` added in Phase 1) untouched.
   - Remove or retain the staging rule (prefer: **retain it** for one week as a rollback target, then prune).
4. **Validate:** `cloudflared tunnel ingress validate`
5. **Reload (not restart):** `systemctl reload cloudflared` — zero-downtime for the untouched hostnames.
6. **Wait ~5 s** for Cloudflare edge propagation.
7. **External verification from the MacBook:**
   ```bash
   curl -sI https://try.grip-web.com/login
   ```
   Expect HTTP 307 or 200 with Next.js headers (`x-nextjs-cache`, `x-powered-by: Next.js`).
8. **V>> logs in via Brave** at `https://try.grip-web.com/login` as the final human verification.
9. **Announce** — post to `#nexus-chats` (C0AKQJ4KR0E) and DM Craig Miller (D0ALWJRGBQB):
   > NEXUS POC is now live at https://try.grip-web.com. Demo password unchanged. Sprint Dashboard moved to Tailscale-only (reach me if you need it).

## Phase 3 — POST-CUTOVER HOUSEKEEPING

1. **Update `~/nexus-poc/CLAUDE.md`** — replace the line `LLM Routing: LiteLLM` with `LLM Routing: direct SDK router (Groq / Ollama / Anthropic) — LiteLLM forbidden, see feedback_no_litellm.md`.
2. **Remove `litellm>=1.55.0`** from `~/nexus-poc/backend/requirements.txt` locally (it's already stripped on the VPS in Phase 1 step 9). Commit with message `chore(nexus): drop litellm dependency (security)`.
3. **Update `~/nexus-poc/start-demo.sh`** — the log line `NEXUS demo live at https://try.grip-web.com` is now actually true. No edit needed, but worth a re-read to confirm nothing else is stale.
4. **Update `~/.claude/rules/session-context.md`** — add to the VPS pm2 line: `grip-server(:3847, Tailscale-only)`, `nexus-backend(:8100)`, `nexus-frontend(:3201, public via try.grip-web.com)`.
5. **Save a new feedback memory** at `~/.claude/projects/-Users-lauriescheepers--claude/memory/project_nexus_vps_location.md` recording: VPS path `/srv/nexus-poc`, pm2 process names, secrets path `/etc/nexus.env`, cloudflared config path (from U5).

## Rollback

Every rollback is a config edit + reload:

- **Nexus crashes post-cutover:** `pm2 stop nexus-*`, restore `config.yml.bak-<timestamp>`, `systemctl reload cloudflared`. `try.grip-web.com` returns to Sprint Dashboard in ~5 s.
- **cloudflared fails to reload:** `systemctl status cloudflared` to read the error. If config YAML is malformed, the backup file is the recovery path. `grip-server` pm2 process is left running throughout — it only loses its public URL, so even during a full Nexus outage it's reachable via Tailscale.
- **Ollama pull fails mid-phase-1:** non-blocking. Nexus backend can start without the confidential path — the router's `_check_ollama()` returns false and traffic routes to Groq/Anthropic. Retry the pull in a background session.

## Blast radius summary

| Phase | Effect on `try.grip-web.com` | Effect on other URLs | Reversible? |
|---|---|---|---|
| Phase 1 | None — Sprint Dashboard still live | None — adds `nexus-staging.grip-web.com` | Yes — delete the staging rule |
| Phase 2 step 5 | ~5 s propagation window | None (reload, not restart) | Yes — config backup + reload |
| Phase 3 | None | Updates doc files only | Yes — git revert |

## Falsification criterion for "this plan succeeded"

All three must hold, measured from a network *off* V>>'s home Wi-Fi (e.g. phone tether) to prove no MacBook dependency:

1. `curl -sf -o /dev/null -w '%{http_code}' https://try.grip-web.com/login` returns `200` or `307`.
2. A login POST against `https://try.grip-web.com/api/auth/login` with `NEXUS_DEMO_PASSWORD=nexus-craig-2026` returns a valid session cookie.
3. A POST to `https://try.grip-web.com/api/routing/query` with a PII-rich prompt returns a response whose `routing_decision.provider == "ollama"` and `model_used == "gemma4:e4b"` within 30 s, and the audit chain on the VPS logs an entry for that routing decision.

If any of the three fails, Phase 2 is not complete.

## Open questions for V>> before executing Phase 1

1. **Secrets:** Are the MacBook's `GROQ_API_KEY` and `ANTHROPIC_API_KEY` OK to copy to the VPS, or do we provision new VPS-scoped keys (rotate risk vs blast-radius containment)?
2. **Source delivery:** Does `nexus-poc` have a git remote yet? If yes, which one? If no, rsync-over-Tailscale is the default (U8).
3. **Staging subdomain:** `nexus-staging.grip-web.com` — is it OK to add this DNS record, or should Phase 1 step 16 use a plain IP:port test instead? (Faster to delete, but slightly less realistic than a full Cloudflare path.)
4. **Cloudflare Access:** Should `try.grip-web.com` be protected by Cloudflare Access (email-link auth) on top of the Next.js demo password, or is the demo password alone sufficient for prospect use?
