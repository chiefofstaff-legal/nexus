/**
 * Client-side auth helpers.
 *
 * The backend is the source of truth: it issues an HMAC-signed
 * `nexus-session` cookie via Set-Cookie on /api/auth/{login,signup}.
 * Every fetch through this module sets `credentials: "include"` so the
 * cookie is sent on subsequent requests and the rewrite layer can
 * forward it through to the backend.
 */

export const SESSION_COOKIE_NAME = "nexus-session";

export interface CurrentUser {
  id: string;
  email: string;
}

async function postJson(path: string, body: unknown): Promise<Response> {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
    cache: "no-store",
  });
}

export class AuthError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: string };
    if (data?.detail) return data.detail;
  } catch {
    // fall through
  }
  return res.statusText || "Authentication failed";
}

export async function signupUser(email: string, password: string): Promise<CurrentUser> {
  const res = await postJson("/api/auth/signup", { email, password });
  if (!res.ok) throw new AuthError(await readError(res), res.status);
  return (await res.json()) as CurrentUser;
}

export async function loginUser(email: string, password: string): Promise<CurrentUser> {
  const res = await postJson("/api/auth/login", { email, password });
  if (!res.ok) throw new AuthError(await readError(res), res.status);
  return (await res.json()) as CurrentUser;
}

export async function logoutUser(): Promise<void> {
  await postJson("/api/auth/logout", {});
}

export async function requestPasswordReset(email: string): Promise<void> {
  const res = await postJson("/api/auth/forgot", { email });
  if (res.status !== 204) throw new AuthError(await readError(res), res.status);
}

export async function resetPassword(token: string, newPassword: string): Promise<CurrentUser> {
  const res = await postJson("/api/auth/reset", { token, new_password: newPassword });
  if (!res.ok) throw new AuthError(await readError(res), res.status);
  return (await res.json()) as CurrentUser;
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  const res = await fetch("/api/auth/me", { credentials: "include", cache: "no-store" });
  if (res.status === 401) return null;
  if (!res.ok) throw new AuthError(await readError(res), res.status);
  return (await res.json()) as CurrentUser;
}
