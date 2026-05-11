"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type VoiceState = "idle" | "recording" | "processing";

interface VoiceMicButtonProps {
  /** Called with the transcribed text when recording stops + transcription completes. */
  onTranscript: (transcript: string) => void;
  /** Aria label tying the mic to the field it dictates into (e.g. "Dictate name"). */
  ariaLabel: string;
  /** Optional disabled state propagated from the parent form (e.g. while submitting). */
  disabled?: boolean;
}

/**
 * Tap-to-record voice mic that posts to /api/voice/transcribe (Groq Whisper).
 *
 * Mirrors the MediaRecorder + transcribeAudio pattern from drafting/page.tsx
 * but encapsulated as a reusable component so the create-matter dialog can
 * mount one per input without copying the state machine three times.
 *
 * UX contract:
 * - Idle:        ● MIC      (tap to start)
 * - Recording:   ■ STOP     (red, tap to stop)
 * - Processing:  ⋯ ...      (disabled while transcript returns)
 * - On success: onTranscript(text) called once; component returns to idle.
 * - On error:   error surfaced via title attribute, returns to idle.
 *
 * Touch targets are min-h-10 min-w-10 (40px) — slightly under the 48px ideal
 * because they sit alongside an existing 48px input row, but still well within
 * tap-friendly territory on mobile.
 */
export function VoiceMicButton({
  onTranscript,
  ariaLabel,
  disabled = false,
}: VoiceMicButtonProps) {
  const [state, setState] = useState<VoiceState>("idle");
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // Cleanup any active stream on unmount so we don't leak the mic between
  // dialog open/close cycles.
  useEffect(() => {
    return () => {
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.stop();
      }
    };
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setState("processing");
        try {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          const result = await api.transcribeAudio(blob);
          const transcript = (result.transcript || "").trim();
          if (transcript) onTranscript(transcript);
        } catch (e) {
          setError(String(e));
        } finally {
          setState("idle");
        }
      };
      recorderRef.current = recorder;
      recorder.start();
      setState("recording");
    } catch (e) {
      setError(String(e));
      setState("idle");
    }
  }, [onTranscript]);

  const stop = useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  const handleClick = () => {
    if (state === "idle") void start();
    else if (state === "recording") stop();
    // processing: no-op (button is disabled)
  };

  const isRecording = state === "recording";
  const isProcessing = state === "processing";

  const label = isRecording ? "Stop" : isProcessing ? "..." : "Mic";
  const symbol = isRecording ? "■" : isProcessing ? "⋯" : "●";

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || isProcessing}
      aria-label={ariaLabel}
      aria-pressed={isRecording}
      title={error ?? ariaLabel}
      className={[
        "flex items-center gap-1 border px-2 py-1 font-mono text-[10px] tracking-widest uppercase",
        "min-h-10 min-w-10 transition-colors duration-200",
        isRecording
          ? "border-[#dc2626] bg-[#dc2626] text-white"
          : isProcessing
          ? "border-[#9ca3af] bg-[#f3f4f6] text-[#6b7280] cursor-wait"
          : "border-[#1a1a1a] bg-white text-[#1a1a1a] hover:bg-[#1a1a1a] hover:text-white",
        disabled && "opacity-50 cursor-not-allowed",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span aria-hidden="true">{symbol}</span>
      <span>{label}</span>
    </button>
  );
}
