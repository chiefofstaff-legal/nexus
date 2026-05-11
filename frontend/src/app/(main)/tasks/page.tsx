"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";

interface Task {
  id: string;
  title: string;
  description?: string;
  assignee: string;
  matter?: string;
  deadline?: string;
  priority: "high" | "medium" | "low" | string;
  status: "pending" | "in_progress" | "done" | string;
  created_at?: string;
  raw_transcript?: string;
}

type DelegatePreview = {
  title: string;
  assignee: string;
  deadline?: string;
  matter?: string;
  priority?: string;
  description?: string;
  raw_transcript?: string;
};

const COLUMNS: Array<{ key: Task["status"]; label: string }> = [
  { key: "pending", label: "Pending" },
  { key: "in_progress", label: "In progress" },
  { key: "done", label: "Done" },
];

const PRIORITY_DOT: Record<string, string> = {
  high: "bg-[#dc2626]",
  medium: "bg-[#f59e0b]",
  low: "bg-[#9ca3af]",
};

// MediaRecorder → Groq Whisper hook (mirrors time/page.tsx).
// Web Speech API removed — silently blocked by Brave's privacy shields.
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
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setVoiceState("processing");
        try {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
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
          ? "border-[#4f46e5] bg-[#4f46e5] text-white animate-pulse"
          : processing
          ? "border-[#b08d57] bg-[#b08d57] text-white animate-pulse"
          : "border-[#d1d5db] hover:border-[#4f46e5] hover:text-[#3730a3]"
      }`}
      aria-label={listening ? "Stop recording" : processing ? "Transcribing…" : "Start recording"}
    >
      <span className="font-mono text-[10px] tracking-widest uppercase">
        {listening ? "Stop" : processing ? "Wait" : "Speak"}
      </span>
    </button>
  );
}

function PreviewCard({
  preview,
  onConfirm,
  onEdit,
  onCancel,
  editing,
  setEditing,
  onEditChange,
}: {
  preview: DelegatePreview;
  onConfirm: () => void;
  onEdit: () => void;
  onCancel: () => void;
  editing: boolean;
  setEditing: (b: boolean) => void;
  onEditChange: (patch: Partial<DelegatePreview>) => void;
}) {
  if (editing) {
    return (
      <div className="border border-[#4f46e5] bg-[#eef2ff] p-6 space-y-3">
        <div className="font-mono text-xs tracking-widest uppercase text-[#3730a3]">
          Edit draft
        </div>
        {(["title", "assignee", "matter", "deadline", "priority"] as const).map((f) => (
          <div key={f} className="grid grid-cols-4 gap-3 items-center">
            <label className="font-mono text-[10px] tracking-widest uppercase text-[#3730a3]">
              {f}
            </label>
            <input
              value={(preview[f] as string) ?? ""}
              onChange={(e) => onEditChange({ [f]: e.target.value })}
              className="col-span-3 border border-[#d1d5db] bg-white px-2 py-1 text-sm"
            />
          </div>
        ))}
        {/* Transcript editing in edit mode */}
        <div className="grid grid-cols-4 gap-3 items-start">
          <label className="font-mono text-[10px] tracking-widest uppercase text-[#3730a3] pt-1">
            Transcript
          </label>
          <textarea
            value={preview.raw_transcript ?? ""}
            onChange={(e) => onEditChange({ raw_transcript: e.target.value })}
            className="col-span-3 border border-[#d1d5db] bg-white px-2 py-1 text-sm font-mono resize-none h-20"
            placeholder="Original voice transcript (correct STT errors here)"
          />
        </div>
        <div className="flex gap-3 justify-end">
          <button
            onClick={() => setEditing(false)}
            className="border border-[#d1d5db] px-4 py-1.5 font-mono text-xs tracking-widest uppercase"
          >
            Back
          </button>
          <button
            onClick={onConfirm}
            className="border border-[#4f46e5] bg-[#4f46e5] text-white px-6 py-1.5 font-mono text-xs tracking-widest uppercase hover:bg-[#3730a3]"
          >
            Confirm
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="border border-[#4f46e5] bg-[#eef2ff] p-6 space-y-4">
      {/* Raw transcript strip — always shown so lawyers can spot STT errors immediately */}
      {preview.raw_transcript && (
        <div>
          <div className="font-mono text-[10px] tracking-widest uppercase text-[#3730a3] mb-1">
            Voice transcript
          </div>
          <div className="font-mono text-xs text-[#4b5563] bg-white border border-[#c7d2fe] px-3 py-2 italic leading-relaxed">
            &ldquo;{preview.raw_transcript}&rdquo;
          </div>
        </div>
      )}
      <div>
        <div className="font-mono text-xs tracking-widest uppercase text-[#3730a3] mb-3">
          Parsed task
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
          <div>
            <div className="font-mono text-[10px] uppercase text-[#3730a3]">Who</div>
            <div className="text-[#1a1a1a] font-bold">{preview.assignee || "—"}</div>
          </div>
          <div className="col-span-2">
            <div className="font-mono text-[10px] uppercase text-[#3730a3]">What</div>
            <div className="text-[#1a1a1a] font-bold">{preview.title || "—"}</div>
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase text-[#3730a3]">When</div>
            <div className="text-[#1a1a1a]">{preview.deadline || "—"}</div>
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase text-[#3730a3]">Matter</div>
            <div className="text-[#1a1a1a]">{preview.matter || "—"}</div>
          </div>
        </div>
      </div>
      <div className="flex gap-3 justify-end">
        <button
          onClick={onCancel}
          className="border border-[#d1d5db] px-4 py-1.5 font-mono text-xs tracking-widest uppercase hover:border-[#dc2626] hover:text-[#dc2626]"
        >
          Discard
        </button>
        <button
          onClick={onEdit}
          className="border border-[#d1d5db] px-4 py-1.5 font-mono text-xs tracking-widest uppercase hover:border-[#4f46e5] hover:text-[#3730a3]"
        >
          Edit
        </button>
        <button
          onClick={onConfirm}
          className="border border-[#4f46e5] bg-[#4f46e5] text-white px-6 py-1.5 font-mono text-xs tracking-widest uppercase hover:bg-[#3730a3]"
        >
          Confirm
        </button>
      </div>
    </div>
  );
}

function TaskCard({
  task,
  onStatusChange,
  onSaveTranscript,
}: {
  task: Task;
  onStatusChange: (id: string, status: string) => void;
  onSaveTranscript: (id: string, transcript: string) => Promise<void>;
}) {
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [transcriptDraft, setTranscriptDraft] = useState(task.raw_transcript ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSaveTranscript(task.id, transcriptDraft);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-[#d1d5db] bg-white p-4 space-y-2 hover:border-[#4f46e5] transition-colors duration-300">
      <div className="flex items-start gap-2">
        <span
          className={`w-2 h-2 rounded-full inline-block mt-1.5 flex-shrink-0 ${
            PRIORITY_DOT[task.priority] ?? "bg-[#9ca3af]"
          }`}
          aria-label={`Priority ${task.priority}`}
        />
        <div className="flex-1 text-sm font-bold text-[#1a1a1a] leading-snug">
          {task.title}
        </div>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <span className="font-mono text-[10px] tracking-widest uppercase border border-[#4f46e5] text-[#3730a3] bg-[#e0e7ff] px-2 py-0.5">
          {task.assignee}
        </span>
        {task.matter && (
          <span className="font-mono text-[10px] tracking-widest uppercase border border-[#d1d5db] text-[#4b5563] px-2 py-0.5">
            {task.matter}
          </span>
        )}
      </div>
      {task.deadline && (
        <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
          Due {task.deadline}
        </div>
      )}
      {/* Transcript toggle link */}
      <button
        onClick={() => setTranscriptOpen((o) => !o)}
        className="font-mono text-[10px] tracking-widest uppercase text-[#9ca3af] hover:text-[#4f46e5] transition-colors"
        title={task.raw_transcript ? "View/edit voice transcript" : "No transcript recorded"}
      >
        {task.raw_transcript
          ? transcriptOpen ? "transcript ↙" : "transcript ↗"
          : "no transcript"}
      </button>
      {/* Expandable transcript panel */}
      {transcriptOpen && (
        <div className="border-t border-[#e5e7eb] pt-3 space-y-2">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[#9ca3af] mb-1">
            Voice transcript
          </div>
          <textarea
            value={transcriptDraft}
            onChange={(e) => {
              setTranscriptDraft(e.target.value);
              setSaved(false);
            }}
            className="w-full border border-[#d1d5db] px-2 py-2 font-mono text-xs text-[#4b5563] resize-none h-20 focus:outline-none focus:border-[#4f46e5] transition-colors"
            placeholder="No transcript recorded"
          />
          <div className="flex justify-end">
            <button
              onClick={handleSave}
              disabled={saving}
              className={`font-mono text-[10px] tracking-widest uppercase px-3 py-1 border transition-colors ${
                saved
                  ? "border-[#059669] text-[#059669]"
                  : "border-[#4f46e5] text-[#4f46e5] hover:bg-[#4f46e5] hover:text-white"
              }`}
            >
              {saved ? "Saved ✓" : saving ? "Saving…" : "Save transcript"}
            </button>
          </div>
        </div>
      )}
      <select
        value={task.status}
        onChange={(e) => onStatusChange(task.id, e.target.value)}
        className="w-full border border-[#d1d5db] bg-white px-2 py-1 font-mono text-[10px] tracking-widest uppercase"
      >
        {COLUMNS.map((c) => (
          <option key={c.key} value={c.key}>
            {c.label}
          </option>
        ))}
      </select>
    </div>
  );
}

interface Filters {
  assignee: string;
  matter: string;
  status: string;
}

function FilterBar({
  filters,
  setFilters,
  assignees,
  matters,
}: {
  filters: Filters;
  setFilters: (f: Filters) => void;
  assignees: string[];
  matters: string[];
}) {
  return (
    <div className="flex flex-wrap gap-3 items-center">
      <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
        Filter
      </span>
      <select
        value={filters.assignee}
        onChange={(e) => setFilters({ ...filters, assignee: e.target.value })}
        className="border border-[#d1d5db] bg-white px-2 py-1 font-mono text-xs"
      >
        <option value="">All assignees</option>
        {assignees.map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </select>
      <select
        value={filters.matter}
        onChange={(e) => setFilters({ ...filters, matter: e.target.value })}
        className="border border-[#d1d5db] bg-white px-2 py-1 font-mono text-xs"
      >
        <option value="">All matters</option>
        {matters.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
      <select
        value={filters.status}
        onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        className="border border-[#d1d5db] bg-white px-2 py-1 font-mono text-xs"
      >
        <option value="">All statuses</option>
        {COLUMNS.map((c) => (
          <option key={c.key} value={c.key}>
            {c.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function TasksPage() {
  const voice = useVoiceTranscript();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [assignees, setAssignees] = useState<string[]>([]);
  const [typing, setTyping] = useState("");
  const [preview, setPreview] = useState<DelegatePreview | null>(null);
  const [editing, setEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({ assignee: "", matter: "", status: "" });

  const refresh = useCallback(async () => {
    try {
      const [taskRes, assigneeRes] = await Promise.all([
        api.listTasks(),
        api.listAssignees(),
      ]);
      setTasks(taskRes.tasks ?? []);
      setAssignees(assigneeRes.assignees ?? []);
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

  const matters = useMemo(() => {
    const set = new Set<string>();
    tasks.forEach((t) => t.matter && set.add(t.matter));
    return Array.from(set).sort();
  }, [tasks]);

  const filteredTasks = useMemo(() => {
    return tasks.filter(
      (t) =>
        (!filters.assignee || t.assignee === filters.assignee) &&
        (!filters.matter || t.matter === filters.matter) &&
        (!filters.status || t.status === filters.status),
    );
  }, [tasks, filters]);

  const handleDelegate = async () => {
    const text = activeTranscript;
    if (!text) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.delegateTask(text);
      const parsed = result.parsed ?? result;
      // Preserve the raw STT transcript — fall back to the text the user spoke
      setPreview({
        ...parsed,
        raw_transcript: parsed.raw_transcript ?? text,
      });
      voice.reset();
      setTyping("");
    } catch (e) {
      setError(String(e));
    }
    setSubmitting(false);
  };

  const handleConfirm = async () => {
    if (!preview) return;
    try {
      await api.createTask({
        title: preview.title,
        description: preview.description,
        assignee: preview.assignee,
        matter: preview.matter,
        deadline: preview.deadline,
        priority: preview.priority,
        raw_transcript: preview.raw_transcript,
      });
      setPreview(null);
      setEditing(false);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleStatusChange = async (id: string, status: string) => {
    try {
      await api.updateTaskStatus(id, status);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleSaveTaskTranscript = async (id: string, transcript: string) => {
    try {
      await api.updateTaskTranscript(id, transcript);
      // Optimistic update — avoids a full refresh for a simple text correction
      setTasks((prev) =>
        prev.map((t) => (t.id === id ? { ...t, raw_transcript: transcript } : t)),
      );
    } catch (e) {
      setError(String(e));
      throw e;
    }
  };

  return (
    <div className="space-y-12">
      {/* Hero */}
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 lg:col-span-3">
          <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] space-y-3">
            <div><span className="text-[#4f46e5]">01</span><span className="ml-3">Speak</span></div>
            <div><span className="text-[#4f46e5]">02</span><span className="ml-3">Parse</span></div>
            <div><span className="text-[#4f46e5]">03</span><span className="ml-3">Delegate</span></div>
          </div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
            Delegation
          </h2>
          <p className="text-lg text-[#4b5563] mt-4 max-w-xl">
            Speak a task — it&rsquo;s delegated instantly.
          </p>
        </div>
      </div>

      {/* Voice input */}
      <div className="border border-[#d1d5db] p-8 space-y-6">
        <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
          Voice delegation
        </span>
        <div className="flex flex-col items-center gap-6">
          <VoiceButton
            listening={voice.listening}
            processing={voice.processing}
            onToggle={() => voice.listening ? voice.stop() : !voice.processing && void voice.start()}
          />
          <div className="w-full border border-[#d1d5db] p-4 min-h-24 font-mono text-sm">
            {voice.final && <span className="text-[#1a1a1a]">{voice.final}</span>}
            {voice.processing && !voice.final && (
              <span className="text-[#b08d57] italic">Transcribing…</span>
            )}
            {!voice.final && !voice.processing && (
              <span className="text-[#9ca3af]">
                Press Speak and describe the task, e.g. &ldquo;Andre, please draft
                the Schneider NDA by Friday&rdquo;.
              </span>
            )}
          </div>
        </div>
        <div>
          <label className="font-mono text-xs tracking-widest uppercase text-[#4b5563] block mb-2">
            Or type:
          </label>
          <textarea
            value={typing}
            onChange={(e) => setTyping(e.target.value)}
            placeholder="e.g. Andre, please draft the Schneider NDA by Friday"
            className="w-full border border-[#d1d5db] px-4 py-3 text-sm h-20 resize-none bg-transparent focus:outline-none focus:border-[#4f46e5] transition-colors duration-300"
          />
        </div>
        <div className="flex justify-end">
          <button
            onClick={handleDelegate}
            disabled={submitting || !activeTranscript}
            className="border border-[#4f46e5] bg-[#4f46e5] text-white px-8 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#3730a3] hover:border-[#3730a3] disabled:opacity-40 transition-colors duration-300"
          >
            {submitting ? "Parsing…" : "Delegate"}
          </button>
        </div>
      </div>

      {/* Preview */}
      {preview && (
        <PreviewCard
          preview={preview}
          editing={editing}
          setEditing={setEditing}
          onConfirm={handleConfirm}
          onEdit={() => setEditing(true)}
          onCancel={() => {
            setPreview(null);
            setEditing(false);
          }}
          onEditChange={(patch) => setPreview({ ...preview, ...patch })}
        />
      )}

      {error && (
        <div className="border border-[#dc2626] text-[#dc2626] px-6 py-4 font-mono text-sm">
          {error}
        </div>
      )}

      {/* Filter bar */}
      <FilterBar
        filters={filters}
        setFilters={setFilters}
        assignees={assignees}
        matters={matters}
      />

      {/* Board */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {COLUMNS.map((col) => {
          const colTasks = filteredTasks.filter((t) => t.status === col.key);
          return (
            <div key={col.key} className="border border-[#d1d5db] bg-[#fafafa] p-4 min-h-64">
              <div className="flex items-center justify-between mb-4">
                <span className="font-mono text-xs tracking-widest uppercase text-[#3730a3]">
                  {col.label}
                </span>
                <span className="font-mono text-xs tracking-widest text-[#4b5563]">
                  {colTasks.length}
                </span>
              </div>
              {colTasks.length > 0 ? (
                <div className="space-y-3">
                  {colTasks.map((t) => (
                    <TaskCard
                      key={t.id}
                      task={t}
                      onStatusChange={handleStatusChange}
                      onSaveTranscript={handleSaveTaskTranscript}
                    />
                  ))}
                </div>
              ) : (
                <div className="font-mono text-[10px] tracking-widest uppercase text-[#9ca3af] text-center py-8">
                  No {col.label.toLowerCase()} tasks
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
