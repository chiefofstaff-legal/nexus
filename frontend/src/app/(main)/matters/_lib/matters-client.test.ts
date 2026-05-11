import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { mattersClient, relativeTime } from "./matters-client";

const ORIGINAL_FETCH = global.fetch;

interface FetchCall {
  url: string;
  init?: RequestInit;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(handler: (call: FetchCall) => Response) {
  const calls: FetchCall[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return handler({ url, init });
  });
  // @ts-expect-error — overriding global fetch for the duration of the test
  global.fetch = fn;
  return calls;
}

describe("mattersClient fetch wrappers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
  });

  it("createMatter POSTs to /api/matters with the request body", async () => {
    const calls = mockFetch(() =>
      jsonResponse({
        id: "m_1",
        name: "x",
        client: null,
        notes: null,
        created_at: "now",
        archived_at: null,
      }, 201),
    );
    await mattersClient.createMatter({ name: "x", client: "Acme" });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/matters");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      name: "x",
      client: "Acme",
    });
  });

  it("listMatters appends the archived flag", async () => {
    const calls = mockFetch(() => jsonResponse({ matters: [] }));
    await mattersClient.listMatters(true);
    expect(calls[0].url).toBe("/api/matters?archived=true");
  });

  it("listMatters defaults to archived=false when called with no argument", async () => {
    const calls = mockFetch(() => jsonResponse({ matters: [] }));
    await mattersClient.listMatters();
    expect(calls[0].url).toBe("/api/matters?archived=false");
  });

  it("listMatters unwraps the {matters: [...]} envelope and returns the array", async () => {
    // Backend returns {"matters": [...]} for forward-compat. Caller treats
    // the result as a Matter[] and calls .map() on it; the client MUST
    // unwrap or the consumer code will throw "e.map is not a function".
    mockFetch(() =>
      jsonResponse({
        matters: [
          { id: "m_1", name: "alpha", client: null, notes: null, created_at: "now", archived_at: null },
          { id: "m_2", name: "beta", client: null, notes: null, created_at: "now", archived_at: null },
        ],
      }),
    );
    const result = await mattersClient.listMatters();
    expect(Array.isArray(result)).toBe(true);
    expect(result).toHaveLength(2);
    expect(result[0].name).toBe("alpha");
    // Critical Goodhart guard: .map MUST be callable on the result
    expect(() => result.map((m) => m.id)).not.toThrow();
  });

  it("getMatter encodes the matter id", async () => {
    const calls = mockFetch(() =>
      jsonResponse({
        id: "id with space",
        name: "x",
        client: null,
        notes: null,
        created_at: "now",
        archived_at: null,
      }),
    );
    await mattersClient.getMatter("id with space");
    expect(calls[0].url).toBe("/api/matters/id%20with%20space");
  });

  it("updateMatter sends PATCH with the patch body", async () => {
    const calls = mockFetch(() =>
      jsonResponse({
        id: "m_1",
        name: "renamed",
        client: null,
        notes: null,
        created_at: "now",
        archived_at: null,
      }),
    );
    await mattersClient.updateMatter("m_1", { name: "renamed" });
    expect(calls[0].url).toBe("/api/matters/m_1");
    expect(calls[0].init?.method).toBe("PATCH");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ name: "renamed" });
  });

  it("archiveMatter sends DELETE", async () => {
    const calls = mockFetch(() =>
      jsonResponse({
        id: "m_1",
        name: "x",
        client: null,
        notes: null,
        created_at: "now",
        archived_at: "now",
      }),
    );
    await mattersClient.archiveMatter("m_1");
    expect(calls[0].url).toBe("/api/matters/m_1");
    expect(calls[0].init?.method).toBe("DELETE");
  });

  it("addDocumentToMatter posts the document_id", async () => {
    const calls = mockFetch(() =>
      jsonResponse({ matter_id: "m_1", document_id: "d_1", added_at: "now" }, 201),
    );
    await mattersClient.addDocumentToMatter("m_1", "d_1");
    expect(calls[0].url).toBe("/api/matters/m_1/documents");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ document_id: "d_1" });
  });

  it("removeDocumentFromMatter sends DELETE and tolerates 204", async () => {
    const calls = mockFetch(
      () => new Response(null, { status: 204 }),
    );
    await mattersClient.removeDocumentFromMatter("m_1", "d_1");
    expect(calls[0].url).toBe("/api/matters/m_1/documents/d_1");
    expect(calls[0].init?.method).toBe("DELETE");
  });

  it("listMatterDocuments GETs the documents list", async () => {
    const calls = mockFetch(() => jsonResponse([]));
    await mattersClient.listMatterDocuments("m_1");
    expect(calls[0].url).toBe("/api/matters/m_1/documents");
    expect(calls[0].init?.method).toBeUndefined();
  });

  it("propagates the API error detail when present", async () => {
    mockFetch(() => jsonResponse({ detail: "matter not found" }, 404));
    await expect(mattersClient.getMatter("nope")).rejects.toThrow("matter not found");
  });
});

describe("relativeTime", () => {
  it("returns 'just now' for sub-minute deltas", () => {
    expect(relativeTime(new Date(Date.now() - 10_000).toISOString())).toBe("just now");
  });

  it("formats minutes, hours, days, months, years", () => {
    const min = (n: number) => new Date(Date.now() - n * 60_000).toISOString();
    expect(relativeTime(min(5))).toBe("5m ago");
    expect(relativeTime(min(60 * 3))).toBe("3h ago");
    expect(relativeTime(min(60 * 24 * 2))).toBe("2d ago");
    expect(relativeTime(min(60 * 24 * 60))).toBe("2mo ago");
    expect(relativeTime(min(60 * 24 * 30 * 24))).toBe("2y ago");
  });

  it("returns em-dash on bad input", () => {
    expect(relativeTime("")).toBe("—");
    expect(relativeTime("not-a-date")).toBe("—");
  });
});
