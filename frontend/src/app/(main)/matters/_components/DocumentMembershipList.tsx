"use client";

import { useState } from "react";
import {
  mattersClient,
  type MatterDocument,
  relativeTime,
} from "../_lib/matters-client";

interface DocumentMembershipListProps {
  matterId: string;
  documents?: MatterDocument[];
  onChanged: () => void;
}

// SRP: this component only manages the membership view. The data comes in
// already loaded (parent owns the list) and changes propagate up via
// onChanged() so the parent can refetch a single source of truth.
// Defensive default: `documents` is undefined briefly during refetch and
// for matters with no documents yet — render 0 attached, never crash.
export function DocumentMembershipList({
  matterId,
  documents = [],
  onChanged,
}: DocumentMembershipListProps) {
  const [docId, setDocId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = docId.trim();
    if (!trimmed) {
      setError("Document id is required");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await mattersClient.addDocumentToMatter(matterId, trimmed);
      setDocId("");
      onChanged();
    } catch (err) {
      setError(String(err));
    }
    setBusy(false);
  };

  const handleRemove = async (documentId: string) => {
    setBusy(true);
    setError(null);
    try {
      await mattersClient.removeDocumentFromMatter(matterId, documentId);
      onChanged();
    } catch (err) {
      setError(String(err));
    }
    setBusy(false);
  };

  return (
    <section
      aria-labelledby="documents-heading"
      data-testid="document-membership"
      className="border border-[#d1d5db] bg-white"
    >
      <div className="flex items-center justify-between border-b border-[#d1d5db] bg-[#fafafa] px-5 py-4">
        <h3
          id="documents-heading"
          className="font-mono text-xs tracking-widest uppercase text-[#4b5563]"
        >
          Documents
        </h3>
        <span className="font-mono text-[10px] tracking-widest uppercase text-[#9ca3af]">
          {documents.length} attached
        </span>
      </div>

      <form
        onSubmit={handleAdd}
        className="border-b border-[#d1d5db] px-5 py-4 flex flex-col md:flex-row gap-3"
      >
        <input
          type="text"
          value={docId}
          onChange={(e) => setDocId(e.target.value)}
          placeholder="Paste document id"
          aria-label="Document id"
          data-testid="add-document-input"
          className="flex-1 border border-[#d1d5db] bg-white px-3 py-3 text-base md:text-sm font-mono min-h-12 focus:outline-none focus:border-[#9a3412]"
        />
        <button
          type="submit"
          disabled={busy}
          data-testid="add-document-submit"
          className="border border-[#1a1a1a] bg-[#1a1a1a] text-white px-5 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#9a3412] hover:border-[#9a3412] disabled:opacity-50 transition-colors duration-300 min-h-12"
        >
          {busy ? "Working…" : "Attach"}
        </button>
      </form>

      {error && (
        <div
          role="alert"
          className="border-b border-[#d1d5db] px-5 py-3 font-mono text-xs text-[#dc2626]"
        >
          {error}
        </div>
      )}

      {documents.length === 0 ? (
        <div className="px-5 py-8 text-center font-mono text-xs tracking-widest uppercase text-[#9ca3af]">
          No documents attached
        </div>
      ) : (
        <ul role="list">
          {documents.map((doc) => (
            <li
              key={doc.document_id}
              data-testid="document-row"
              className="grid grid-cols-12 gap-3 px-5 py-4 border-b border-[#e5e7eb] last:border-b-0 items-center"
            >
              <div className="col-span-12 md:col-span-7 font-mono text-sm text-[#1a1a1a] break-all">
                {doc.document_id}
              </div>
              <div className="col-span-6 md:col-span-3 font-mono text-[10px] tracking-wider text-[#4b5563]">
                {relativeTime(doc.added_at)}
              </div>
              <div className="col-span-6 md:col-span-2 flex justify-end">
                <button
                  type="button"
                  onClick={() => handleRemove(doc.document_id)}
                  disabled={busy}
                  aria-label={`Remove ${doc.document_id}`}
                  data-testid="document-remove"
                  className="border border-[#d1d5db] px-3 py-2 font-mono text-[10px] tracking-widest uppercase text-[#4b5563] hover:border-[#dc2626] hover:text-[#dc2626] disabled:opacity-50 min-h-12 min-w-12"
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
