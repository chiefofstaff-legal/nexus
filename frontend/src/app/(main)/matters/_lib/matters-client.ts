// Typed fetch wrappers for the Matter API. Matches the existing src/lib/api.ts
// pattern (single fetchAPI helper, named export object). Kept colocated to the
// matters route group because the backend domain is matter-specific.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (res.status === 401 && typeof window !== "undefined") {
    window.location.href = `/login?from=${encodeURIComponent(path)}`;
    throw new Error("Session expired — redirecting to login");
  }
  if (res.status === 204) return undefined as unknown as T;
  if (!res.ok) {
    let detail = `API error: ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // non-JSON body — keep status message
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export interface Matter {
  id: string;
  name: string;
  client: string | null;
  notes: string | null;
  created_at: string;
  archived_at: string | null;
}

export interface MatterDocument {
  matter_id: string;
  document_id: string;
  added_at: string;
}

export interface MatterCreate {
  name: string;
  client?: string;
  notes?: string;
}

export interface MatterUpdate {
  name?: string;
  client?: string | null;
  notes?: string | null;
}

export const mattersClient = {
  createMatter: (body: MatterCreate): Promise<Matter> =>
    fetchAPI("/api/matters", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listMatters: async (archived = false): Promise<Matter[]> => {
    // Backend wraps the array as {"matters": [...]} for forward-compatibility
    // (lets us add pagination/metadata fields later without breaking callers).
    // Unwrap here so consumers can call .map() directly.
    const wrapped = await fetchAPI<{ matters: Matter[] }>(
      `/api/matters?archived=${archived ? "true" : "false"}`,
    );
    return wrapped.matters;
  },

  getMatter: (matterId: string): Promise<Matter> =>
    fetchAPI(`/api/matters/${encodeURIComponent(matterId)}`),

  updateMatter: (matterId: string, patch: MatterUpdate): Promise<Matter> =>
    fetchAPI(`/api/matters/${encodeURIComponent(matterId)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  archiveMatter: (matterId: string): Promise<Matter> =>
    fetchAPI(`/api/matters/${encodeURIComponent(matterId)}`, {
      method: "DELETE",
    }),

  addDocumentToMatter: (
    matterId: string,
    documentId: string,
  ): Promise<MatterDocument> =>
    fetchAPI(`/api/matters/${encodeURIComponent(matterId)}/documents`, {
      method: "POST",
      body: JSON.stringify({ document_id: documentId }),
    }),

  removeDocumentFromMatter: (
    matterId: string,
    documentId: string,
  ): Promise<void> =>
    fetchAPI(
      `/api/matters/${encodeURIComponent(matterId)}/documents/${encodeURIComponent(documentId)}`,
      { method: "DELETE" },
    ),

  listMatterDocuments: async (matterId: string): Promise<MatterDocument[]> => {
    // Same {"documents": [...]} wrapper as listMatters — unwrap on the client.
    const wrapped = await fetchAPI<{ documents: MatterDocument[] }>(
      `/api/matters/${encodeURIComponent(matterId)}/documents`,
    );
    return wrapped.documents;
  },
};

export interface SummarySnapshot {
  matter_id: string;
  version_id: number;
  content: string;
  source_citations: string[];
  created_at: string;
}

export const summaryClient = {
  getSummary: (matterId: string): Promise<SummarySnapshot> =>
    fetchAPI(`/api/matters/${encodeURIComponent(matterId)}/summary`),

  regenerateSummary: (matterId: string): Promise<SummarySnapshot> =>
    fetchAPI(`/api/matters/${encodeURIComponent(matterId)}/summary/regenerate`, {
      method: "POST",
    }),

  getSummaryVersion: (matterId: string, versionId: number): Promise<SummarySnapshot> =>
    fetchAPI(`/api/matters/${encodeURIComponent(matterId)}/summary/${versionId}`),
};

// Relative-time helper used by the list cards. Kept in the same module as the
// types so the consumer imports from one place.
export function relativeTime(iso: string): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diffSec = Math.round((Date.now() - then) / 1000);
  if (diffSec < 60) return "just now";
  const mins = Math.round(diffSec / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.round(months / 12)}y ago`;
}
