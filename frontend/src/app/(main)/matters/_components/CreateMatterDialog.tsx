"use client";

import { useEffect, useRef, useState } from "react";
import { mattersClient, type Matter } from "../_lib/matters-client";
import { VoiceMicButton } from "./VoiceMicButton";

interface CreateMatterDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (matter: Matter) => void;
}

// ESC/click-outside close + focus trap on the first input. The submit handler
// is async-aware (disables on submit, re-enables on error) so a slow backend
// never lets the user fire the same POST twice.
export function CreateMatterDialog({
  open,
  onClose,
  onCreated,
}: CreateMatterDialogProps) {
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    nameRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (open) {
      setName("");
      setClient("");
      setNotes("");
      setError(null);
      setSubmitting(false);
    }
  }, [open]);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await mattersClient.createMatter({
        name: name.trim(),
        client: client.trim() || undefined,
        notes: notes.trim() || undefined,
      });
      onCreated(created);
      onClose();
    } catch (err) {
      setError(String(err));
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end md:items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-matter-title"
    >
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
        aria-hidden="true"
      />
      <form
        onSubmit={handleSubmit}
        className="relative w-full md:max-w-xl bg-white border border-[#1a1a1a] p-6 md:p-8 max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-1">
              New record
            </div>
            <h2
              id="new-matter-title"
              className="text-2xl md:text-3xl font-bold tracking-tight text-[#1a1a1a]"
            >
              Open a matter
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="font-mono text-xs tracking-widest uppercase text-[#4b5563] hover:text-[#9a3412] min-h-12 min-w-12 px-3"
          >
            Close
          </button>
        </div>

        <div className="space-y-5">
          <FieldLabel
            id="matter-name"
            label="Name"
            required
            mic={
              <VoiceMicButton
                ariaLabel="Dictate name"
                disabled={submitting}
                onTranscript={(t) => setName(t)}
              />
            }
          >
            <input
              id="matter-name"
              ref={nameRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Helvetica Corp v. Schmidt"
              className="w-full border border-[#d1d5db] bg-white px-3 py-3 text-base md:text-sm min-h-12 focus:outline-none focus:border-[#9a3412]"
              required
            />
          </FieldLabel>

          <FieldLabel
            id="matter-client"
            label="Client (optional)"
            mic={
              <VoiceMicButton
                ariaLabel="Dictate client"
                disabled={submitting}
                onTranscript={(t) => setClient(t)}
              />
            }
          >
            <input
              id="matter-client"
              type="text"
              value={client}
              onChange={(e) => setClient(e.target.value)}
              placeholder="e.g. Helvetica Corp"
              className="w-full border border-[#d1d5db] bg-white px-3 py-3 text-base md:text-sm min-h-12 focus:outline-none focus:border-[#9a3412]"
            />
          </FieldLabel>

          <FieldLabel
            id="matter-notes"
            label="Notes (optional)"
            mic={
              <VoiceMicButton
                ariaLabel="Dictate notes"
                disabled={submitting}
                onTranscript={(t) =>
                  // Append for the notes field — operators often dictate context
                  // in multiple sentences; appending preserves prior thinking.
                  setNotes((prev) => (prev.trim() ? prev.trim() + " " + t : t))
                }
              />
            }
          >
            <textarea
              id="matter-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={4}
              placeholder="Internal context — visible to the assigned team only"
              className="w-full border border-[#d1d5db] bg-white px-3 py-3 text-base md:text-sm focus:outline-none focus:border-[#9a3412]"
            />
          </FieldLabel>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-4 border border-[#dc2626] text-[#dc2626] px-4 py-2 font-mono text-xs"
          >
            {error}
          </div>
        )}

        <div className="mt-8 flex flex-col-reverse md:flex-row md:justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="border border-[#d1d5db] px-6 py-3 font-mono text-xs tracking-widest uppercase text-[#4b5563] hover:border-[#1a1a1a] hover:text-[#1a1a1a] min-h-12"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            data-testid="create-matter-submit"
            className="border border-[#1a1a1a] bg-[#1a1a1a] text-white px-6 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#9a3412] hover:border-[#9a3412] disabled:opacity-50 transition-colors duration-300 min-h-12"
          >
            {submitting ? "Opening…" : "Open matter"}
          </button>
        </div>
      </form>
    </div>
  );
}

function FieldLabel({
  id,
  label,
  required,
  children,
  mic,
}: {
  id: string;
  label: string;
  required?: boolean;
  children: React.ReactNode;
  /** Optional voice-mic button rendered in the label row, right-aligned. */
  mic?: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-end justify-between mb-2 gap-2">
        <label
          htmlFor={id}
          className="block font-mono text-[10px] tracking-widest uppercase text-[#4b5563]"
        >
          {label}
          {required && <span className="text-[#9a3412] ml-1">*</span>}
        </label>
        {mic && <div className="shrink-0">{mic}</div>}
      </div>
      {children}
    </div>
  );
}
