# Multi-Tenancy Isolation — 8h Wave Sprint

**Goal**: make `free.donnaoss.com` 100% prod-ready for multiple attorneys. Every layer (auth, audit chain, IDR, ChromaDB, filesystem, routes, frontend) must partition data by `user_id`.

**Started**: 2026-05-11 21:58 UTC
**Branch**: `feat/multi-tenancy-isolation` (worktree `/tmp/nexus-mt-1778536790`)
**TTL**: 8 hours (until 2026-05-12 05:58 UTC)

## Starting state (the gap V>> flagged)

The single-tenant failure surface as confirmed by reading the code on 2026-05-11:

| Layer | State today | Symptom |
|-------|-------------|---------|
| Auth | Single shared `NEXUS_DEMO_PASSWORD`; identical hash cookie for everyone (`frontend/src/lib/auth.ts`) | No notion of "user" — login UI is a turnstile, not an identity gate |
| Backend auth | **No middleware** — backend trusts every request, no `get_current_user` dependency, no 401 on unauthenticated calls | Anyone with the demo password sees everything |
| ChromaDB | One global collection, no metadata filter | All embeddings co-mingle |
| Filesystem | `data/filed/<doc>.pdf` flat | Every upload lands in the same place |
| Audit chain | One signing key + one chain state | All IDRs share one HMAC chain |
| IDR store | Single JSONL | No tenant scope |
| Matters / documents / SOPs | No `user_id` column anywhere | No ownership |

## Wave plan (Fibonacci 1,1,2,3,5,8)

### W1 — User identity + session (d=1, 1 batch)

Build the substrate that everything else depends on.

- `backend/models/user.py` — `User` Pydantic model: `id`, `email`, `password_hash`, `created_at`
- `backend/services/user_store.py` — JSONL persistence (`data/users.jsonl`), simple bcrypt or Argon2 hash
- `backend/app/auth.py` — FastAPI dependency `get_current_user`, session cookie reader (HMAC-signed cookie `nexus-session=<user_id>:<sig>`)
- `backend/app/routes_auth.py` — `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- Replace `frontend/src/lib/auth.ts` shared-password hash with email/password call to `/api/auth/login`
- Replace `frontend/src/middleware.ts` cookie check to look for the new `nexus-session` cookie
- Replace `frontend/src/app/api/auth/login/route.ts` to proxy to backend
- New `frontend/src/app/(auth)/signup/page.tsx`
- `frontend/src/components/UserContext.tsx` — provider exposing `currentUser`

**Hypothesis H-MT-1**: a freshly signed-up user `alice@test.com` and a separately signed-up `bob@test.com` produce different session cookies that resolve to distinct `user_id` values, and `GET /api/auth/me` returns different payloads. Falsified if same `user_id` issued or signature collision.

**Anti-Goodhart**: pytest case `test_signup_two_users_get_different_ids` asserts exact distinct UUIDs.

### W2 — Authorisation middleware on every route (d=1, 1 batch)

Mechanical enforcement so future routes can't forget.

- FastAPI middleware OR `Depends(get_current_user)` applied to every router include in `backend/app/main.py`
- Whitelist: `/health`, `/api/auth/*`, `/openapi.json`, `/docs`, `/redoc`
- Every other `/api/*` route returns **401** when no valid session cookie present

**Hypothesis H-MT-2**: `curl POST /api/documents/upload` without a cookie returns HTTP 401. Falsified if any non-auth route reachable anonymously.

**Anti-Goodhart**: pytest `test_every_non_auth_route_requires_session` enumerates all routes via `app.routes` and POSTs to each without a cookie, asserts 401 on each.

### W3 — Storage layer partitioning (d=2, 2 batches)

**3a — ChromaDB user-scoped collection**:
- `backend/services/embedding_service.py` — `upsert(..., user_id)` stamps metadata, `search(..., user_id)` adds `where={"user_id": user_id}`
- All callers pass `current_user.id`

**3b — Filesystem per-user partitioning**:
- `backend/services/document_processor.py` — `file_doc(..., user_id)` writes to `data/filed/<user_id>/<doc>.pdf`
- Migration: existing `data/filed/*.pdf` (V>>'s data) → `data/filed/<v_user_id>/` after V>> first signup

**Hypothesis H-MT-3**: a search query by Alice cannot return any chunk that Bob uploaded. Falsified if cross-tenant chunk surfaces in any search.

**Anti-Goodhart**: integration test creates two users, uploads distinct docs, runs identical search query as each, asserts disjoint result sets.

### W4 — Audit chain + IDR per-tenant (d=3, 3 batches)

**4a — Audit chain**:
- `backend/core/audit_chain.py` — `AuditChain(tenant_id)` constructor, signing key under `data/audit/<tenant_id>/signing-key`, chain state under `data/audit/<tenant_id>/chain-state.json`

**4b — IDR store**:
- `backend/core/idr_store.py` + `backend/core/idr_happi.py` — per-tenant JSONL at `data/audit/<tenant_id>/idrs.jsonl`

**4c — Caller migration**:
- All sites that read/write IDRs accept `user_id` and route to the right chain

**Hypothesis H-MT-4**: Alice's `GET /api/idrs/recent` cannot contain any record whose `signer` matches Bob's user_id. Falsified if cross-tenant IDR leakage.

**Anti-Goodhart**: pytest creates an IDR as user A, switches to user B's session, asserts B sees zero records.

### W5 — Resource ownership on every model (d=5, 5 batches)

**5a Matter** — `MatterIn` accepts `user_id` from `current_user`, GET/LIST scoped, ownership check on detail/update
**5b Document** — `Document.user_id`, listing filtered, download blocks cross-user
**5c SOP execution** — `SOPExecution.user_id`, list scoped
**5d Task** — `Task.user_id`, list scoped
**5e Email/Calendar drafts** — drafts persisted per-user (if persisted at all; current state is in-memory)

**Hypothesis H-MT-5**: Bob cannot `GET /api/matters/<alice_matter_id>` — should return 404 (not 403, to avoid leaking existence). Falsified if anything ≠ 404 returned for cross-tenant resource fetch.

### W6 — Integration + ship (d=8, 8 batches)

**6a** End-to-end integration test: Alice signup → upload doc → search; Bob signup → upload doc → search; assert disjoint everything
**6b** Frontend signup page wired through real backend
**6c** Frontend login page wired through real backend
**6d** UserContext provider + `useCurrentUser` hook + display in `(main)/layout.tsx` header
**6e** Vercel preview build — manual two-account walkthrough
**6f** VPS deploy: `ssh root@VPS && git pull && pm2 restart nexus-backend nexus-frontend`
**6g** Backwards-compat: migrate V>>'s existing data into the first-signup user account so the demo continues to work
**6h** Documentation: `docs/multi-tenancy.md` + production runbook + close out

**Hypothesis H-MT-6**: on the live `free.donnaoss.com`, two browsers in incognito mode with two distinct signups see zero overlap in documents, matters, IDRs, embeddings. Falsified if any cross-tenant data visible from either account.

## Falsification surface (cross-cutting)

This whole sprint is wrong if any of:

- The session cookie can be forged by a client (HMAC validation must reject tampering)
- A user can guess another user's `user_id` and access their resources via the URL
- ChromaDB `where` filter is bypassed by a query path we missed
- `data/filed/` writes still land in the flat directory under any code path
- The migration of V>>'s existing data either loses records or assigns them to the wrong account

## Notification cadence

- Pre-W1: kickoff post (this commit)
- After each wave's ship: progress post
- Final: production-ready announcement

## What this does NOT cover (explicit non-goals)

- Email verification flow
- Password reset
- Per-tenant rate limiting
- Tenant admin (multiple users per tenant)
- SSO/SAML
- 2FA
- Per-tenant feature flags

Those are valid follow-ups but not on the 8h critical path.
