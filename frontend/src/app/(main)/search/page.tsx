"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { SearchModeToggle, type SearchMode, type SearchLang } from "@/components/SearchModeToggle";

// -- Types --------------------------------------------------------------------

interface SearchHit {
  text: string;
  metadata: {
    doc_id?: string;
    filename?: string;
    document_type?: string;
    chunk_index?: number;
    total_chunks?: number;
  };
  distance: number;
  relevance: number;
}

interface SearchResult {
  query: string;
  results: SearchHit[];
  total: number;
}

// -- Helpers ------------------------------------------------------------------

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

function relevanceColour(r: number): string {
  if (r >= 0.8) return "bg-[#059669]";
  if (r >= 0.6) return "bg-[#b08d57]";
  return "bg-[#9ca3af]";
}

function excerpt(text: string, maxChars = 280): string {
  if (text.length <= maxChars) return text;
  return text.slice(0, maxChars).trimEnd() + "…";
}

// -- Primitives ---------------------------------------------------------------

function RelevanceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 bg-[#e5e7eb] rounded-full overflow-hidden">
        <div
          className={`h-full ${relevanceColour(value)} rounded-full`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-[10px] tracking-wider text-[#6b7280] w-9 text-right">
        {pct}%
      </span>
    </div>
  );
}

function HitCard({ hit, query }: { hit: SearchHit; query: string }) {
  const [expanded, setExpanded] = useState(false);
  const filename = hit.metadata.filename || "Untitled document";
  const docType = DOC_TYPE_LABELS[hit.metadata.document_type ?? ""] ?? hit.metadata.document_type ?? "Other";
  const docId = hit.metadata.doc_id;
  const chunkInfo =
    hit.metadata.chunk_index !== undefined
      ? `Chunk ${hit.metadata.chunk_index + 1} / ${hit.metadata.total_chunks}`
      : null;

  return (
    <div className="border border-[#d1d5db] bg-white p-5 space-y-3 hover:border-[#0a1628] transition-colors duration-200">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          {docId ? (
            <a
              href={`/documents?highlight=${encodeURIComponent(docId)}`}
              className="text-sm font-bold text-[#0a1628] truncate block hover:text-[#b08d57] transition-colors duration-200"
              title={`Open ${filename} in Documents`}
            >
              {filename} ↗
            </a>
          ) : (
            <div className="text-sm font-bold text-[#0a1628] truncate">{filename}</div>
          )}
          <div className="font-mono text-[10px] tracking-wider text-[#6b7280] mt-0.5">
            {chunkInfo && `${chunkInfo} · `}{docType}
          </div>
        </div>
        <span className="shrink-0 font-mono text-[10px] tracking-widest uppercase border border-[#d1d5db] px-2 py-1 text-[#374151]">
          {docType}
        </span>
      </div>

      <RelevanceBar value={hit.relevance} />

      <p className="text-sm text-[#374151] leading-relaxed break-words overflow-hidden">
        {expanded ? hit.text : excerpt(hit.text)}
      </p>

      <div className="flex items-center justify-between">
        {hit.text.length > 280 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="font-mono text-[10px] tracking-widest uppercase text-[#0a1628] hover:text-[#b08d57] transition-colors duration-200"
          >
            {expanded ? "Show less" : "Show more"}
          </button>
        )}
        {docId && (
          <span className="font-mono text-[9px] tracking-wider text-[#9ca3af] ml-auto">
            cite: {docId.startsWith("corpus_") ? docId.replace("corpus_", "") : docId}
          </span>
        )}
      </div>
    </div>
  );
}

function ResultSkeleton() {
  return (
    <div className="space-y-4">
      {[0, 1, 2].map((i) => (
        <div key={i} className="border border-[#d1d5db] bg-white p-5 animate-pulse space-y-3">
          <div className="h-4 bg-[#e5e7eb] w-48" />
          <div className="h-1 bg-[#e5e7eb] w-full" />
          <div className="space-y-2">
            <div className="h-3 bg-[#e5e7eb] w-full" />
            <div className="h-3 bg-[#e5e7eb] w-5/6" />
            <div className="h-3 bg-[#e5e7eb] w-4/6" />
          </div>
        </div>
      ))}
    </div>
  );
}

// -- Page ---------------------------------------------------------------------

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<{ total_chunks: number } | null>(null);
  const [nResults, setNResults] = useState(8);
  const [searchMode, setSearchMode] = useState<SearchMode>("semantic");
  const [searchLang, setSearchLang] = useState<SearchLang>("en");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.searchStats().then(setStats).catch(() => null);
    inputRef.current?.focus();
  }, []);

  const handleSearch = useCallback(async (q = query, n = nResults, mode = searchMode, lang = searchLang) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.searchDocuments(trimmed, n, mode, lang);
      setResult(res as SearchResult);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [query, nResults, searchMode, searchLang]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") void handleSearch();
  };

  return (
    <div className="space-y-10 overflow-x-hidden">
      {/* Hero */}
      <div>
        <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] mb-2">
          Semantic lookup
        </div>
        <h1 className="text-4xl md:text-5xl font-bold tracking-tighter">
          Search
        </h1>
        <p className="text-lg text-[#4b5563] mt-3 max-w-2xl">
          Find obligations, clauses, and parties by concept — not by exact phrase.
          Searches meaning across the full corpus. Ask it in plain language; it returns
          the relevant passages ranked by semantic proximity.
        </p>
      </div>

      {/* Stats */}
      {stats && (
        <div className="flex items-center gap-2 font-mono text-xs tracking-widest uppercase text-[#4b5563]">
          <span className="w-2 h-2 bg-[#059669] inline-block rounded-full" />
          {stats.total_chunks.toLocaleString()} chunks indexed
        </div>
      )}
      {stats?.total_chunks === 0 && (
        <div className="border border-[#b08d57] bg-[#fffbf0] px-6 py-4 font-mono text-xs tracking-wider text-[#92400e]">
          No corpus indexed. Upload documents on the{" "}
          <a href="/documents" className="underline hover:text-[#9a3412]">Documents page</a>{" "}
          — or wait a moment while the demo corpus seeds automatically.
        </div>
      )}

      {/* Search bar */}
      <div className="flex flex-col gap-3 w-full">
      <SearchModeToggle
        mode={searchMode}
        lang={searchLang}
        onChange={({ mode, lang }) => { setSearchMode(mode); setSearchLang(lang); }}
        disabled={loading}
      />
      <div className="flex flex-col sm:flex-row gap-2 sm:gap-3 w-full">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="e.g. confidentiality obligations under Swiss law"
          className="min-w-0 flex-1 border border-[#d1d5db] px-4 py-3 text-sm bg-transparent focus:outline-none focus:border-[#0a1628] transition-colors duration-200"
          disabled={loading}
        />
        <div className="flex gap-2 sm:gap-3 shrink-0">
          <select
            value={nResults}
            onChange={(e) => setNResults(Number(e.target.value))}
            className="border border-[#d1d5db] px-3 py-3 text-sm bg-white font-mono focus:outline-none focus:border-[#0a1628] transition-colors duration-200"
          >
            {[5, 8, 10, 20].map((n) => (
              <option key={n} value={n}>{n} results</option>
            ))}
          </select>
          <button
            onClick={() => void handleSearch()}
            disabled={loading || !query.trim()}
            className="flex-1 sm:flex-none border border-[#0a1628] bg-[#0a1628] text-white px-6 sm:px-8 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#b08d57] hover:border-[#b08d57] disabled:opacity-40 transition-colors duration-200"
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </div>
      </div>
      </div>

      {/* Error */}
      {error && (
        <div className="border border-[#dc2626] text-[#dc2626] px-6 py-4 font-mono text-xs tracking-wider">
          {error}
        </div>
      )}

      {/* Results */}
      {loading && <ResultSkeleton />}

      {!loading && result && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
              {result.total} result{result.total !== 1 ? "s" : ""} for &ldquo;{result.query}&rdquo;
            </span>
          </div>

          {result.results.length === 0 ? (
            <div className="border border-dashed border-[#d1d5db] p-12 text-center font-mono text-sm text-[#4b5563] tracking-widest uppercase">
              No matching passages — try a broader or different phrasing.
            </div>
          ) : (
            result.results.map((hit, i) => (
              <HitCard key={i} hit={hit} query={result.query} />
            ))
          )}
        </div>
      )}

      {!loading && !result && (
        <div className="border border-dashed border-[#d1d5db] p-12 text-center font-mono text-sm text-[#4b5563] tracking-widest uppercase">
          Enter a query to search across all indexed documents.
        </div>
      )}
    </div>
  );
}
