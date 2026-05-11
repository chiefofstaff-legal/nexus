"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface SPDocument {
  id: string;
  title: string;
  document_type: string;
  modified: string;
  size_bytes: number;
  author: string;
  web_url: string;
  synced: boolean;
}

interface ConnectionResult {
  connected: boolean;
  stub_mode: boolean;
  site_url: string;
  message: string;
}

interface Config {
  tenant_id: string;
  client_id: string;
  client_secret: string;
  site_url: string;
  library_name: string;
}

const DEFAULT_CONFIG: Config = {
  tenant_id: "",
  client_id: "",
  client_secret: "",
  site_url: "",
  library_name: "Documents",
};

const DOC_TYPE_LABELS: Record<string, string> = {
  contract: "Contract",
  brief: "Brief",
  nda: "NDA",
  motion: "Motion",
  invoice: "Invoice",
  statute: "Statute",
  correspondence: "Letter",
  other: "Other",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatModified(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

// -- Primitives ---------------------------------------------------------------

function StubBanner() {
  return (
    <div className="border border-[#b08d57] bg-[#0a1628] text-white px-6 py-4 flex items-start gap-4">
      <span className="w-2 h-2 bg-[#b08d57] inline-block animate-pulse flex-shrink-0 mt-1" />
      <div>
        <div className="font-mono text-xs tracking-widest uppercase text-[#b08d57] mb-1">
          Preview mode
        </div>
        <p className="text-sm text-[#9ca3af]">
          SharePoint Graph API not configured. Showing mock documents. Set{" "}
          <code className="text-[#b08d57]">SHAREPOINT_ENABLED=true</code> with
          tenant credentials to connect live.
        </p>
      </div>
    </div>
  );
}

function ConnectionForm({
  config,
  onChange,
  onTest,
  testing,
  result,
}: {
  config: Config;
  onChange: (c: Config) => void;
  onTest: () => void;
  testing: boolean;
  result: ConnectionResult | null;
}) {
  const fields: Array<{ key: keyof Config; label: string; placeholder: string; secret?: boolean }> = [
    { key: "tenant_id", label: "Tenant ID", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" },
    { key: "client_id", label: "Client ID", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" },
    { key: "client_secret", label: "Client Secret", placeholder: "App registration secret value", secret: true },
    { key: "site_url", label: "Site URL", placeholder: "https://contoso.sharepoint.com/sites/legal" },
    { key: "library_name", label: "Library", placeholder: "Documents" },
  ];

  return (
    <div className="border border-[#d1d5db] bg-white p-6 space-y-5">
      <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
        Connection settings
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {fields.map(({ key, label, placeholder, secret }) => (
          <div key={key}>
            <label className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-1">
              {label}
            </label>
            <input
              type={secret ? "password" : "text"}
              value={config[key]}
              onChange={(e) => onChange({ ...config, [key]: e.target.value })}
              placeholder={placeholder}
              className="w-full border border-[#d1d5db] px-3 py-2 text-sm bg-transparent focus:outline-none focus:border-[#0a1628] transition-colors duration-200"
            />
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <button
          onClick={onTest}
          disabled={testing}
          className="border border-[#0a1628] bg-[#0a1628] text-white px-6 py-2 font-mono text-xs tracking-widest uppercase hover:bg-[#b08d57] hover:border-[#b08d57] disabled:opacity-40 transition-colors duration-200"
        >
          {testing ? "Testing…" : "Test connection"}
        </button>
        {result && (
          <div
            className={`font-mono text-xs tracking-widest uppercase ${
              result.connected ? "text-[#065f46]" : "text-[#dc2626]"
            }`}
          >
            {result.connected
              ? `Connected · ${result.site_url || "stub"}`
              : result.message}
          </div>
        )}
      </div>
    </div>
  );
}

function DocumentRow({
  doc,
  onSync,
  syncing,
}: {
  doc: SPDocument;
  onSync: (id: string) => void;
  syncing: boolean;
}) {
  return (
    <div className="px-5 py-4 flex items-center justify-between gap-4 hover:bg-[#f9fafb] transition-colors duration-200">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold text-[#0a1628] truncate">{doc.title}</div>
        <div className="font-mono text-[10px] tracking-wider text-[#6b7280] mt-1">
          {doc.author} · {formatModified(doc.modified)} · {formatBytes(doc.size_bytes)}
        </div>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <span className="font-mono text-[10px] tracking-widest uppercase border border-[#d1d5db] px-2 py-1 text-[#374151]">
          {DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type}
        </span>
        {doc.synced ? (
          <span className="font-mono text-[10px] tracking-widest uppercase border border-[#059669] text-[#065f46] bg-[#d1fae5] px-2 py-1">
            Synced
          </span>
        ) : (
          <button
            onClick={() => onSync(doc.id)}
            disabled={syncing}
            className="font-mono text-[10px] tracking-widest uppercase border border-[#0a1628] px-3 py-1 hover:bg-[#0a1628] hover:text-white disabled:opacity-40 transition-colors duration-200"
          >
            {syncing ? "Syncing…" : "Sync"}
          </button>
        )}
      </div>
    </div>
  );
}

function DocSkeleton() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <div key={i} className="px-5 py-4 animate-pulse flex justify-between gap-4">
          <div className="flex-1 space-y-2">
            <div className="h-3 bg-[#e5e7eb] w-48" />
            <div className="h-3 bg-[#e5e7eb] w-64" />
          </div>
          <div className="h-6 bg-[#e5e7eb] w-16 self-center" />
        </div>
      ))}
    </>
  );
}

// -- Page ---------------------------------------------------------------------

export default function SharePointPage() {
  const [stubMode, setStubMode] = useState(true);
  const [config, setConfig] = useState<Config>(DEFAULT_CONFIG);
  const [connection, setConnection] = useState<ConnectionResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [documents, setDocuments] = useState<SPDocument[]>([]);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncedCount, setSyncedCount] = useState(0);
  const [exportText, setExportText] = useState("");
  const [exportFilename, setExportFilename] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<{ message: string; web_url: string } | null>(null);

  const loadDocuments = useCallback(async (cfg = config) => {
    setLoading(true);
    try {
      const res = await api.sharepointDocuments({
        site_url: cfg.site_url,
        library_name: cfg.library_name,
      });
      setDocuments(res.documents);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    (async () => {
      try {
        const status = await api.sharepointStatus();
        setStubMode(status.stub_mode);
        setSyncedCount(status.synced_count);
      } catch {/* status is informational */}
      await loadDocuments();
    })();
  }, [loadDocuments]);

  const handleTest = async () => {
    setTesting(true);
    setError(null);
    try {
      const result = await api.sharepointConnect(config);
      setConnection({
        connected: result.connected,
        stub_mode: result.stub_mode,
        site_url: result.site_url,
        message: result.message,
      });
      if (result.connected) await loadDocuments(config);
    } catch (e) {
      setError(String(e));
    }
    setTesting(false);
  };

  const handleExport = async () => {
    if (!exportText.trim() || !exportFilename.trim()) return;
    setExporting(true);
    setExportResult(null);
    setError(null);
    try {
      const result = await api.sharepointExport({
        content: exportText,
        filename: exportFilename,
        folder: "NEXUS Drafts",
        ...config,
      });
      setExportResult({ message: result.message, web_url: result.web_url });
    } catch (e) {
      setError(String(e));
    }
    setExporting(false);
  };

  const handleSync = async (docId: string) => {
    setSyncing(docId);
    setError(null);
    try {
      await api.sharepointSync(docId, {
        site_url: config.site_url,
        library_name: config.library_name,
      });
      setDocuments((prev) =>
        prev.map((d) => (d.id === docId ? { ...d, synced: true } : d))
      );
      setSyncedCount((n) => n + 1);
    } catch (e) {
      setError(String(e));
    }
    setSyncing(null);
  };

  return (
    <div className="space-y-10">
      {/* Hero */}
      <div>
        <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] mb-2">
          Integration
        </div>
        <h1 className="text-4xl md:text-5xl font-bold tracking-tighter">
          SharePoint
        </h1>
        <p className="text-lg text-[#4b5563] mt-3 max-w-2xl">
          Connect your firm&apos;s document library for semantic search and AI
          classification inside NEXUS.
        </p>
      </div>

      {stubMode && <StubBanner />}

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <div className="border border-[#d1d5db] bg-white p-5">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
            Available
          </div>
          <div className="text-4xl font-bold tracking-tighter text-[#0a1628] mt-2">
            {documents.length}
          </div>
          <div className="font-mono text-[10px] tracking-wider text-[#6b7280] mt-1">
            documents in library
          </div>
        </div>
        <div className="border border-[#b08d57] bg-white p-5">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
            Synced
          </div>
          <div className="text-4xl font-bold tracking-tighter text-[#0a1628] mt-2">
            {syncedCount}
          </div>
          <div className="font-mono text-[10px] tracking-wider text-[#6b7280] mt-1">
            imported into NEXUS
          </div>
        </div>
        <div className="border border-[#d1d5db] bg-white p-5 col-span-2 md:col-span-1">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
            Mode
          </div>
          <div className="text-2xl font-bold tracking-tighter text-[#0a1628] mt-2">
            {stubMode ? "Preview" : "Live"}
          </div>
          <div className="font-mono text-[10px] tracking-wider text-[#6b7280] mt-1">
            {stubMode
              ? "mock data · Graph API not connected"
              : "Graph API active"}
          </div>
        </div>
      </div>

      {/* Connection form */}
      <ConnectionForm
        config={config}
        onChange={setConfig}
        onTest={handleTest}
        testing={testing}
        result={connection}
      />

      {/* Document list */}
      <div className="border border-[#d1d5db] bg-white">
        <div className="px-5 py-4 border-b border-[#e5e7eb] flex items-center justify-between">
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
            Library documents
          </span>
          <button
            onClick={() => loadDocuments()}
            className="font-mono text-[10px] tracking-widest uppercase text-[#0a1628] hover:text-[#b08d57] transition-colors duration-200"
          >
            Refresh →
          </button>
        </div>
        <div className="divide-y divide-[#f1f3f5]">
          {loading ? (
            <DocSkeleton />
          ) : documents.length === 0 ? (
            <div className="px-5 py-10 font-mono text-xs tracking-wider text-[#6b7280] text-center uppercase">
              No documents found — test connection or check library name.
            </div>
          ) : (
            documents.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                onSync={handleSync}
                syncing={syncing === doc.id}
              />
            ))
          )}
        </div>
      </div>

      {/* Export panel */}
      <div className="border border-[#d1d5db] bg-white p-6 space-y-4">
        <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
          Export draft to SharePoint
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <label className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-1">
              Draft content
            </label>
            <textarea
              rows={5}
              value={exportText}
              onChange={(e) => setExportText(e.target.value)}
              placeholder="Paste or type the draft text to upload…"
              className="w-full border border-[#d1d5db] px-3 py-2 text-sm bg-transparent focus:outline-none focus:border-[#0a1628] transition-colors duration-200 resize-none"
            />
          </div>
          <div className="space-y-4">
            <div>
              <label className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-1">
                Filename
              </label>
              <input
                type="text"
                value={exportFilename}
                onChange={(e) => setExportFilename(e.target.value)}
                placeholder="draft-2026-04.txt"
                className="w-full border border-[#d1d5db] px-3 py-2 text-sm bg-transparent focus:outline-none focus:border-[#0a1628] transition-colors duration-200"
              />
            </div>
            <button
              onClick={handleExport}
              disabled={exporting || !exportText.trim() || !exportFilename.trim()}
              className="w-full border border-[#0a1628] bg-[#0a1628] text-white px-6 py-2 font-mono text-xs tracking-widest uppercase hover:bg-[#b08d57] hover:border-[#b08d57] disabled:opacity-40 transition-colors duration-200"
            >
              {exporting ? "Uploading…" : "Upload to SharePoint"}
            </button>
            {exportResult && (
              <div className="font-mono text-[10px] tracking-wider text-[#065f46]">
                {exportResult.message}
                {exportResult.web_url && (
                  <a
                    href={exportResult.web_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block mt-1 text-[#b08d57] underline truncate"
                  >
                    Open in SharePoint →
                  </a>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="border border-[#dc2626] text-[#dc2626] px-6 py-4 font-mono text-xs tracking-wider">
          {error}
        </div>
      )}
    </div>
  );
}
