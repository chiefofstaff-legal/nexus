"use client";

import { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthError, signupUser } from "@/lib/auth";

function SignupForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [acceptedDisclosure, setAcceptedDisclosure] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!acceptedDisclosure) {
      setError("Please accept the data-handling disclosure before creating an account.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await signupUser(email, password);
      router.push("/");
      router.refresh();
    } catch (err) {
      const msg = err instanceof AuthError ? err.message : "Signup failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
        autoFocus
        required
        className="w-full border border-[#d1d5db] px-4 py-3.5 text-base font-mono
                   bg-white text-[#1a1a1a] placeholder-[#6b7280]
                   focus:outline-none focus:border-[#ea580c]
                   transition-colors duration-300"
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password (min 8 characters)"
        required
        minLength={8}
        className="w-full border border-[#d1d5db] px-4 py-3.5 text-base font-mono
                   bg-white text-[#1a1a1a] placeholder-[#6b7280]
                   focus:outline-none focus:border-[#ea580c]
                   transition-colors duration-300"
      />

      <div className="border border-[#d1d5db] bg-white p-4 space-y-3">
        <p className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
          How your data is handled
        </p>
        <p className="font-mono text-xs leading-relaxed text-[#1a1a1a]">
          This is a public demo. Text and voice you submit are routed through a
          server in Germany (Hetzner, Falkenstein) to US-based frontier AI
          models — Anthropic Claude, Groq, and OpenAI — for parsing,
          summarisation, and drafting. Audio is transcribed by Groq Whisper
          and is not retained by the demo.
        </p>
        <p className="font-mono text-xs leading-relaxed text-[#1a1a1a]">
          Do not enter privileged, confidential client matter, or any
          information that cannot leave your jurisdiction. The self-hosted
          path that runs entirely on the Germany server (open-source local
          LLM) is on the roadmap but is <em>not</em> the default for this
          public demo today.
        </p>
        <label className="flex items-start gap-3 cursor-pointer pt-1">
          <input
            type="checkbox"
            checked={acceptedDisclosure}
            onChange={(e) => setAcceptedDisclosure(e.target.checked)}
            required
            className="mt-1 w-4 h-4 accent-[#ea580c] cursor-pointer"
            aria-label="I understand how my data will be processed"
          />
          <span className="font-mono text-xs leading-relaxed text-[#1a1a1a]">
            I understand my inputs are sent to US-based AI models via a
            Germany-hosted relay and will not enter confidential matter
            information into this demo.
          </span>
        </label>
      </div>

      {error && (
        <p className="font-mono text-sm text-[#9a3412] border-l-2 border-[#ea580c] pl-3">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={loading || !email || password.length < 8 || !acceptedDisclosure}
        className="w-full border-l-2 border-l-[#ea580c] bg-[#1a1a1a] text-white
                   px-8 py-3.5 font-mono text-sm tracking-widest uppercase
                   hover:bg-[#9a3412] disabled:opacity-30
                   transition-colors duration-300"
      >
        {loading ? "Creating account…" : "Create account"}
      </button>

      <p className="font-mono text-xs tracking-wider text-[#4b5563] text-center pt-2">
        Already have an account?{" "}
        <Link href="/login" className="text-[#ea580c] hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}

export default function SignupPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#EAEAEA]">
      <div className="w-full max-w-md p-8">
        <div className="mb-12">
          <span className="text-[#1a1a1a] text-2xl font-bold tracking-tighter">
            ChiefOfStaff
          </span>
          <span className="font-mono text-sm tracking-widest text-[#4b5563] uppercase ml-2">
            .pro
          </span>
        </div>

        <h1 className="text-4xl font-bold tracking-tighter text-[#1a1a1a] mb-2">
          Create account
        </h1>
        <p className="font-mono text-sm tracking-wider text-[#4b5563] mb-8">
          Your matters stay isolated to your account.
        </p>

        <Suspense fallback={<div className="font-mono text-sm text-[#6b7280]">Loading…</div>}>
          <SignupForm />
        </Suspense>
      </div>
    </div>
  );
}
