import { describe, expect, it, vi, beforeEach } from "vitest";
import {
  AuthError,
  SESSION_COOKIE_NAME,
  getCurrentUser,
  loginUser,
  logoutUser,
  signupUser,
} from "@/lib/auth";

describe("auth helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("exports the canonical session cookie name", () => {
    expect(SESSION_COOKIE_NAME).toBe("nexus-session");
  });

  it("loginUser POSTs JSON to /api/auth/login with credentials included", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: "u1", email: "alice@test.com" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = await loginUser("alice@test.com", "longenough");

    expect(user).toEqual({ id: "u1", email: "alice@test.com" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: "alice@test.com", password: "longenough" }),
      }),
    );
  });

  it("signupUser hits /api/auth/signup", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: "u2", email: "bob@test.com" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await signupUser("bob@test.com", "longenough");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/signup");
  });

  it("loginUser throws AuthError with backend detail on 401", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: async () => ({ detail: "Invalid credentials" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(loginUser("alice@test.com", "wrongpw1")).rejects.toMatchObject({
      message: "Invalid credentials",
      status: 401,
    });
    await expect(loginUser("alice@test.com", "wrongpw1")).rejects.toBeInstanceOf(AuthError);
  });

  it("getCurrentUser returns null when backend says 401", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401 });
    vi.stubGlobal("fetch", fetchMock);
    await expect(getCurrentUser()).resolves.toBeNull();
  });

  it("logoutUser hits /api/auth/logout", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    await logoutUser();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/logout");
  });
});
