"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthError, resetPassword } from "@/lib/auth";

const INVALID_LINK = "This reset link has expired or is invalid.";

function ResetForm() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  if (!token) {
    return (
      <div className="space-y-6">
        <p className="font-mono text-sm leading-relaxed text-[#9a3412] border-l-2 border-[#ea580c] pl-3">
          {INVALID_LINK}
        </p>
        <p className="font-mono text-xs tracking-wider text-[#4b5563] text-center">
          <Link href="/forgot" className="text-[#ea580c] hover:underline">
            Request a new link
          </Link>
        </p>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await resetPassword(token, password);
      router.push("/login?reset=success");
      router.refresh();
    } catch (err) {
      const msg =
        err instanceof AuthError && err.status >= 500
          ? "Something went wrong. Please try again."
          : INVALID_LINK;
      setError(msg);
      setPassword("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="New password (min 8 characters)"
        autoFocus
        required
        minLength={8}
        className="w-full border border-[#d1d5db] px-4 py-3.5 text-base font-mono
                   bg-white text-[#1a1a1a] placeholder-[#6b7280]
                   focus:outline-none focus:border-[#ea580c]
                   transition-colors duration-300"
      />

      {error && (
        <div className="space-y-2">
          <p className="font-mono text-sm text-[#9a3412] border-l-2 border-[#ea580c] pl-3">
            {error}
          </p>
          <p className="font-mono text-xs tracking-wider text-[#4b5563]">
            <Link href="/forgot" className="text-[#ea580c] hover:underline">
              Request a new link
            </Link>
          </p>
        </div>
      )}

      <button
        type="submit"
        disabled={loading || password.length < 8}
        className="w-full border-l-2 border-l-[#ea580c] bg-[#1a1a1a] text-white
                   px-8 py-3.5 font-mono text-sm tracking-widest uppercase
                   hover:bg-[#9a3412] disabled:opacity-30
                   transition-colors duration-300"
      >
        {loading ? "Setting…" : "Set new password"}
      </button>
    </form>
  );
}

export default function ResetPage() {
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
          New password
        </h1>
        <p className="font-mono text-sm tracking-wider text-[#4b5563] mb-8">
          Choose a password you haven&apos;t used before.
        </p>

        <Suspense fallback={<div className="font-mono text-sm text-[#6b7280]">Loading…</div>}>
          <ResetForm />
        </Suspense>
      </div>
    </div>
  );
}
