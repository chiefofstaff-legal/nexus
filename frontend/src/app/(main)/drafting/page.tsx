"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";

// -- Types -------------------------------------------------------------------

interface Template {
  id: string;
  name: string;
  description: string;
  template_type: string;
  base_prompt: string;
}

interface Draft {
  template_id: string;
  template_name: string;
  matter_name: string;
  client_name: string;
  draft_text: string;
  word_count: number;
  estimated_reading_minutes: number;
  model_used: string;
  // Stored client-side so lawyers can see what they originally dictated
  source_transcript?: string;
}

interface Summary {
  summary_type: string;
  summary: string;
  word_count: number;
  source_chars: number;
  model_used: string;
}

type Tab = "draft" | "summarise";
type SummaryType = "brief" | "detailed" | "action_items";

// -- Groq Whisper voice hook (mirrors tasks/page.tsx) ------------------------

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

  return {
    listening: voiceState === "recording",
    processing: voiceState === "processing",
    final,
    start,
    stop,
    voiceError,
  };
}

// -- Small UI primitives (kept short per KISS/CC gates) ----------------------

function Heading({ eyebrow, title, subtitle }: {
  eyebrow: string; title: string; subtitle: string;
}) {
  return (
    <div className="grid grid-cols-12 gap-8">
      <div className="col-span-12 lg:col-span-3">
        <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
          <span className="text-[#9a3412]">03</span>
          <span className="ml-3">{eyebrow}</span>
        </div>
      </div>
      <div className="col-span-12 lg:col-span-9">
        <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
          {title}
        </h2>
        <p className="text-lg text-[#4b5563] mt-4 max-w-xl">{subtitle}</p>
      </div>
    </div>
  );
}

function TemplateCard({ template, selected, onClick }: {
  template: Template; selected: boolean; onClick: () => void;
}) {
  const cls = selected
    ? "border-black bg-[#1a1a1a] text-white"
    : "border-gray-300 hover:border-[#ea580c] hover:text-[#9a3412]";
  return (
    <button
      onClick={onClick}
      className={`border p-5 text-left transition-colors duration-300 ${cls}`}
    >
      <span className="font-mono text-[10px] tracking-widest uppercase opacity-60 block mb-2">
        {template.template_type}
      </span>
      <div className="text-lg font-bold tracking-tight mb-1">{template.name}</div>
      <p className="text-xs opacity-80 leading-relaxed">{template.description}</p>
    </button>
  );
}

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-2">
        {label}
      </span>
      {children}
    </div>
  );
}

function PrimaryButton({ onClick, disabled, children }: {
  onClick: () => void; disabled?: boolean; children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="border border-black bg-[#1a1a1a] text-white px-8 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#ea580c] hover:border-[#ea580c] disabled:opacity-50 transition-colors duration-300"
    >
      {children}
    </button>
  );
}

function SecondaryButton({ onClick, disabled, children }: {
  onClick: () => void; disabled?: boolean; children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="border border-gray-300 px-6 py-3 font-mono text-xs tracking-widest uppercase hover:border-[#ea580c] hover:text-[#9a3412] disabled:opacity-50 transition-colors duration-300"
    >
      {children}
    </button>
  );
}

// -- Main page ---------------------------------------------------------------

export default function DraftingPage() {
  const [tab, setTab] = useState<Tab>("draft");
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [matter, setMatter] = useState("");
  const [client, setClient] = useState("");
  const [keyFactsText, setKeyFactsText] = useState("");
  const [additional, setAdditional] = useState("");
  const [transcript, setTranscript] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Summarise tab state
  const [sourceText, setSourceText] = useState("");
  const [summaryType, setSummaryType] = useState<SummaryType>("brief");
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    api.listDraftingTemplates()
      .then((r) => setTemplates(r.templates ?? []))
      .catch((e) => setError(String(e)));
  }, []);

  const keyFacts = useMemo(
    () => keyFactsText.split("\n").map((s) => s.trim()).filter(Boolean),
    [keyFactsText],
  );

  const handleGenerate = useCallback(async () => {
    if (!selected) return;
    setLoading(true); setError(""); setDraft(null);
    try {
      const result = await api.generateDraft({
        template_id: selected,
        matter_name: matter,
        client_name: client,
        key_facts: keyFacts,
        additional_instructions: additional,
      });
      setDraft(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [selected, matter, client, keyFacts, additional]);

  const handleVoice = useCallback(async () => {
    if (!transcript.trim()) return;
    setLoading(true); setError(""); setDraft(null); setDrafts([]);
    try {
      const result = await api.voiceToDraftMulti(transcript);
      if (result.intent_count === 1) {
        const { plan, draft: d } = result.results[0];
        setDraft({ ...d, source_transcript: transcript });
        setSelected(plan.template_id);
        setMatter(plan.matter_name ?? "");
        setClient(plan.client_name ?? "");
        setKeyFactsText((plan.key_facts ?? []).join("\n"));
        setAdditional(plan.additional_instructions ?? "");
      } else {
        setDrafts(result.results.map((r) => ({ ...r.draft, source_transcript: transcript })));
        const first = result.results[0].plan;
        setSelected(first.template_id);
        setMatter(first.matter_name ?? "");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [transcript]);

  const handleSummarise = useCallback(async () => {
    if (!sourceText.trim()) return;
    setLoading(true); setError(""); setSummary(null);
    try {
      const result = await api.summariseDocument(sourceText, summaryType);
      setSummary(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [sourceText, summaryType]);

  const copyDraft = () => {
    if (draft) navigator.clipboard.writeText(draft.draft_text);
  };

  return (
    <div className="space-y-12">
      <Heading
        eyebrow="Drafting"
        title={"AI\nDrafting"}
        subtitle="Efficiency work, automated. Select a template — AI applies your matter context. British English, Swiss law-aware, FADP-compliant routing."
      />

      <TabBar tab={tab} setTab={setTab} />

      {tab === "draft" && (
        <DraftTab
          templates={templates}
          selected={selected} setSelected={setSelected}
          matter={matter} setMatter={setMatter}
          client={client} setClient={setClient}
          keyFactsText={keyFactsText} setKeyFactsText={setKeyFactsText}
          additional={additional} setAdditional={setAdditional}
          transcript={transcript} setTranscript={setTranscript}
          loading={loading}
          onGenerate={handleGenerate}
          onVoice={handleVoice}
        />
      )}

      {tab === "summarise" && (
        <SummariseTab
          sourceText={sourceText} setSourceText={setSourceText}
          summaryType={summaryType} setSummaryType={setSummaryType}
          loading={loading}
          onSummarise={handleSummarise}
          summary={summary}
        />
      )}

      {error && (
        <div className="border-l-2 border-[#ea580c] pl-6 py-2">
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#9a3412] block mb-1">
            Error
          </span>
          <p className="font-mono text-xs text-[#4b5563]">{error}</p>
        </div>
      )}

      {tab === "draft" && draft && <DraftOutput draft={draft} onCopy={copyDraft} />}

      {tab === "draft" && drafts.length > 1 && (
        <div className="space-y-6">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
            {drafts.length} drafts generated
          </div>
          {drafts.map((d, i) => (
            <div key={i}>
              <div className="font-mono text-[10px] tracking-widest uppercase text-[#9a3412] mb-3">
                Draft {i + 1} — {d.template_name}
              </div>
              <DraftOutput
                draft={d}
                onCopy={() => navigator.clipboard.writeText(d.draft_text)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// -- Tab bar -----------------------------------------------------------------

function TabBar({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  const tabs: { id: Tab; label: string }[] = [
    { id: "draft", label: "Draft from template" },
    { id: "summarise", label: "Summarise document" },
  ];
  return (
    <div className="flex gap-2 border-b border-gray-300">
      {tabs.map((t) => {
        const active = tab === t.id;
        const cls = active
          ? "border-[#ea580c] text-[#9a3412]"
          : "border-transparent text-[#4b5563] hover:text-[#9a3412]";
        return (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-3 font-mono text-xs tracking-widest uppercase border-b-2 transition-colors duration-300 ${cls}`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

// -- Draft tab ---------------------------------------------------------------

interface DraftTabProps {
  templates: Template[];
  selected: string; setSelected: (v: string) => void;
  matter: string; setMatter: (v: string) => void;
  client: string; setClient: (v: string) => void;
  keyFactsText: string; setKeyFactsText: (v: string) => void;
  additional: string; setAdditional: (v: string) => void;
  transcript: string; setTranscript: (v: string) => void;
  loading: boolean;
  onGenerate: () => void;
  onVoice: () => void;
}

function DraftTab(p: DraftTabProps) {
  return (
    <div className="space-y-10">
      <VoiceBox
        transcript={p.transcript}
        setTranscript={p.setTranscript}
        onVoice={p.onVoice}
        loading={p.loading}
      />

      <div>
        <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563] block mb-4">
          Template Gallery
        </span>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {p.templates.map((t) => (
            <TemplateCard
              key={t.id}
              template={t}
              selected={p.selected === t.id}
              onClick={() => p.setSelected(t.id)}
            />
          ))}
        </div>
      </div>

      {p.selected && (
        <MatterForm
          matter={p.matter} setMatter={p.setMatter}
          client={p.client} setClient={p.setClient}
          keyFactsText={p.keyFactsText} setKeyFactsText={p.setKeyFactsText}
          additional={p.additional} setAdditional={p.setAdditional}
          onGenerate={p.onGenerate}
          loading={p.loading}
        />
      )}
    </div>
  );
}

function VoiceBox({ transcript, setTranscript, onVoice, loading }: {
  transcript: string;
  setTranscript: (v: string) => void;
  onVoice: () => void;
  loading: boolean;
}) {
  const voice = useVoiceTranscript();

  // When Groq returns a transcript, append/replace into the textarea
  useEffect(() => {
    if (voice.final) setTranscript(voice.final);
  }, [voice.final, setTranscript]);

  const toggleRecording = () => {
    if (voice.listening) { voice.stop(); return; }
    if (!voice.processing) void voice.start();
  };

  const micLabel = voice.listening ? "Stop" : voice.processing ? "Wait" : "Speak";
  const micCls = voice.listening
    ? "border-[#ea580c] bg-[#ea580c] text-white animate-pulse"
    : voice.processing
    ? "border-[#b08d57] bg-[#b08d57] text-white animate-pulse"
    : "border-[#1a1a1a] bg-[#1a1a1a] text-white hover:bg-[#ea580c] hover:border-[#ea580c]";

  return (
    <div className="border border-[#1a1a1a] p-6 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#9a3412] block mb-1">
            Voice delegation
          </span>
          <p className="text-xs text-[#4b5563] max-w-lg">
            Dictate in natural language — the AI selects the template, extracts your matter
            details, and drafts in one step. No form to fill. No BigHand licence required.
          </p>
        </div>
        {/* Mic button — Groq Whisper large-v3 */}
        <button
          type="button"
          onClick={toggleRecording}
          disabled={loading}
          title={voice.listening ? "Stop recording" : "Start voice recording"}
          className={`shrink-0 w-10 h-10 rounded-full border-2 flex items-center justify-center transition-all duration-300 ${micCls}`}
          aria-label={micLabel}
        >
          {voice.processing ? (
            <span className="font-mono text-[8px] tracking-widest uppercase">…</span>
          ) : (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <rect x="5" y="1" width="6" height="9" rx="3" fill="currentColor"/>
              <path d="M2 8a6 6 0 0 0 12 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <line x1="8" y1="14" x2="8" y2="16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          )}
        </button>
      </div>
      {voice.voiceError && (
        <p className="font-mono text-[10px] text-[#9a3412]">{voice.voiceError}</p>
      )}
      <Labelled label={voice.listening ? "Recording…" : voice.processing ? "Transcribing…" : "Speak your draft request"}>
        <textarea
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          placeholder='e.g. "Draft an NDA for Müller AG, bilateral, 3-year term, Zurich governing law"'
          className="w-full border border-gray-300 px-4 py-3 text-sm h-20 resize-none bg-transparent focus:outline-none focus:border-[#ea580c] transition-colors duration-300"
        />
      </Labelled>
      <div className="flex gap-3 items-center">
        <SecondaryButton onClick={onVoice} disabled={loading || !transcript.trim()}>
          {loading ? "Parsing…" : "Auto-select + draft"}
        </SecondaryButton>
        <span className="font-mono text-[10px] tracking-wider text-[#9ca3af]">
          Haiku parses intent · Sonnet drafts · Swiss-law aware
        </span>
      </div>
    </div>
  );
}

interface MatterFormProps {
  matter: string; setMatter: (v: string) => void;
  client: string; setClient: (v: string) => void;
  keyFactsText: string; setKeyFactsText: (v: string) => void;
  additional: string; setAdditional: (v: string) => void;
  loading: boolean;
  onGenerate: () => void;
}

function MatterForm(p: MatterFormProps) {
  return (
    <div className="border border-gray-300 p-8 space-y-5">
      <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563] block">
        Matter Context
      </span>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <Labelled label="Matter name">
          <input
            value={p.matter}
            onChange={(e) => p.setMatter(e.target.value)}
            placeholder="e.g. Müller AG v. Credit Suisse"
            className="w-full border border-gray-300 px-4 py-2 text-sm bg-transparent focus:outline-none focus:border-[#ea580c] transition-colors duration-300"
          />
        </Labelled>
        <Labelled label="Client name">
          <input
            value={p.client}
            onChange={(e) => p.setClient(e.target.value)}
            placeholder="e.g. Müller AG"
            className="w-full border border-gray-300 px-4 py-2 text-sm bg-transparent focus:outline-none focus:border-[#ea580c] transition-colors duration-300"
          />
        </Labelled>
      </div>
      <Labelled label="Key facts (one per line)">
        <textarea
          value={p.keyFactsText}
          onChange={(e) => p.setKeyFactsText(e.target.value)}
          placeholder={"Bilateral disclosure\nTerm: 3 years\nGoverning law: Switzerland\nJurisdiction: Zurich"}
          className="w-full border border-gray-300 px-4 py-3 text-sm h-28 resize-none bg-transparent focus:outline-none focus:border-[#ea580c] transition-colors duration-300"
        />
      </Labelled>
      <Labelled label="Additional instructions (optional)">
        <textarea
          value={p.additional}
          onChange={(e) => p.setAdditional(e.target.value)}
          placeholder="Any additional tone or structure requests..."
          className="w-full border border-gray-300 px-4 py-3 text-sm h-20 resize-none bg-transparent focus:outline-none focus:border-[#ea580c] transition-colors duration-300"
        />
      </Labelled>
      <PrimaryButton onClick={p.onGenerate} disabled={p.loading}>
        {p.loading ? "Generating..." : "Generate Draft"}
      </PrimaryButton>
    </div>
  );
}

// -- Summarise tab -----------------------------------------------------------

interface SummariseTabProps {
  sourceText: string; setSourceText: (v: string) => void;
  summaryType: SummaryType; setSummaryType: (v: SummaryType) => void;
  loading: boolean;
  onSummarise: () => void;
  summary: Summary | null;
}

function SummariseTab(p: SummariseTabProps) {
  const [extracting, setExtracting] = useState(false);
  const [extractedName, setExtractedName] = useState("");
  const [extractError, setExtractError] = useState("");

  const handleFileUpload = async (e: { target: HTMLInputElement }) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setExtracting(true);
    setExtractError("");
    setExtractedName("");
    try {
      const record = await api.uploadDocument(file);
      const content = await api.getDocumentContent(record.id);
      p.setSourceText(content.text ?? "");
      setExtractedName(`${file.name} · ${content.page_count ?? "?"} pages`);
    } catch (err) {
      setExtractError(String(err));
    } finally {
      setExtracting(false);
      e.target.value = "";
    }
  };

  const types: { id: SummaryType; label: string }[] = [
    { id: "brief", label: "Brief" },
    { id: "detailed", label: "Detailed" },
    { id: "action_items", label: "Action items" },
  ];

  return (
    <div className="space-y-6">
      <div className="border border-gray-300 p-8 space-y-5">
        {/* File upload area */}
        <Labelled label="Upload document">
          <label className="block cursor-pointer group">
            <div className={`border-2 border-dashed px-6 py-5 text-center transition-colors duration-300 ${
              extracting
                ? "border-[#ea580c] bg-orange-50"
                : "border-gray-300 group-hover:border-[#ea580c]"
            }`}>
              {extracting ? (
                <div className="flex items-center justify-center gap-3">
                  <span className="w-2 h-2 bg-[#ea580c] rounded-full animate-pulse" />
                  <span className="font-mono text-xs tracking-wider uppercase text-[#9a3412]">
                    Extracting text…
                  </span>
                </div>
              ) : (
                <>
                  <p className="font-mono text-xs tracking-wider uppercase text-gray-500">
                    Click to upload PDF, DOCX, or TXT
                  </p>
                  {extractedName && (
                    <p className="font-mono text-[10px] text-[#9a3412] mt-2 truncate">{extractedName}</p>
                  )}
                </>
              )}
            </div>
            <input
              type="file"
              accept=".pdf,.docx,.doc,.txt,.md"
              onChange={handleFileUpload}
              disabled={extracting || p.loading}
              className="hidden"
            />
          </label>
          {extractError && (
            <p className="font-mono text-xs text-[#9a3412] mt-2">{extractError}</p>
          )}
        </Labelled>

        <Labelled label="Or paste document text">
          <textarea
            value={p.sourceText}
            onChange={(e) => p.setSourceText(e.target.value)}
            placeholder="Paste the full text of the document to summarise..."
            className="w-full border border-gray-300 px-4 py-3 text-sm h-40 resize-none bg-transparent focus:outline-none focus:border-[#ea580c] transition-colors duration-300"
          />
        </Labelled>
        <div className="flex flex-wrap gap-2">
          {types.map((t) => {
            const active = p.summaryType === t.id;
            const cls = active
              ? "border-black bg-[#1a1a1a] text-white"
              : "border-gray-300 hover:border-[#ea580c] hover:text-[#9a3412]";
            return (
              <button
                key={t.id}
                onClick={() => p.setSummaryType(t.id)}
                className={`border px-4 py-2 font-mono text-[10px] tracking-widest uppercase transition-colors duration-300 ${cls}`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
        <PrimaryButton onClick={p.onSummarise} disabled={p.loading || !p.sourceText.trim()}>
          {p.loading ? "Summarising..." : "Summarise"}
        </PrimaryButton>
      </div>

      {p.summary && <SummaryOutput summary={p.summary} />}
    </div>
  );
}

function SummaryOutput({ summary }: { summary: Summary }) {
  return (
    <div className="border border-gray-300 p-8">
      <div className="flex items-center justify-between mb-4">
        <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
          {summary.summary_type.replace("_", " ")} summary
        </span>
        <span className="font-mono text-[10px] tracking-wider text-[#4b5563]">
          {summary.word_count} words · source {summary.source_chars} chars · {summary.model_used}
        </span>
      </div>
      <div className="text-sm text-[#1a1a1a] whitespace-pre-wrap leading-relaxed font-serif">
        {summary.summary}
      </div>
    </div>
  );
}

// -- Draft output ------------------------------------------------------------

function DraftOutput({ draft, onCopy }: { draft: Draft; onCopy: () => void }) {
  const [showTranscript, setShowTranscript] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block">
            {draft.template_name}
          </span>
          {(draft.matter_name || draft.client_name) && (
            <span className="font-mono text-xs text-[#4b5563]">
              {draft.matter_name}
              {draft.client_name ? ` · ${draft.client_name}` : ""}
            </span>
          )}
        </div>
        <div className="flex gap-6 items-center">
          <span className="font-mono text-[10px] tracking-wider text-[#4b5563]">
            {draft.word_count} words · {draft.estimated_reading_minutes} min read
          </span>
          {draft.source_transcript && (
            <button
              onClick={() => setShowTranscript((s) => !s)}
              className="font-mono text-[10px] tracking-widest uppercase text-[#9ca3af] hover:text-[#ea580c] transition-colors"
              title="View original voice instruction"
            >
              {showTranscript ? "transcript ↙" : "transcript ↗"}
            </button>
          )}
          <SecondaryButton onClick={onCopy}>Copy</SecondaryButton>
        </div>
      </div>
      {/* Original voice instruction — collapsible */}
      {showTranscript && draft.source_transcript && (
        <div className="border border-orange-200 bg-orange-50 px-5 py-3">
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#9a3412] block mb-1">
            Voice instruction
          </span>
          <p className="font-mono text-xs text-[#4b5563] italic leading-relaxed">
            &ldquo;{draft.source_transcript}&rdquo;
          </p>
        </div>
      )}
      <div className="border border-gray-300 bg-white p-10">
        <div className="text-sm text-[#1a1a1a] whitespace-pre-wrap leading-relaxed font-serif max-w-3xl mx-auto">
          {draft.draft_text}
        </div>
      </div>
      <div className="font-mono text-[10px] tracking-wider text-[#4b5563] text-right">
        Model: {draft.model_used}
      </div>
    </div>
  );
}
