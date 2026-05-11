"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

interface EventDraft {
  title: string;
  start_iso: string;
  end_iso: string;
  attendees: string[];
  location: string;
}

type VoiceState = "idle" | "recording" | "processing";

function useVoiceTranscript() {
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [transcript, setTranscript] = useState("");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = useCallback(async () => {
    setTranscript("");
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
          const form = new FormData();
          form.append("audio", blob, "recording.webm");
          const res = await fetch(`${API_BASE}/api/voice/transcribe`, { method: "POST", body: form });
          if (!res.ok) throw new Error(`Transcription failed: ${res.status}`);
          const data = await res.json();
          setTranscript(data.transcript ?? "");
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
    transcript,
    voiceError,
    start,
    stop,
  };
}

function formatIso(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
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
          ? "border-[#0a1628] bg-[#0a1628] text-white animate-pulse"
          : processing
          ? "border-[#b08d57] bg-[#b08d57] text-white animate-pulse"
          : "border-[#d1d5db] hover:border-[#0a1628] hover:text-[#0a1628]"
      }`}
      aria-label={listening ? "Stop recording" : processing ? "Transcribing…" : "Start recording"}
    >
      <span className="font-mono text-[10px] tracking-widest uppercase">
        {listening ? "Stop" : processing ? "Wait" : "Speak"}
      </span>
    </button>
  );
}

export default function CalendarPage() {
  const voice = useVoiceTranscript();
  const [draft, setDraft] = useState<EventDraft | null>(null);
  const [parsing, setParsing] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (voice.voiceError) setError(voice.voiceError);
  }, [voice.voiceError]);

  useEffect(() => {
    if (!voice.transcript) return;
    const parse = async () => {
      setParsing(true);
      setError(null);
      setDraft(null);
      setConfirmed(false);
      try {
        const res = await fetch(`${API_BASE}/api/calendar/voice`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transcript: voice.transcript }),
        });
        if (!res.ok) throw new Error(`Parse failed: ${res.status}`);
        setDraft(await res.json());
      } catch (e) {
        setError(String(e));
      }
      setParsing(false);
    };
    parse();
  }, [voice.transcript]);

  const handleToggle = () => {
    if (voice.listening) voice.stop();
    else if (!voice.processing) void voice.start();
  };

  const handleConfirm = () => {
    console.log("Create calendar event:", draft);
    setConfirmed(true);
  };

  return (
    <div className="space-y-12">
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 lg:col-span-3">
          <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] space-y-3">
            <div><span className="text-[#0a1628]">01</span><span className="ml-3">Speak</span></div>
            <div><span className="text-[#0a1628]">02</span><span className="ml-3">Review</span></div>
            <div><span className="text-[#0a1628]">03</span><span className="ml-3">Confirm</span></div>
          </div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
            Calendar<br />Event
          </h2>
          <p className="text-lg text-[#4b5563] mt-4 max-w-xl">
            Dictate a meeting. Review the details. Confirm to create.
          </p>
        </div>
      </div>

      <div className="border border-[#d1d5db] p-8 space-y-6">
        <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
          Voice input
        </span>
        <div className="flex flex-col items-center gap-6">
          <VoiceButton
            listening={voice.listening}
            processing={voice.processing}
            onToggle={handleToggle}
          />
          <div className="w-full border border-[#d1d5db] p-4 min-h-16 font-mono text-sm">
            {voice.transcript ? (
              <span className="text-[#1a1a1a]">{voice.transcript}</span>
            ) : parsing ? (
              <span className="text-[#b08d57] italic">Parsing event…</span>
            ) : (
              <span className="text-[#9ca3af]">
                Press Speak and describe your meeting, e.g. &ldquo;Schedule a call with Müller on Friday at 10am for 30 minutes&rdquo;.
              </span>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="border border-[#dc2626] text-[#dc2626] px-6 py-4 font-mono text-sm">
          {error}
        </div>
      )}

      {draft && !confirmed && (
        <section aria-labelledby="event-heading" className="border border-[#d1d5db] bg-white">
          <div className="border-b border-[#d1d5db] bg-[#fafafa] px-5 py-4">
            <h3
              id="event-heading"
              className="font-mono text-xs tracking-widest uppercase text-[#4b5563]"
            >
              Event preview
            </h3>
          </div>
          <div className="p-5 md:p-6 space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2">
                  Title
                </div>
                <div className="border border-[#d1d5db] bg-[#fafafa] px-3 py-3 text-sm font-medium text-[#1a1a1a]">
                  {draft.title}
                </div>
              </div>
              {draft.location && (
                <div>
                  <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2">
                    Location
                  </div>
                  <div className="border border-[#d1d5db] bg-[#fafafa] px-3 py-3 text-sm text-[#1a1a1a]">
                    {draft.location}
                  </div>
                </div>
              )}
              <div>
                <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2">
                  Start
                </div>
                <div className="border border-[#d1d5db] bg-[#fafafa] px-3 py-3 text-sm text-[#1a1a1a]">
                  {formatIso(draft.start_iso)}
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2">
                  End
                </div>
                <div className="border border-[#d1d5db] bg-[#fafafa] px-3 py-3 text-sm text-[#1a1a1a]">
                  {formatIso(draft.end_iso)}
                </div>
              </div>
            </div>
            {draft.attendees.length > 0 && (
              <div>
                <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2">
                  Attendees
                </div>
                <div className="flex flex-wrap gap-2">
                  {draft.attendees.map((a) => (
                    <span
                      key={a}
                      className="border border-[#d1d5db] px-3 py-1 font-mono text-xs text-[#4b5563]"
                    >
                      {a}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleConfirm}
                className="border border-[#0a1628] bg-[#0a1628] text-white px-8 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#1f2937] transition-colors duration-300"
              >
                Create meeting
              </button>
            </div>
          </div>
        </section>
      )}

      {confirmed && (
        <div className="border-l-2 border-[#0a1628] pl-6 py-3">
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#0a1628] block mb-1">
            Meeting created
          </span>
          <div className="text-sm text-[#1a1a1a]">
            Event logged. Integration with MS Graph will create it in production.
          </div>
        </div>
      )}
    </div>
  );
}
