"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";

interface TimeEntry {
  id: string;
  matter: string | null;
  description: string;
  duration_minutes: number;
  value_chf: number;
  billable: boolean;
  timestamp: string;
  raw_transcript?: string;
}

interface TimeSummary {
  total_hours: number;
  total_value_chf: number;
  entry_count: number;
}

// MediaRecorder → Groq Whisper large-v3 hook.
type VoiceState = "idle" | "recording" | "processing";

function useVoiceTranscript() {
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [final, setFinal] = useState("");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = useCallback(async () => {
    setFinal("");
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/mp4";
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setVoiceState("processing");
        try {
          const blob = new Blob(chunksRef.current, { type: mimeType });
          const result = await api.transcribeAudio(blob);
          setFinal(result.transcript);
        } catch (e) {
          setVoiceError(String(e));
        } finally {
          setVoiceState("idle");
        }
      };
      recorderRef.current = recorder;
      recorder.start();
      setVoiceState("recording");
    } catch (e) {
      setVoiceError(String(e));
    }
  }, []);

  const stop = useCallback(() => {
    recorderRef.current?.stop();
    setVoiceState("processing");
  }, []);

  const reset = useCallback(() => {
    setFinal("");
    setVoiceError(null);
  }, []);

  return {
    listening: voiceState === "recording",
    processing: voiceState === "processing",
    interim: "",
    final,
    supported: true,
    start,
    stop,
    reset,
    setFinal,
    voiceError,
  };
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const hours = minutes / 60;
  return `${hours.toFixed(hours >= 10 ? 0 : 1)} hr`;
}

function formatTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function formatDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

// -- Entry detail modal -------------------------------------------------------

function EntryDetail({
  entry,
  onClose,
  onSaveMatter,
  onSaveTranscript,
}: {
  entry: TimeEntry;
  onClose: () => void;
  onSaveMatter: (id: string, matter: string) => void;
  onSaveTranscript: (id: string, transcript: string) => Promise<void>;
}) {
  const [matterDraft, setMatterDraft] = useState(entry.matter ?? "");
  const [transcriptDraft, setTranscriptDraft] = useState(entry.raw_transcript ?? "");
  const [savingTranscript, setSavingTranscript] = useState(false);
  const [transcriptSaved, setTranscriptSaved] = useState(false);

  const saveMatter = () => {
    const trimmed = matterDraft.trim();
    if (trimmed !== (entry.matter ?? "")) onSaveMatter(entry.id, trimmed);
  };

  const saveTranscript = async () => {
    setSavingTranscript(true);
    setTranscriptSaved(false);
    await onSaveTranscript(entry.id, transcriptDraft);
    setSavingTranscript(false);
    setTranscriptSaved(true);
    setTimeout(() => setTranscriptSaved(false), 2000);
  };

  const transcriptChanged = transcriptDraft !== (entry.raw_transcript ?? "");

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4"
      onClick={onClose}
    >
      <div
        className="bg-white w-full sm:max-w-xl max-h-[90vh] overflow-y-auto border border-[#d1d5db] sm:border-[#0a1628]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-[#f3f4f6]">
          <div>
            <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
              Time entry · {formatDate(entry.timestamp)}
            </div>
            <div className="text-2xl font-bold tracking-tighter mt-1">
              {formatTime(entry.timestamp)}
            </div>
          </div>
          <button
            onClick={onClose}
            className="font-mono text-xs text-[#9ca3af] hover:text-[#0a1628] transition-colors ml-4 mt-1"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Stats strip */}
          <div className="grid grid-cols-3 gap-4 border border-[#f3f4f6] bg-[#f9fafb] p-4">
            <div>
              <div className="font-mono text-[9px] tracking-widest uppercase text-[#6b7280]">Duration</div>
              <div className="text-lg font-bold tracking-tighter mt-0.5">
                {formatDuration(entry.duration_minutes)}
              </div>
            </div>
            <div>
              <div className="font-mono text-[9px] tracking-widest uppercase text-[#6b7280]">Status</div>
              <div className="mt-0.5">
                <span
                  className={`font-mono text-[10px] tracking-widest uppercase border px-2 py-0.5 ${
                    entry.billable
                      ? "border-[#059669] text-[#065f46] bg-[#d1fae5]"
                      : "border-[#d1d5db] text-[#4b5563]"
                  }`}
                >
                  {entry.billable ? "Billable" : "Non-billable"}
                </span>
              </div>
            </div>
            <div>
              <div className="font-mono text-[9px] tracking-widest uppercase text-[#6b7280]">Value</div>
              <div className="text-lg font-bold tracking-tighter text-[#065f46] mt-0.5">
                CHF {entry.value_chf.toFixed(0)}
              </div>
            </div>
          </div>

          {/* Matter (editable) */}
          <div>
            <label className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-2">
              Matter
            </label>
            <input
              value={matterDraft}
              onChange={(e) => setMatterDraft(e.target.value)}
              onBlur={saveMatter}
              onKeyDown={(e) => e.key === "Enter" && saveMatter()}
              placeholder="Click to tag a matter"
              className="w-full border border-[#d1d5db] px-3 py-2 text-sm focus:outline-none focus:border-[#059669] transition-colors"
            />
          </div>

          {/* AI summary (read-only) */}
          <div>
            <label className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-2">
              Summary
            </label>
            <div className="border border-[#f3f4f6] bg-[#f9fafb] px-3 py-2 text-sm text-[#374151] min-h-10">
              {entry.description || (
                <span className="italic text-[#9ca3af]">No summary generated.</span>
              )}
            </div>
          </div>

          {/* Raw transcript (editable) */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
                Voice transcript
              </label>
              <span className="font-mono text-[9px] tracking-wider text-[#9ca3af]">
                Edit to fix STT errors — acronyms, names, amounts
              </span>
            </div>
            <textarea
              value={transcriptDraft}
              onChange={(e) => setTranscriptDraft(e.target.value)}
              placeholder="No voice transcript recorded for this entry."
              rows={4}
              className="w-full border border-[#d1d5db] px-3 py-2 font-mono text-xs text-[#374151] resize-y bg-transparent focus:outline-none focus:border-[#059669] transition-colors"
            />
            <div className="flex justify-end mt-2">
              <button
                onClick={saveTranscript}
                disabled={savingTranscript || !transcriptChanged}
                className={`font-mono text-[10px] tracking-widest uppercase border px-4 py-1.5 transition-colors disabled:opacity-40 ${
                  transcriptSaved
                    ? "border-[#059669] bg-[#d1fae5] text-[#065f46]"
                    : "border-[#059669] text-[#065f46] hover:bg-[#d1fae5]"
                }`}
              >
                {savingTranscript ? "Saving…" : transcriptSaved ? "Saved ✓" : "Save transcript"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// -- Entry card ---------------------------------------------------------------

function EntryCard({
  entry,
  onSaveMatter,
  onSaveTranscript,
  onOpenDetail,
}: {
  entry: TimeEntry;
  onSaveMatter: (id: string, matter: string) => void;
  onSaveTranscript: (id: string, transcript: string) => Promise<void>;
  onOpenDetail: (entry: TimeEntry) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entry.matter ?? "");

  const save = () => {
    setEditing(false);
    const trimmed = draft.trim();
    if (trimmed && trimmed !== (entry.matter ?? "")) {
      onSaveMatter(entry.id, trimmed);
    }
  };

  return (
    <div className="border border-[#d1d5db] p-5 hover:border-[#059669] transition-colors duration-300">
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 md:col-span-5">
          {editing ? (
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={save}
              onKeyDown={(e) => e.key === "Enter" && save()}
              className="w-full border border-[#059669] px-2 py-1 text-sm font-bold"
            />
          ) : (
            <button
              onClick={() => setEditing(true)}
              className="text-left text-sm font-bold text-[#1a1a1a] hover:text-[#065f46] transition-colors duration-300"
            >
              {entry.matter || "Untagged matter — click to set"}
            </button>
          )}
          <p className="text-xs text-[#4b5563] mt-1">{entry.description}</p>
          <div className="flex items-center gap-3 mt-2">
            <span className="font-mono text-[10px] tracking-widest uppercase text-[#9ca3af]">
              {formatTime(entry.timestamp)}
            </span>
            <button
              onClick={() => onOpenDetail(entry)}
              className="font-mono text-[10px] tracking-widest uppercase text-[#9ca3af] hover:text-[#059669] transition-colors"
              title="View transcript and details"
            >
              {entry.raw_transcript ? "transcript ↗" : "details ↗"}
            </button>
          </div>
        </div>
        <div className="col-span-6 md:col-span-3 flex items-center">
          <span className="font-mono text-xs tracking-widest uppercase border border-[#d1d5db] px-3 py-1">
            {formatDuration(entry.duration_minutes)}
          </span>
        </div>
        <div className="col-span-6 md:col-span-2 flex items-center">
          <span
            className={`font-mono text-[10px] tracking-widest uppercase border px-2 py-1 ${
              entry.billable
                ? "border-[#059669] text-[#065f46] bg-[#d1fae5]"
                : "border-[#d1d5db] text-[#4b5563]"
            }`}
          >
            {entry.billable ? "Billable" : "Non-billable"}
          </span>
        </div>
        <div className="col-span-12 md:col-span-2 flex items-center justify-end">
          <span className="text-xl font-bold tracking-tighter text-[#065f46]">
            CHF {entry.value_chf.toFixed(0)}
          </span>
        </div>
      </div>
    </div>
  );
}

function VoiceButton({
  listening,
  processing,
  onToggle,
}: {
  listening: boolean;
  processing: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={processing}
      className={`w-24 h-24 rounded-full border-2 flex items-center justify-center transition-all duration-300 ${
        listening
          ? "border-[#059669] bg-[#059669] text-white animate-pulse"
          : processing
          ? "border-[#b08d57] bg-[#b08d57] text-white animate-pulse"
          : "border-[#d1d5db] hover:border-[#059669] hover:text-[#065f46]"
      }`}
      aria-label={listening ? "Stop recording" : processing ? "Transcribing…" : "Start recording"}
    >
      <span className="font-mono text-[10px] tracking-widest uppercase">
        {listening ? "Stop" : processing ? "Wait" : "Speak"}
      </span>
    </button>
  );
}

export default function TimePage() {
  const voice = useVoiceTranscript();
  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [summary, setSummary] = useState<TimeSummary | null>(null);
  const [typing, setTyping] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [lastLogged, setLastLogged] = useState<TimeEntry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detailEntry, setDetailEntry] = useState<TimeEntry | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [entriesRes, summaryRes] = await Promise.all([
        api.listTimeEntries(),
        api.timeSummary(),
      ]);
      setEntries(entriesRes.entries ?? []);
      setSummary(summaryRes);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (voice.voiceError) setError(voice.voiceError);
  }, [voice.voiceError]);

  const activeTranscript = useMemo(() => {
    return voice.final.trim() || typing.trim();
  }, [voice.final, typing]);

  const handleToggle = () => {
    if (voice.listening) voice.stop();
    else if (!voice.processing) void voice.start();
  };

  const handleLog = async () => {
    const text = activeTranscript;
    if (!text) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.captureTime(text);
      setLastLogged(result.entry ?? result);
      voice.reset();
      setTyping("");
      await refresh();
    } catch (e) {
      setError(String(e));
    }
    setSubmitting(false);
  };

  const handleSaveMatter = async (id: string, matter: string) => {
    try {
      await api.updateTimeMatter(id, matter);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleSaveTranscript = async (id: string, transcript: string) => {
    try {
      await api.updateTimeTranscript(id, transcript);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="space-y-12">
      {/* Entry detail modal */}
      {detailEntry && (
        <EntryDetail
          entry={detailEntry}
          onClose={() => setDetailEntry(null)}
          onSaveMatter={(id, matter) => {
            handleSaveMatter(id, matter);
            setDetailEntry((prev) => prev ? { ...prev, matter } : null);
          }}
          onSaveTranscript={async (id, transcript) => {
            await handleSaveTranscript(id, transcript);
            setDetailEntry((prev) => prev ? { ...prev, raw_transcript: transcript } : null);
          }}
        />
      )}

      {/* Hero */}
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 lg:col-span-3">
          <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] space-y-3">
            <div><span className="text-[#059669]">01</span><span className="ml-3">Speak</span></div>
            <div><span className="text-[#059669]">02</span><span className="ml-3">Parse</span></div>
            <div><span className="text-[#059669]">03</span><span className="ml-3">Bill</span></div>
          </div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
            Time<br />Capture
          </h2>
          <p className="text-lg text-[#4b5563] mt-4 max-w-xl">
            Voice-log billable time in under 15 seconds.
          </p>
        </div>
      </div>

      {/* Daily summary banner */}
      <div className="border border-[#059669] bg-[#d1fae5] px-8 py-6 flex flex-wrap items-center justify-between gap-4">
        <div className="font-mono text-xs tracking-widest uppercase text-[#065f46]">
          Today
        </div>
        <div className="flex items-center gap-8">
          <div>
            <div className="font-mono text-[10px] tracking-widest uppercase text-[#065f46]">
              Hours
            </div>
            <div className="text-3xl font-bold tracking-tighter text-[#065f46]">
              {summary ? summary.total_hours.toFixed(1) : "0.0"}
            </div>
          </div>
          <div>
            <div className="font-mono text-[10px] tracking-widest uppercase text-[#065f46]">
              Value
            </div>
            <div className="text-3xl font-bold tracking-tighter text-[#065f46]">
              CHF {summary ? summary.total_value_chf.toLocaleString("en-GB") : "0"}
            </div>
          </div>
          <div>
            <div className="font-mono text-[10px] tracking-widest uppercase text-[#065f46]">
              Entries
            </div>
            <div className="text-3xl font-bold tracking-tighter text-[#065f46]">
              {summary?.entry_count ?? 0}
            </div>
          </div>
        </div>
      </div>

      {/* Voice input */}
      <div className="border border-[#d1d5db] p-8 space-y-6">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
            Voice entry
          </span>
          <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
            Rate: CHF 450/hr <button className="ml-2 text-[#059669] hover:text-[#065f46]" aria-label="Edit rate">[edit]</button>
          </span>
        </div>
        <div className="flex flex-col items-center gap-6">
          <VoiceButton
            listening={voice.listening}
            processing={voice.processing}
            onToggle={handleToggle}
          />
          <div className="w-full border border-[#d1d5db] p-4 min-h-24 font-mono text-sm">
            {voice.final && <span className="text-[#1a1a1a]">{voice.final}</span>}
            {voice.processing && !voice.final && (
              <span className="text-[#b08d57] italic">Transcribing…</span>
            )}
            {!voice.final && !voice.processing && (
              <span className="text-[#9ca3af]">
                Press Speak and describe what you did, e.g. &ldquo;Spent 45 minutes
                drafting the Müller contract review&rdquo;.
              </span>
            )}
          </div>
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-2">
            Or type:
          </label>
          <textarea
            value={typing}
            onChange={(e) => setTyping(e.target.value)}
            placeholder="e.g. Spent 45 minutes drafting the Müller contract review"
            className="w-full border border-[#d1d5db] px-4 py-3 text-sm h-20 resize-none bg-transparent focus:outline-none focus:border-[#059669] transition-colors duration-300"
          />
        </div>
        <div className="flex justify-end">
          <button
            onClick={handleLog}
            disabled={submitting || !activeTranscript}
            className="border border-[#059669] bg-[#059669] text-white px-8 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#065f46] hover:border-[#065f46] disabled:opacity-40 transition-colors duration-300"
          >
            {submitting ? "Logging…" : "Log entry"}
          </button>
        </div>
      </div>

      {/* Last-logged confirmation card */}
      {lastLogged && (
        <div className="border-l-2 border-[#059669] pl-6 py-3">
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#065f46] block mb-1">
            Logged
          </span>
          <div className="text-sm text-[#1a1a1a]">
            <strong>{lastLogged.matter || "Untagged"}</strong> · {formatDuration(lastLogged.duration_minutes)} · CHF {lastLogged.value_chf.toFixed(0)}
          </div>
          <button
            onClick={() => setDetailEntry(lastLogged)}
            className="font-mono text-[10px] tracking-widest uppercase text-[#059669] hover:text-[#065f46] mt-1 transition-colors"
          >
            View transcript ↗
          </button>
        </div>
      )}

      {error && (
        <div className="border border-[#dc2626] text-[#dc2626] px-6 py-4 font-mono text-sm">
          {error}
        </div>
      )}

      {/* Time entries list */}
      <div>
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-2xl font-bold tracking-tighter">Entries</h3>
          <button
            onClick={refresh}
            className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] hover:text-[#065f46] transition-colors duration-300"
          >
            Refresh
          </button>
        </div>
        {entries.length > 0 ? (
          <div className="space-y-3">
            {entries.map((entry) => (
              <EntryCard
                key={entry.id}
                entry={entry}
                onSaveMatter={handleSaveMatter}
                onSaveTranscript={handleSaveTranscript}
                onOpenDetail={setDetailEntry}
              />
            ))}
          </div>
        ) : (
          <div className="border border-dashed border-[#d1d5db] p-12 text-center font-mono text-sm text-[#4b5563] tracking-widest uppercase">
            No time entries today. Start speaking to log your first entry.
          </div>
        )}
      </div>
    </div>
  );
}
