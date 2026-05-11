/**
 * Shared auth utilities for middleware and login route handler.
 * Deterministic hash for cookie-based session validation.
 */

export const COOKIE_NAME = "nexus-demo-auth";
export const ENV_KEY = "NEXUS_DEMO_PASSWORD";
const SALT = "nexus-demo-2026";

export function hashPassword(password: string): string {
  let hash = 0;
  const str = `${SALT}:${password}`;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash + char) | 0;
  }
  return hash.toString(36);
}

export function getDemoPassword(): string | undefined {
  return process.env[ENV_KEY];
}

export function validateCookie(cookieValue: string): boolean {
  const pw = getDemoPassword();
  if (!pw) return true;
  return cookieValue === hashPassword(pw);
}
