const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

async function fetchAPI(path: string, options?: RequestInit) {
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
  if (!res.ok) {
    let detail = `API error: ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // non-JSON error body — keep the status message
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => fetchAPI("/health"),

  // Documents
  uploadDocument: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/api/documents/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
  },
  batchUpload: () => fetchAPI("/api/documents/batch-upload", { method: "POST" }),
  listDocuments: () => fetchAPI("/api/documents/list"),
  getDocumentContent: (doc_id: string) =>
    fetchAPI(`/api/documents/content/${doc_id}`),
  redactDocument: (doc_id: string) =>
    fetchAPI(`/api/documents/content/${doc_id}/redact`, { method: "POST" }),
  downloadRedactedUrl: (doc_id: string) =>
    `${API_BASE}/api/documents/content/${doc_id}/download-redacted`,
  searchDocuments: (query: string, n_results = 5, mode = "semantic", lang = "en") =>
    fetchAPI("/api/documents/search", {
      method: "POST",
      body: JSON.stringify({ query, n_results, mode, lang }),
    }),
  searchStats: () => fetchAPI("/api/documents/search-stats"),
  classifyText: (text: string, filename = "") =>
    fetchAPI("/api/documents/classify", {
      method: "POST",
      body: JSON.stringify({ text, filename }),
    }),
  ingestFolderStream: (
    folder_path: string,
    onEvent: (data: Record<string, unknown>) => void,
    onDone: () => void,
    onError: (err: string) => void,
  ): AbortController => {
    const controller = new AbortController();
    fetch(`${API_BASE}/api/documents/ingest-folder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_path }),
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          onError(`API error: ${res.status}`);
          return;
        }
        const reader = res.body?.getReader();
        if (!reader) {
          onError("No response body");
          return;
        }
        const decoder = new TextDecoder();
        let buffer = "";
        let finished = false;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            const match = line.match(/^data:\s*(.*)/);
            if (match?.[1]) {
              try {
                const data = JSON.parse(match[1]);
                onEvent(data);
                if (data.event === "done") {
                  finished = true;
                  onDone();
                  return;
                }
              } catch { /* skip malformed */ }
            }
          }
        }
        if (!finished) onDone();
      })
      .catch((err) => {
        if (err.name !== "AbortError") onError(String(err));
      });
    return controller;
  },

  // LLM Routing
  routeQuery: (prompt: string, task_type = "general", force_model?: string) =>
    fetchAPI("/api/routing/query", {
      method: "POST",
      body: JSON.stringify({ prompt, task_type, force_model }),
    }),
  classifySensitivity: (text: string): Promise<{
    sensitivity_level: string;
    sensitivity_score: number;
    pii_types_detected: string[];
    confidence_rationale?: string;
    reasoning?: string;
    synthesis_method?: string;
    idr?: Record<string, unknown>;
  }> =>
    fetchAPI("/api/routing/classify-sensitivity", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  getRoutingAudit: () => fetchAPI("/api/routing/audit"),

  // Entity Graph
  getGraph: () => fetchAPI("/api/entities/graph"),
  getSubgraph: (entityId: string, depth = 1) =>
    fetchAPI(`/api/entities/graph/${entityId}?depth=${depth}`),
  listEntities: () => fetchAPI("/api/entities/list"),
  entityStats: () => fetchAPI("/api/entities/stats"),

  // Intent Decision Records (IDRs)
  getIdrsRecent: (limit = 50) => fetchAPI(`/api/idrs/recent?limit=${limit}`),
  verifyIdrChain: () => fetchAPI("/api/idrs/verify"),
  getIdrBySequence: (sequence: number) => fetchAPI(`/api/idrs/sequence/${sequence}`),
  reviewIdr: (
    sequence: number,
    body: {
      status: "confirmed" | "refuted" | "inconclusive";
      reviewer_id: string;
      reviewer_label?: string;
      notes?: string;
    },
  ) =>
    fetchAPI(`/api/idrs/${sequence}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // SOPs
  listSOPs: () => fetchAPI("/api/sops/list"),
  startSOP: (sopId: string) =>
    fetchAPI(`/api/sops/start/${sopId}`, { method: "POST" }),
  respondToSOP: (executionId: string, response: unknown) =>
    fetchAPI(`/api/sops/respond/${executionId}`, {
      method: "POST",
      body: JSON.stringify({ response }),
    }),
  sopStatus: (executionId: string) =>
    fetchAPI(`/api/sops/status/${executionId}`),

  // Voice Transcription (Groq Whisper large-v3 — browser-agnostic, no Google STT)
  transcribeAudio: async (blob: Blob, filename = "audio.webm"): Promise<{ transcript: string }> => {
    const form = new FormData();
    form.append("audio", blob, filename);
    const res = await fetch(`${API_BASE}/api/voice/transcribe`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(`Transcription failed: ${res.status}`);
    return res.json();
  },

  // Time Capture
  captureTime: (transcript: string, hourly_rate_chf = 450) =>
    fetchAPI("/api/time/capture", {
      method: "POST",
      body: JSON.stringify({ transcript, hourly_rate_chf }),
    }),
  logTime: (transcript: string, hourly_rate_chf = 450) =>
    fetchAPI("/api/time/log", {
      method: "POST",
      body: JSON.stringify({ transcript, hourly_rate_chf }),
    }),
  listTimeEntries: () => fetchAPI("/api/time/entries"),
  updateTimeMatter: (entryId: string, matter: string) =>
    fetchAPI(`/api/time/entries/${entryId}/matter`, {
      method: "PATCH",
      body: JSON.stringify({ matter }),
    }),
  updateTimeTranscript: (entryId: string, transcript: string) =>
    fetchAPI(`/api/time/entries/${entryId}/transcript`, {
      method: "PATCH",
      body: JSON.stringify({ transcript }),
    }),
  timeSummary: (rate?: number) =>
    fetchAPI(`/api/time/summary${rate ? `?rate=${rate}` : ""}`),

  // AI Drafting
  listDraftingTemplates: (): Promise<{
    templates: Array<{
      id: string;
      name: string;
      description: string;
      template_type: string;
      base_prompt: string;
    }>;
  }> => fetchAPI("/api/drafting/templates"),
  generateDraft: (body: {
    template_id: string;
    matter_name?: string;
    client_name?: string;
    key_facts?: string[];
    additional_instructions?: string;
  }): Promise<{
    template_id: string;
    template_name: string;
    matter_name: string;
    client_name: string;
    draft_text: string;
    word_count: number;
    estimated_reading_minutes: number;
    model_used: string;
  }> =>
    fetchAPI("/api/drafting/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  summariseDocument: (
    document_text: string,
    summary_type: "brief" | "detailed" | "action_items",
  ): Promise<{
    summary_type: string;
    summary: string;
    word_count: number;
    source_chars: number;
    model_used: string;
  }> =>
    fetchAPI("/api/drafting/summarise", {
      method: "POST",
      body: JSON.stringify({ document_text, summary_type }),
    }),
  voiceToDraft: (transcript: string) =>
    fetchAPI("/api/drafting/voice-to-draft", {
      method: "POST",
      body: JSON.stringify({ transcript }),
    }),
  voiceToDraftMulti: (transcript: string): Promise<{
    intent_count: number;
    results: Array<{
      plan: { template_id: string; matter_name: string; client_name: string; key_facts: string[]; additional_instructions: string; rationale: string };
      draft: { template_id: string; template_name: string; matter_name: string; client_name: string; draft_text: string; word_count: number; estimated_reading_minutes: number; model_used: string };
    }>;
  }> =>
    fetchAPI("/api/drafting/voice-to-draft-multi", {
      method: "POST",
      body: JSON.stringify({ transcript }),
    }),

  // Tasks / Delegation
  listTasks: (status?: string) =>
    fetchAPI(`/api/tasks/list${status ? `?status=${status}` : ""}`),
  delegateTask: (transcript: string) =>
    fetchAPI("/api/tasks/delegate", {
      method: "POST",
      body: JSON.stringify({ transcript }),
    }),
  createTask: (task: {
    title: string;
    description?: string;
    assignee: string;
    matter?: string;
    deadline?: string;
    priority?: string;
    raw_transcript?: string;
  }) =>
    fetchAPI("/api/tasks/create", {
      method: "POST",
      body: JSON.stringify(task),
    }),
  updateTaskStatus: (taskId: string, status: string) =>
    fetchAPI(`/api/tasks/${taskId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  updateTaskTranscript: (taskId: string, transcript: string) =>
    fetchAPI(`/api/tasks/${taskId}/transcript`, {
      method: "PATCH",
      body: JSON.stringify({ transcript }),
    }),
  listAssignees: (): Promise<{ assignees: string[] }> =>
    fetchAPI("/api/tasks/assignees"),

  // SharePoint (stub integration)
  sharepointStatus: (): Promise<{
    enabled: boolean;
    stub_mode: boolean;
    synced_count: number;
  }> => fetchAPI("/api/sharepoint/status"),
  sharepointConnect: (config: {
    tenant_id?: string;
    client_id?: string;
    site_url?: string;
    library_name?: string;
  }): Promise<{
    connected: boolean;
    stub_mode: boolean;
    site_url: string;
    library_name: string;
    message: string;
    sample_documents: string[];
    tested_at: string;
  }> =>
    fetchAPI("/api/sharepoint/connect", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  sharepointDocuments: (config: {
    site_url?: string;
    library_name?: string;
  } = {}): Promise<{
    documents: Array<{
      id: string;
      title: string;
      document_type: string;
      modified: string;
      size_bytes: number;
      author: string;
      web_url: string;
      synced: boolean;
    }>;
    count: number;
    stub_mode: boolean;
  }> => {
    const params = new URLSearchParams();
    if (config.site_url) params.set("site_url", config.site_url);
    if (config.library_name) params.set("library_name", config.library_name);
    const qs = params.toString();
    return fetchAPI(`/api/sharepoint/documents${qs ? `?${qs}` : ""}`);
  },
  sharepointSync: (doc_id: string, config: Record<string, string> = {}) =>
    fetchAPI("/api/sharepoint/sync", {
      method: "POST",
      body: JSON.stringify({ doc_id, ...config }),
    }),
  sharepointExport: (config: {
    content: string;
    filename: string;
    folder?: string;
    [key: string]: unknown;
  }) =>
    fetchAPI("/api/sharepoint/export", {
      method: "POST",
      body: JSON.stringify(config),
    }),
};
