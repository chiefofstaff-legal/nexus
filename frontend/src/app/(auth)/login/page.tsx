"use client";

import { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthError, loginUser } from "@/lib/auth";

function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await loginUser(email, password);
      const from = searchParams.get("from") || "/";
      router.push(from);
      router.refresh();
    } catch (err) {
      const msg = err instanceof AuthError ? err.message : "Authentication failed";
      setError(msg);
      setPassword("");
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
        placeholder="Password"
        required
        minLength={8}
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
        disabled={loading || !email || !password}
        className="w-full border-l-2 border-l-[#ea580c] bg-[#1a1a1a] text-white
                   px-8 py-3.5 font-mono text-sm tracking-widest uppercase
                   hover:bg-[#9a3412] disabled:opacity-30
                   transition-colors duration-300"
      >
        {loading ? "Signing in…" : "Sign in"}
      </button>

      <p className="font-mono text-xs tracking-wider text-[#4b5563] text-center pt-2">
        Don&apos;t have an account?{" "}
        <Link href="/signup" className="text-[#ea580c] hover:underline">
          Create one
        </Link>
      </p>

      <p className="font-mono text-[10px] leading-relaxed tracking-wider text-[#6b7280] pt-6 border-t border-[#d1d5db] mt-6">
        Public demo. Inputs are processed by US-based frontier AI models
        (Anthropic, Groq, OpenAI) via a Germany-hosted relay. Do not enter
        privileged or confidential matter data.
      </p>
    </form>
  );
}

export default function LoginPage() {
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
          Sign in
        </h1>
        <p className="font-mono text-sm tracking-wider text-[#4b5563] mb-8">
          Your matters, only yours.
        </p>

        <Suspense fallback={<div className="font-mono text-sm text-[#6b7280]">Loading…</div>}>
          <LoginForm />
        </Suspense>
      </div>
    </div>
  );
}
