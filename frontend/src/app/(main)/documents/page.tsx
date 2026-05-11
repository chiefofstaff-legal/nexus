"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { DocumentViewer } from "../DocumentViewer";

// -- Types -------------------------------------------------------------------

interface DocumentRecord {
  id: string;
  original_filename: string;
  filed_path: string;
  document_type: string;
  classification_confidence: number;
  parties: string[];
  dates: string[];
  matter_reference: string | null;
  jurisdiction: string | null;
  summary: string;
  page_count: number;
  extraction_method: string;
  chunk_count: number;
}

interface IngestProgress {
  total: number;
  completed: number;
  currentFile: string;
  currentType: string;
  currentConfidence: number;
  rate: number;
  eta: number;
  errors: number;
  recentFiles: Array<{ name: string; type: string; confidence: number; chunks: number }>;
  startedAt: number;
}

const TYPE_LABELS: Record<string, string> = {
  contract: "CONTRACT",
  nda: "NDA",
  brief: "BRIEF",
  court_filing: "COURT FILING",
  invoice: "INVOICE",
  correspondence: "CORRESPONDENCE",
  memorandum: "MEMO",
  other: "OTHER",
};

// -- Page --------------------------------------------------------------------

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [viewerDocId, setViewerDocId] = useState<string | null>(null);
  const [watchPath, setWatchPath] = useState("");
  const [ingestProgress, setIngestProgress] = useState<IngestProgress | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api
      .listDocuments()
      .then((r) => setDocuments(r.documents ?? []))
      .catch(() => { /* silent; empty state handles it */ });
  }, []);

  const handleMultiFileUpload = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    const arr = Array.from(files);
    setStatus(`Ingesting ${arr.length} file${arr.length > 1 ? "s" : ""}...`);
    const results: DocumentRecord[] = [];
    for (const file of arr) {
      try {
        const record = await api.uploadDocument(file);
        results.push(record);
        setStatus(`${results.length}/${arr.length} — ${file.name} → ${record.document_type}`);
      } catch (err) {
        setStatus(`Error on ${file.name}: ${err}`);
      }
    }
    setDocuments((prev) => mergeById(prev, results));
    setStatus(`${results.length} of ${arr.length} documents ingested`);
    setUploading(false);
  };

  const handleFolderIngest = () => {
    if (!watchPath.trim()) return;
    setLoading(true);
    setIngestProgress(null);
    setStatus("");
    abortRef.current = api.ingestFolderStream(
      watchPath.trim(),
      (data) => handleIngestEvent(data, setIngestProgress, setDocuments, setStatus, setLoading),
      () => setLoading(false),
      (err) => {
        setStatus(`Error: ${err}`);
        setLoading(false);
        setIngestProgress(null);
      },
    );
  };

  const handleCancelIngest = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    setIngestProgress(null);
    setStatus("Ingestion cancelled");
  };

  return (
    <div className="space-y-10">
      <PageHeading />

      <div className="grid grid-cols-12 gap-6">
        <UploadPanel
          onFiles={handleMultiFileUpload}
          uploading={uploading}
        />
        <FolderPanel
          watchPath={watchPath}
          setWatchPath={setWatchPath}
          onIngest={handleFolderIngest}
          loading={loading}
        />
      </div>

      {ingestProgress && (
        <IngestProgressCard
          progress={ingestProgress}
          onCancel={handleCancelIngest}
        />
      )}

      {status && !ingestProgress && <StatusStrip message={status} />}

      <DocumentGrid
        documents={documents}
        onOpen={(id) => setViewerDocId(id)}
      />

      <DocumentViewer
        docId={viewerDocId}
        onClose={() => setViewerDocId(null)}
      />
    </div>
  );
}

// -- Helpers -----------------------------------------------------------------

function mergeById(prev: DocumentRecord[], next: DocumentRecord[]): DocumentRecord[] {
  const map = new Map<string, DocumentRecord>();
  for (const d of prev) if (d.id) map.set(d.id, d);
  for (const d of next) if (d.id) map.set(d.id, d);
  return Array.from(map.values());
}

function handleIngestEvent(
  data: Record<string, unknown>,
  setProgress: React.Dispatch<React.SetStateAction<IngestProgress | null>>,
  setDocs: React.Dispatch<React.SetStateAction<DocumentRecord[]>>,
  setStatus: (s: string) => void,
  setLoading: (v: boolean) => void,
) {
  if (data.event === "start") {
    setProgress({
      total: data.total as number,
      completed: 0,
      currentFile: "",
      currentType: "",
      currentConfidence: 0,
      rate: 0,
      eta: 0,
      errors: 0,
      recentFiles: [],
      startedAt: Date.now(),
    });
    setStatus(`Scanning ${data.total} files...`);
  } else if (data.event === "progress") {
    setProgress((prev) => prev ? updateProgress(prev, data) : prev);
    const doc = data.document as DocumentRecord | undefined;
    if (doc?.id) setDocs((prev) => mergeById(prev, [doc]));
    setStatus(`${data.completed}/${data.total} — ${data.filename}`);
  } else if (data.event === "error") {
    setProgress((prev) => prev ? { ...prev, completed: data.completed as number, errors: prev.errors + 1 } : prev);
  } else if (data.event === "done") {
    setStatus(`Done: ${data.processed} processed, ${data.errors} errors in ${data.elapsed_seconds}s`);
    setLoading(false);
    setProgress(null);
  }
}

function updateProgress(prev: IngestProgress, data: Record<string, unknown>): IngestProgress {
  const doc = data.document as Record<string, unknown> | undefined;
  const chunks = (doc?.chunk_count as number) ?? 0;
  const recent = [
    {
      name: data.filename as string,
      type: data.document_type as string,
      confidence: data.confidence as number,
      chunks,
    },
    ...prev.recentFiles,
  ].slice(0, 5);
  return {
    ...prev,
    completed: data.completed as number,
    currentFile: data.filename as string,
    currentType: data.document_type as string,
    currentConfidence: data.confidence as number,
    rate: data.rate as number,
    eta: data.eta_seconds as number,
    recentFiles: recent,
  };
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s < 10 ? "0" : ""}${s}s`;
}

// -- Sections ----------------------------------------------------------------

function PageHeading() {
  return (
    <div>
      <div className="font-mono text-[10px] tracking-widest uppercase text-[#6b7280] mb-2">
        Library
      </div>
      <h2 className="text-4xl md:text-5xl font-bold tracking-tighter text-[#0a1628]">
        Documents
      </h2>
      <p className="text-sm md:text-base text-[#4b5563] mt-3 max-w-2xl">
        Upload, classify, and index. Any file type — multi-select enabled.
        Click a card to view or redact.
      </p>
    </div>
  );
}

function UploadPanel({
  onFiles,
  uploading,
}: {
  onFiles: (e: React.ChangeEvent<HTMLInputElement>) => void;
  uploading: boolean;
}) {
  return (
    <div className="col-span-12 md:col-span-5 border border-[#d1d5db] bg-white p-8">
      <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-5">
        Upload Files
      </span>
      <div className="space-y-3">
        <label className="block cursor-pointer group">
          <div className="border-2 border-dashed border-[#d1d5db] p-8 text-center group-hover:border-[#b08d57] transition-colors duration-300">
            <p className="font-mono text-sm tracking-wider uppercase text-[#4b5563]">
              Drop files or click
            </p>
            <p className="text-xs text-[#6b7280] mt-2">
              Multi-select enabled · any file type
            </p>
          </div>
          <input
            type="file"
            multiple
            onChange={onFiles}
            disabled={uploading}
            className="hidden"
          />
        </label>
        <label className="block cursor-pointer group">
          <div className="border border-dashed border-[#d1d5db] px-6 py-4 text-center group-hover:border-[#b08d57] transition-colors duration-300">
            <p className="font-mono text-xs tracking-wider uppercase text-[#4b5563]">
              Pick Folder
            </p>
            <p className="text-xs text-[#6b7280] mt-1">
              Uploads all files in a local folder
            </p>
          </div>
          <input
            type="file"
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            {...({ webkitdirectory: "" } as any)}
            onChange={onFiles}
            disabled={uploading}
            className="hidden"
          />
        </label>
      </div>
      {uploading && (
        <div className="mt-4 flex items-center gap-3">
          <span className="w-2 h-2 bg-[#b08d57] inline-block animate-pulse" />
          <span className="font-mono text-xs text-[#4b5563]">Processing...</span>
        </div>
      )}
    </div>
  );
}

function FolderPanel({
  watchPath,
  setWatchPath,
  onIngest,
  loading,
}: {
  watchPath: string;
  setWatchPath: (v: string) => void;
  onIngest: () => void;
  loading: boolean;
}) {
  return (
    <div className="col-span-12 md:col-span-7 border border-[#d1d5db] bg-white p-8">
      <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-5">
        Folder Ingest
      </span>
      <div className="flex gap-0">
        <input
          type="text"
          value={watchPath}
          onChange={(e) => setWatchPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onIngest()}
          placeholder="Enter server path: ~/Documents/legal/"
          className="flex-1 border border-[#d1d5db] px-4 py-3 text-sm font-mono bg-white text-[#0a1628] placeholder-[#9ca3af] focus:outline-none focus:border-[#b08d57] transition-colors duration-300"
        />
        <button
          onClick={onIngest}
          disabled={loading || !watchPath.trim()}
          className="bg-[#0a1628] text-white px-6 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#b08d57] disabled:opacity-30 transition-colors duration-300"
        >
          Ingest
        </button>
      </div>
      <p className="text-xs text-[#6b7280] mt-3">Server-side path — streams progress</p>
    </div>
  );
}

function IngestProgressCard({
  progress,
  onCancel,
}: {
  progress: IngestProgress;
  onCancel: () => void;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const update = () => setElapsed(Math.floor((Date.now() - progress.startedAt) / 1000));
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [progress.startedAt]);

  const pct = progress.total > 0 ? (progress.completed / progress.total) * 100 : 0;

  return (
    <div className="border border-[#d1d5db] bg-white p-8 space-y-5">
      {/* Header row */}
      <div className="flex items-start justify-between">
        <div>
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-1">
            Ingesting
          </span>
          <div className="font-mono text-3xl font-bold text-[#0a1628] leading-none">
            {progress.completed}
            <span className="text-lg text-[#9ca3af] font-normal"> / {progress.total}</span>
          </div>
        </div>
        <div className="flex items-start gap-6">
          <div className="text-right">
            <div className="font-mono text-[9px] tracking-widest uppercase text-[#9ca3af]">elapsed</div>
            <div className="font-mono text-sm font-bold text-[#4b5563]">{formatElapsed(elapsed)}</div>
          </div>
          <div className="text-right">
            <div className="font-mono text-[9px] tracking-widest uppercase text-[#9ca3af]">rate</div>
            <div className="font-mono text-sm font-bold text-[#4b5563]">
              {progress.rate > 0 ? `${progress.rate.toFixed(1)}/s` : "—"}
            </div>
          </div>
          {progress.eta > 0 && (
            <div className="text-right">
              <div className="font-mono text-[9px] tracking-widest uppercase text-[#9ca3af]">eta</div>
              <div className="font-mono text-sm font-bold text-[#4b5563]">{formatElapsed(Math.ceil(progress.eta))}</div>
            </div>
          )}
          <button
            onClick={onCancel}
            className="font-mono text-[10px] tracking-widest uppercase text-[#b08d57] hover:text-[#0a1628] transition-colors mt-1"
          >
            Cancel
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div>
        <div className="relative h-2 bg-[#e5e7eb] overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-[#b08d57] transition-all duration-500 ease-out"
            style={{ width: `${pct}%` }}
          />
          {pct > 0 && pct < 100 && (
            <div
              className="absolute inset-y-0 bg-white/20 animate-pulse"
              style={{ left: `${pct - 5}%`, width: "10%" }}
            />
          )}
        </div>
        <div className="flex justify-between font-mono text-[9px] text-[#9ca3af] mt-1">
          <span>{pct.toFixed(1)}%</span>
          <span>{progress.total - progress.completed} remaining</span>
        </div>
      </div>

      {/* Currently processing */}
      {progress.currentFile && (
        <div className="flex items-start gap-3 border-t border-[#e5e7eb] pt-4">
          <span className="w-1.5 h-1.5 bg-[#b08d57] rounded-full animate-pulse mt-1.5 flex-shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="font-mono text-xs text-[#0a1628] truncate">{progress.currentFile}</div>
            <div className="flex items-center gap-3 mt-1.5">
              {progress.currentType && (
                <span className="font-mono text-[9px] tracking-widest uppercase border border-[#d1d5db] px-2 py-0.5 text-[#374151]">
                  {TYPE_LABELS[progress.currentType] || "OTHER"}
                </span>
              )}
              {progress.currentConfidence > 0 && (
                <span className="font-mono text-[10px] text-[#6b7280]">
                  {(progress.currentConfidence * 100).toFixed(0)}% confidence
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Recent files */}
      {progress.recentFiles.length > 0 && (
        <div className="border-t border-[#e5e7eb] pt-4">
          <span className="font-mono text-[9px] tracking-widest uppercase text-[#9ca3af] block mb-3">
            Completed
          </span>
          <div className="space-y-2">
            {progress.recentFiles.map((f, i) => (
              <div
                key={`${f.name}-${i}`}
                className={`flex items-center gap-3 font-mono text-xs transition-opacity duration-300 ${
                  i === 0 ? "opacity-100" : "opacity-40"
                }`}
              >
                <span className="tracking-widest uppercase border border-[#e5e7eb] px-2 py-0.5 min-w-[72px] text-center text-[9px] text-[#374151] flex-shrink-0">
                  {TYPE_LABELS[f.type] || "OTHER"}
                </span>
                <span className="truncate flex-1 text-[#4b5563]">{f.name}</span>
                <span className="text-[#9ca3af] flex-shrink-0">{(f.confidence * 100).toFixed(0)}%</span>
                {f.chunks > 0 && (
                  <span className="text-[#9ca3af] flex-shrink-0 text-[9px]">{f.chunks} ch</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {progress.errors > 0 && (
        <div className="font-mono text-xs text-[#dc2626] border-t border-[#e5e7eb] pt-3">
          {progress.errors} error{progress.errors !== 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}

function StatusStrip({ message }: { message: string }) {
  return (
    <div className="font-mono text-xs tracking-wider text-[#374151] border-l-2 border-[#b08d57] pl-5 py-2">
      {message}
    </div>
  );
}

function DocumentGrid({
  documents,
  onOpen,
}: {
  documents: DocumentRecord[];
  onOpen: (id: string) => void;
}) {
  if (documents.length === 0) {
    return (
      <div className="border border-dashed border-[#d1d5db] p-12 text-center font-mono text-xs text-[#6b7280] tracking-widest uppercase">
        No documents yet — upload files or ingest a folder.
      </div>
    );
  }
  return (
    <div>
      <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-5">
        Classified Documents — {documents.length}
      </span>
      <div className="grid grid-cols-12 gap-5">
        {documents.map((doc, i) => (
          <DocumentCard key={doc.id} doc={doc} index={i} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}

function DocumentCard({
  doc,
  index,
  onOpen,
}: {
  doc: DocumentRecord;
  index: number;
  onOpen: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(doc.id)}
      className="col-span-12 md:col-span-6 lg:col-span-4 border border-[#d1d5db] bg-white p-5 hover:border-[#b08d57] transition-colors duration-300 group text-left cursor-pointer"
    >
      <div className="flex items-start justify-between mb-3">
        <span className="font-mono text-2xl font-bold text-[#b08d57]">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span className="font-mono text-[10px] tracking-widest uppercase border border-[#d1d5db] px-2 py-1 text-[#374151] group-hover:border-[#b08d57] transition-colors duration-300">
          {TYPE_LABELS[doc.document_type] || "OTHER"}
        </span>
      </div>
      <h4 className="font-bold text-sm text-[#0a1628] tracking-tight truncate mb-2">
        {doc.original_filename}
      </h4>
      <div className="font-mono text-[10px] tracking-wider text-[#4b5563] space-y-1">
        <div>
          Confidence{" "}
          <span className="text-[#0a1628] text-xs font-bold">
            {(doc.classification_confidence * 100).toFixed(0)}%
          </span>
        </div>
        {doc.parties.length > 0 && (
          <div className="truncate">
            Parties <span className="text-[#374151]">{doc.parties.join(" | ")}</span>
          </div>
        )}
        <div>
          {doc.page_count} pg · {doc.chunk_count} chunks
        </div>
      </div>
      {doc.summary && (
        <p className="text-xs text-[#374151] mt-3 leading-relaxed whitespace-pre-wrap break-words line-clamp-4">
          {doc.summary}
        </p>
      )}
      <div className="mt-3 font-mono text-[9px] tracking-widest uppercase text-[#9ca3af] group-hover:text-[#b08d57] transition-colors">
        Click to view / redact →
      </div>
    </button>
  );
}
