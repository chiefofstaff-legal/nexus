"use client";

import { useState } from "react";
import Link from "next/link";
import { AuthError, requestPasswordReset } from "@/lib/auth";

const GENERIC_NOTICE =
  "If that email is registered, you'll receive a reset link shortly. The link expires in 1 hour.";

function ForgotForm() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await requestPasswordReset(email);
      setSubmitted(true);
    } catch (err) {
      // Even on error we surface the same generic line — never enumerate.
      // Only network failures (no response) become a visible error.
      const status = err instanceof AuthError ? err.status : 0;
      if (status === 0) {
        setError("Network error. Please try again in a moment.");
      } else {
        setSubmitted(true);
      }
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <div className="space-y-6">
        <p className="font-mono text-sm leading-relaxed text-[#1a1a1a] border-l-2 border-[#059669] bg-[#f0fdf4] p-4">
          {GENERIC_NOTICE}
        </p>
        <p className="font-mono text-xs tracking-wider text-[#4b5563] text-center">
          <Link href="/login" className="text-[#ea580c] hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    );
  }

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

      {error && (
        <p className="font-mono text-sm text-[#9a3412] border-l-2 border-[#ea580c] pl-3">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={loading || !email}
        className="w-full border-l-2 border-l-[#ea580c] bg-[#1a1a1a] text-white
                   px-8 py-3.5 font-mono text-sm tracking-widest uppercase
                   hover:bg-[#9a3412] disabled:opacity-30
                   transition-colors duration-300"
      >
        {loading ? "Sending…" : "Send reset link"}
      </button>

      <p className="font-mono text-xs tracking-wider text-[#4b5563] text-center pt-2">
        Remembered it?{" "}
        <Link href="/login" className="text-[#ea580c] hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}

export default function ForgotPage() {
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
          Reset password
        </h1>
        <p className="font-mono text-sm tracking-wider text-[#4b5563] mb-8">
          Enter your email and we&apos;ll send a reset link.
        </p>

        <ForgotForm />
      </div>
    </div>
  );
}
