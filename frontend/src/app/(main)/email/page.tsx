"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

interface EmailDraft {
  recipient_hint: string;
  subject: string;
  body: string;
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
          form.append("file", blob, "recording.webm");
          const res = await fetch(`${API_BASE}/api/transcribe`, { method: "POST", body: form });
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

export default function EmailPage() {
  const voice = useVoiceTranscript();
  const [draft, setDraft] = useState<EmailDraft | null>(null);
  const [parsing, setParsing] = useState(false);
  const [sent, setSent] = useState(false);
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
      setSent(false);
      try {
        const res = await fetch(`${API_BASE}/api/email/voice`, {
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

  const handleSend = () => {
    console.log("Send email:", draft);
    setSent(true);
  };

  return (
    <div className="space-y-12">
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 lg:col-span-3">
          <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] space-y-3">
            <div><span className="text-[#0a1628]">01</span><span className="ml-3">Speak</span></div>
            <div><span className="text-[#0a1628]">02</span><span className="ml-3">Review</span></div>
            <div><span className="text-[#0a1628]">03</span><span className="ml-3">Send</span></div>
          </div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
            Email<br />Draft
          </h2>
          <p className="text-lg text-[#4b5563] mt-4 max-w-xl">
            Dictate an email. Review the draft. Send with one click.
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
              <span className="text-[#b08d57] italic">Parsing email…</span>
            ) : (
              <span className="text-[#9ca3af]">
                Press Speak and describe your email, e.g. &ldquo;Email Müller about the contract review on Friday&rdquo;.
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

      {draft && !sent && (
        <section aria-labelledby="draft-heading" className="border border-[#d1d5db] bg-white">
          <div className="border-b border-[#d1d5db] bg-[#fafafa] px-5 py-4">
            <h3
              id="draft-heading"
              className="font-mono text-xs tracking-widest uppercase text-[#4b5563]"
            >
              Draft preview
            </h3>
          </div>
          <div className="p-5 md:p-6 space-y-5">
            <div>
              <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2">
                To
              </div>
              <div className="border border-[#d1d5db] bg-[#fafafa] px-3 py-3 text-sm text-[#1a1a1a]">
                {draft.recipient_hint || <span className="text-[#9ca3af] italic">No recipient detected</span>}
              </div>
            </div>
            <div>
              <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2">
                Subject
              </div>
              <div className="border border-[#d1d5db] bg-[#fafafa] px-3 py-3 text-sm font-medium text-[#1a1a1a]">
                {draft.subject}
              </div>
            </div>
            <div>
              <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2">
                Body
              </div>
              <div className="border border-[#d1d5db] bg-[#fafafa] px-3 py-4 text-sm text-[#1a1a1a] whitespace-pre-wrap min-h-24">
                {draft.body}
              </div>
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSend}
                className="border border-[#0a1628] bg-[#0a1628] text-white px-8 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#1f2937] transition-colors duration-300"
              >
                Send email
              </button>
            </div>
          </div>
        </section>
      )}

      {sent && (
        <div className="border-l-2 border-[#0a1628] pl-6 py-3">
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#0a1628] block mb-1">
            Sent
          </span>
          <div className="text-sm text-[#1a1a1a]">
            Email logged. Integration with MS Graph will dispatch it in production.
          </div>
        </div>
      )}
    </div>
  );
}
