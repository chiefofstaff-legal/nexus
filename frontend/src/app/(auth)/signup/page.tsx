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

      <div className="border-l-2 border-[#059669] bg-[#f0fdf4] p-4 space-y-3">
        <p className="font-mono text-[10px] tracking-widest uppercase text-[#065f46]">
          PII Shield — your client data stays yours
        </p>
        <p className="font-mono text-xs leading-relaxed text-[#1a1a1a]">
          Before any sentence you speak or type leaves the Germany-hosted
          server, the open-source <strong>PII Shield</strong> replaces every
          real client name, person, organisation, and matter reference with
          a stable placeholder (e.g. <code>ORG_1</code>, <code>PERSON_2</code>,
          <code>CASE_3</code>). The AI parser only ever sees the placeholders.
          The original names are restored locally before the entry is shown
          back to you and stored.
        </p>
        <p className="font-mono text-xs leading-relaxed text-[#1a1a1a]">
          This is the canonical primitive from the open-source DONNA repo —
          you can read its 103 lines of stdlib Python and its 170-line test
          suite at <code>chiefofstaff-legal/nexus/backend/services/pii_shield.py</code>.
          AGPL-3.0. Self-hosters get the same protection.
        </p>
        <p className="font-mono text-[10px] leading-relaxed text-[#4b5563] pt-2 border-t border-[#bbf7d0]">
          <strong>As-is public demo.</strong> The shield is best-effort
          pattern-based redaction, not a guarantee. Use professional
          judgement with privileged content. Provided as-is under AGPL-3.0
          with no warranty of accuracy, availability, or fitness for legal
          practice; your firm remains responsible for compliance,
          confidentiality, and the safekeeping of client matter. By signing
          up you accept these terms.
        </p>
        <label className="flex items-start gap-3 cursor-pointer pt-1">
          <input
            type="checkbox"
            checked={acceptedDisclosure}
            onChange={(e) => setAcceptedDisclosure(e.target.checked)}
            required
            className="mt-1 w-4 h-4 accent-[#059669] cursor-pointer"
            aria-label="I understand the PII Shield protection model and accept the as-is demo terms"
          />
          <span className="font-mono text-xs leading-relaxed text-[#1a1a1a]">
            I understand the PII Shield anonymises client references before
            any AI call, and I accept this as-is public demo (AGPL-3.0, no
            warranty; my firm remains responsible for compliance).
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
