"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface DocumentContent {
  id: string;
  filename: string;
  document_type: string;
  classification_confidence: number;
  parties: string[];
  dates: string[];
  summary: string;
  page_count: number;
  extraction_method: string;
  text: string;
  char_count: number;
}

interface RedactionResult {
  text: string;
  counts: Record<string, number>;
  span_count: number;
}

interface Props {
  docId: string | null;
  onClose: () => void;
}

export function DocumentViewer({ docId, onClose }: Props) {
  const [content, setContent] = useState<DocumentContent | null>(null);
  const [redaction, setRedaction] = useState<RedactionResult | null>(null);
  const [mode, setMode] = useState<"raw" | "redacted">("raw");
  const [loading, setLoading] = useState(false);
  const [redacting, setRedacting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = (await api.getDocumentContent(id)) as DocumentContent;
      setContent(result);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (docId) {
      load(docId);
      setMode("raw");
      setRedaction(null);
    }
  }, [docId, load]);

  const handleRedact = async () => {
    if (!docId) return;
    setRedacting(true);
    setError(null);
    try {
      const result = (await api.redactDocument(docId)) as RedactionResult;
      setRedaction(result);
      setMode("redacted");
    } catch (e) {
      setError(String(e));
    }
    setRedacting(false);
  };

  const handleExport = () => {
    if (!docId) return;
    window.open(api.downloadRedactedUrl(docId), "_blank");
  };

  if (!docId) return null;

  const displayText =
    mode === "redacted" && redaction ? redaction.text : content?.text || "";

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white border border-[#1a1a1a] max-w-5xl w-full max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-[#d1d5db] px-6 py-4 flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
              Document · {content?.document_type || "…"}
            </div>
            <h3 className="text-lg font-bold tracking-tight mt-1 truncate">
              {content?.filename || docId}
            </h3>
            {content && (
              <div className="font-mono text-[10px] tracking-wider text-[#6b7280] mt-1 flex flex-wrap gap-x-4">
                <span>{content.char_count} chars</span>
                <span>{content.page_count} pg</span>
                <span>{content.extraction_method}</span>
                <span>
                  conf {Math.round(content.classification_confidence * 100)}%
                </span>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="font-mono text-xs tracking-widest uppercase text-[#4b5563] hover:text-[#9a3412] transition-colors duration-300 shrink-0"
            aria-label="Close viewer"
          >
            Close ×
          </button>
        </div>

        {/* Toolbar */}
        <div className="border-b border-[#d1d5db] bg-[#fafafa] px-6 py-3 flex items-center gap-2 flex-wrap">
          <div className="inline-flex border border-[#d1d5db]">
            <button
              type="button"
              onClick={() => setMode("raw")}
              className={`font-mono text-[10px] tracking-widest uppercase px-4 py-1.5 ${
                mode === "raw"
                  ? "bg-[#1a1a1a] text-white"
                  : "text-[#4b5563] hover:text-[#9a3412]"
              }`}
            >
              Raw
            </button>
            <button
              type="button"
              onClick={() => {
                if (redaction) setMode("redacted");
                else handleRedact();
              }}
              disabled={redacting}
              className={`font-mono text-[10px] tracking-widest uppercase px-4 py-1.5 border-l border-[#d1d5db] disabled:opacity-50 ${
                mode === "redacted"
                  ? "bg-[#1a1a1a] text-white"
                  : "text-[#4b5563] hover:text-[#9a3412]"
              }`}
            >
              {redacting ? "Redacting…" : "Redacted"}
            </button>
          </div>

          {redaction && (
            <span className="font-mono text-[10px] tracking-wider text-[#4b5563]">
              {redaction.span_count} spans masked ·{" "}
              {Object.entries(redaction.counts)
                .map(([cat, n]) => `${cat}:${n}`)
                .join(" ")}
            </span>
          )}

          <button
            type="button"
            onClick={handleExport}
            className="ml-auto border border-[#1a1a1a] bg-white text-[#1a1a1a] px-4 py-1.5 font-mono text-[10px] tracking-widest uppercase hover:bg-[#1a1a1a] hover:text-white transition-colors duration-300"
          >
            Export redacted .txt
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto px-6 py-4">
          {loading && (
            <div className="font-mono text-xs text-[#4b5563]">Loading document…</div>
          )}
          {error && (
            <div className="border border-[#dc2626] text-[#dc2626] px-4 py-2 font-mono text-xs">
              {error}
            </div>
          )}
          {content && (
            <pre className="whitespace-pre-wrap break-words text-sm text-[#1a1a1a] leading-relaxed font-sans">
              {displayText}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
