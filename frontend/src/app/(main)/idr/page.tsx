"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface CouncilVote {
  model: string;
  provider: string;
  decision: string;
  confidence: number;
  reasoning: string;
  latency_ms: number;
  error: string | null;
}

interface LatestReview {
  sequence: number;
  timestamp: string;
  reviewer_id?: string;
  reviewer_label?: string;
  notes?: string;
  verdict: string;
}

interface IntentDecisionRecord {
  idr_id: string;
  timestamp: string;
  decision_point: string;
  input_hash: string;
  input_summary: string;
  decision: string;
  confidence: number;
  confidence_rationale: string;
  reasoning: string;
  council_votes: CouncilVote[];
  synthesis_method: string;
  falsification_criterion: string;
  falsification_status: string;
  falsification_evidence: string | null;
  metadata: Record<string, unknown>;
  entry_hash?: string;
  chain_hash?: string;
  sequence?: number;
  effective_falsification_status?: string;
  latest_review?: LatestReview;
}

interface ChainVerifyResult {
  valid: boolean;
  total_entries: number;
  signed_entries: number;
  unsigned_entries: number;
  first_break: number | null;
  break_reason: string | null;
  last_sequence: number;
}

const DECISION_STYLE: Record<string, string> = {
  confidential: "border-[#1a1a1a] bg-[#1a1a1a] text-white",
  internal: "border-[#ea580c] text-[#9a3412]",
  public: "border-[#9ca3af] text-[#4b5563]",
};

function decisionChipClass(decision: string): string {
  const key = decision.toLowerCase();
  return DECISION_STYLE[key] ?? "border-[#9ca3af] text-[#4b5563]";
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      day: "2-digit",
      month: "short",
    });
  } catch {
    return iso;
  }
}

function truncate(text: string, n: number): string {
  if (!text) return "";
  return text.length > n ? text.slice(0, n - 1) + "…" : text;
}

interface ReviewDraft {
  status: "confirmed" | "refuted" | "inconclusive";
  reviewer_id: string;
  reviewer_label: string;
  notes: string;
}

const EMPTY_DRAFT: ReviewDraft = {
  status: "confirmed",
  reviewer_id: "",
  reviewer_label: "",
  notes: "",
};

const STATUS_BADGE: Record<string, string> = {
  pending: "border-[#d1d5db] text-[#4b5563]",
  confirmed: "border-[#16a34a] text-[#15803d] bg-[#f0fdf4]",
  refuted: "border-[#dc2626] text-[#991b1b] bg-[#fef2f2]",
  inconclusive: "border-[#eab308] text-[#854d0e] bg-[#fefce8]",
};

export default function IDRPage() {
  const [entries, setEntries] = useState<IntentDecisionRecord[]>([]);
  const [verify, setVerify] = useState<ChainVerifyResult | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<number, ReviewDraft>>({});
  const [submitting, setSubmitting] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [recent, verifyResult] = await Promise.all([
        api.getIdrsRecent(100),
        api.verifyIdrChain(),
      ]);
      setEntries(recent.entries ?? []);
      setVerify(verifyResult);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const getDraft = (seq: number): ReviewDraft => drafts[seq] ?? EMPTY_DRAFT;
  const updateDraft = (seq: number, patch: Partial<ReviewDraft>) =>
    setDrafts((prev) => ({ ...prev, [seq]: { ...getDraft(seq), ...patch } }));

  const submitReview = async (seq: number) => {
    const draft = getDraft(seq);
    if (!draft.reviewer_id.trim()) {
      setError("reviewer_id is required");
      return;
    }
    if (draft.status === "refuted" && !draft.reviewer_label.trim()) {
      setError("refuted reviews require the label the reviewer would assign");
      return;
    }
    setError(null);
    setSubmitting(seq);
    try {
      await api.reviewIdr(seq, {
        status: draft.status,
        reviewer_id: draft.reviewer_id.trim(),
        reviewer_label: draft.reviewer_label.trim() || undefined,
        notes: draft.notes.trim(),
      });
      setDrafts((prev) => ({ ...prev, [seq]: EMPTY_DRAFT }));
      await refresh();
    } catch (e) {
      setError(String(e));
    }
    setSubmitting(null);
  };

  return (
    <div className="space-y-12">
      {/* Hero — asymmetric */}
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 lg:col-span-3">
          <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] space-y-3">
            <div><span className="text-[#9a3412]">01</span><span className="ml-3">Classify</span></div>
            <div><span className="text-[#9a3412]">02</span><span className="ml-3">Council</span></div>
            <div><span className="text-[#9a3412]">03</span><span className="ml-3">Falsify</span></div>
            <div><span className="text-[#9a3412]">04</span><span className="ml-3">Chain</span></div>
          </div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
            Intent<br />Decision<br />Records
          </h2>
          <p className="text-lg text-[#4b5563] mt-4 max-w-xl">
            Every AI decision is recorded, signed, and open to challenge. A multi-model
            council votes independently — confidence is derived from agreement, not
            self-reported. Each record states the exact observation that would prove it
            wrong. Chain integrity is HMAC-SHA256. Nothing is deleted; reviews are
            appended. Built to survive a regulator asking <em>why did the AI route this?</em>
          </p>
        </div>
      </div>

      {/* Chain status bar */}
      <div className="border border-[#d1d5db] bg-white">
        <div className="px-6 py-4 flex flex-wrap items-center gap-x-8 gap-y-2 font-mono text-sm tracking-widest uppercase text-[#4b5563]">
          {verify ? (
            <>
              <span className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 inline-block ${
                    verify.valid ? "bg-[#16a34a]" : "bg-[#dc2626]"
                  }`}
                />
                {verify.valid ? "Chain verified" : "Chain broken"}
              </span>
              <span>
                <span className="text-[#9a3412]">{verify.total_entries}</span> entries
              </span>
              <span>
                <span className="text-[#9a3412]">{verify.signed_entries}</span> signed
              </span>
              <span>
                seq <span className="text-[#9a3412]">{verify.last_sequence}</span>
              </span>
              {verify.break_reason && (
                <span className="text-[#dc2626]">{verify.break_reason}</span>
              )}
            </>
          ) : (
            <span>Loading chain status…</span>
          )}
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="ml-auto border border-[#d1d5db] px-4 py-1 text-xs tracking-widest uppercase hover:border-[#9a3412] hover:text-[#9a3412] transition-colors duration-300 disabled:opacity-50"
          >
            {loading ? "…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <div className="border border-[#dc2626] text-[#dc2626] px-6 py-4 font-mono text-sm">
          {error}
        </div>
      )}

      {/* IDR log */}
      <div className="border border-[#d1d5db] bg-white">
        <div className="grid grid-cols-12 gap-4 px-6 py-3 border-b border-[#d1d5db] bg-[#fafafa] font-mono text-xs tracking-widest uppercase text-[#4b5563]">
          <div className="col-span-1">Seq</div>
          <div className="col-span-2">Timestamp</div>
          <div className="col-span-3">Decision Point</div>
          <div className="col-span-2">Decision</div>
          <div className="col-span-3">Confidence</div>
          <div className="col-span-1 text-right">Method</div>
        </div>
        {entries.length === 0 && !loading && (
          <div className="px-6 py-12 text-center font-mono text-sm text-[#4b5563] tracking-widest uppercase">
            Empty chain. Route a query at <a href="/routing" className="text-[#9a3412] underline">/routing</a> to write the first IDR.
          </div>
        )}
        {entries.map((entry) => {
          const id = entry.idr_id;
          const isOpen = expanded.has(id);
          const confPct = Math.round(entry.confidence * 100);
          return (
            <div key={id} className="border-b border-[#e5e7eb] last:border-b-0">
              <button
                type="button"
                onClick={() => toggleExpand(id)}
                className="w-full grid grid-cols-12 gap-4 px-6 py-4 text-left hover:bg-[#fafafa] transition-colors duration-150"
              >
                <div className="col-span-1 font-mono text-sm tracking-widest text-[#9a3412]">
                  #{entry.sequence ?? "—"}
                </div>
                <div className="col-span-2 font-mono text-xs text-[#4b5563]">
                  {formatTimestamp(entry.timestamp)}
                </div>
                <div className="col-span-3 text-sm text-[#1a1a1a]">
                  {(entry.decision_point ?? "").replace(/_/g, " ")}
                </div>
                <div className="col-span-2">
                  <span
                    className={`inline-block border px-3 py-1 font-mono text-xs tracking-widest uppercase ${decisionChipClass(entry.decision)}`}
                  >
                    {entry.decision}
                  </span>
                </div>
                <div className="col-span-3 flex items-center gap-3">
                  <div className="flex-1 h-1 bg-[#e5e7eb]">
                    <div
                      className="h-1 bg-[#ea580c]"
                      style={{ width: `${confPct}%` }}
                    />
                  </div>
                  <span className="font-mono text-xs tracking-widest text-[#4b5563] w-10 text-right">
                    {confPct}%
                  </span>
                </div>
                <div className="col-span-1 text-right font-mono text-xs tracking-widest text-[#4b5563] uppercase">
                  {isOpen ? "−" : "+"}
                </div>
              </button>
              {isOpen && (
                <div className="px-6 py-6 bg-[#fafafa] border-t border-[#e5e7eb] space-y-6">
                  <div className="grid grid-cols-12 gap-6">
                    <div className="col-span-12 md:col-span-6">
                      <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] mb-2">
                        Input summary
                      </div>
                      <div className="text-sm text-[#1a1a1a]">
                        {entry.input_summary}
                      </div>
                      <div className="font-mono text-xs text-[#9ca3af] mt-2">
                        hash: {truncate(entry.input_hash, 64)}
                      </div>
                    </div>
                    <div className="col-span-12 md:col-span-6">
                      <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] mb-2">
                        Synthesis
                      </div>
                      <div className="text-sm text-[#1a1a1a]">
                        {(entry.synthesis_method ?? "").replace(/_/g, " ")}
                      </div>
                      <div className="text-xs text-[#4b5563] mt-2">
                        {entry.confidence_rationale}
                      </div>
                    </div>
                  </div>

                  <div>
                    <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] mb-2">
                      Council votes
                    </div>
                    {(entry.council_votes ?? []).length === 0 ? (
                      <div className="text-xs text-[#9ca3af]">no votes recorded</div>
                    ) : (
                      <div className="border border-[#e5e7eb]">
                        {(entry.council_votes ?? []).map((v, i) => (
                          <div
                            key={`${v.provider}-${v.model}-${i}`}
                            className="grid grid-cols-12 gap-4 px-4 py-3 border-b border-[#e5e7eb] last:border-b-0 text-sm"
                          >
                            <div className="col-span-3 font-mono text-xs tracking-widest uppercase text-[#4b5563]">
                              {v.provider}
                            </div>
                            <div className="col-span-3 font-mono text-xs text-[#4b5563]">
                              {truncate(v.model, 28)}
                            </div>
                            <div className="col-span-2">
                              {v.error ? (
                                <span className="text-[#dc2626] font-mono text-xs">
                                  error
                                </span>
                              ) : (
                                <span
                                  className={`inline-block border px-2 py-0.5 font-mono text-[10px] tracking-widest uppercase ${decisionChipClass(v.decision)}`}
                                >
                                  {v.decision}
                                </span>
                              )}
                            </div>
                            <div className="col-span-2 font-mono text-xs text-[#4b5563]">
                              {v.error ? "—" : `${Math.round(v.confidence * 100)}%`}
                            </div>
                            <div className="col-span-2 font-mono text-xs text-[#9ca3af] text-right">
                              {Math.round(v.latency_ms)} ms
                            </div>
                            {v.reasoning && !v.error && (
                              <div className="col-span-12 text-xs text-[#4b5563] italic whitespace-pre-wrap break-words">
                                {v.reasoning}
                              </div>
                            )}
                            {v.error && (
                              <div className="col-span-12 text-xs text-[#dc2626] font-mono">
                                {v.error}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] mb-2">
                      Reasoning
                    </div>
                    <div className="text-sm text-[#1a1a1a] whitespace-pre-wrap break-words">
                      {entry.reasoning || "—"}
                    </div>
                  </div>

                  <div>
                    <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] mb-2">
                      Falsification criterion
                    </div>
                    <div className="text-sm text-[#1a1a1a] italic whitespace-pre-wrap break-words">
                      {entry.falsification_criterion}
                    </div>
                    {(() => {
                      const eff = entry.effective_falsification_status || entry.falsification_status;
                      const badge = STATUS_BADGE[eff] || STATUS_BADGE.pending;
                      return (
                        <div className="mt-3 flex items-center gap-3 flex-wrap">
                          <span className={`inline-block font-mono text-xs tracking-widest uppercase border px-3 py-1 ${badge}`}>
                            status: {eff}
                          </span>
                          {entry.latest_review && (
                            <span className="font-mono text-[10px] tracking-wider text-[#4b5563]">
                              reviewed by {entry.latest_review.reviewer_id || "unknown"}
                              {entry.latest_review.reviewer_label && ` (would assign: ${entry.latest_review.reviewer_label})`}
                            </span>
                          )}
                        </div>
                      );
                    })()}
                    {entry.latest_review?.notes && (
                      <div className="mt-2 text-xs text-[#4b5563] whitespace-pre-wrap break-words border-l-2 border-[#d1d5db] pl-3">
                        {entry.latest_review.notes}
                      </div>
                    )}
                  </div>

                  {entry.sequence !== undefined && entry.decision_point !== "falsification_review" && (
                    <div className="border border-dashed border-[#d1d5db] p-4">
                      <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] mb-3">
                        Record a review
                      </div>
                      {(() => {
                        const seq = entry.sequence!;
                        const draft = getDraft(seq);
                        const isSubmitting = submitting === seq;
                        return (
                          <div className="grid grid-cols-12 gap-3 text-sm">
                            <div className="col-span-12 md:col-span-3">
                              <label className="block font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-1">
                                Verdict
                              </label>
                              <select
                                value={draft.status}
                                onChange={(e) =>
                                  updateDraft(seq, { status: e.target.value as ReviewDraft["status"] })
                                }
                                className="w-full border border-[#d1d5db] bg-white px-2 py-1.5 font-mono text-xs uppercase"
                              >
                                <option value="confirmed">Confirmed</option>
                                <option value="refuted">Refuted</option>
                                <option value="inconclusive">Inconclusive</option>
                              </select>
                            </div>
                            <div className="col-span-12 md:col-span-4">
                              <label className="block font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-1">
                                Reviewer ID
                              </label>
                              <input
                                type="text"
                                value={draft.reviewer_id}
                                onChange={(e) => updateDraft(seq, { reviewer_id: e.target.value })}
                                placeholder="e.g. v.scheepers@codetonight"
                                className="w-full border border-[#d1d5db] bg-white px-2 py-1.5 font-mono text-xs"
                              />
                            </div>
                            {draft.status === "refuted" && (
                              <div className="col-span-12 md:col-span-5">
                                <label className="block font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-1">
                                  Label you would assign (required for refuted)
                                </label>
                                <input
                                  type="text"
                                  value={draft.reviewer_label}
                                  onChange={(e) => updateDraft(seq, { reviewer_label: e.target.value })}
                                  placeholder="e.g. confidential"
                                  className="w-full border border-[#d1d5db] bg-white px-2 py-1.5 font-mono text-xs"
                                />
                              </div>
                            )}
                            <div className="col-span-12">
                              <label className="block font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-1">
                                Notes
                              </label>
                              <textarea
                                value={draft.notes}
                                onChange={(e) => updateDraft(seq, { notes: e.target.value })}
                                rows={2}
                                placeholder="Reasoning the reviewer wants in the chain (visible in future audits)"
                                className="w-full border border-[#d1d5db] bg-white px-2 py-1.5 text-xs"
                              />
                            </div>
                            <div className="col-span-12 flex justify-end">
                              <button
                                type="button"
                                onClick={() => submitReview(seq)}
                                disabled={isSubmitting}
                                className="border border-[#1a1a1a] bg-[#1a1a1a] text-white px-5 py-1.5 font-mono text-xs tracking-widest uppercase hover:bg-[#9a3412] hover:border-[#9a3412] transition-colors duration-300 disabled:opacity-50"
                              >
                                {isSubmitting ? "Submitting…" : "Append review to chain"}
                              </button>
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  )}

                  {entry.chain_hash && (
                    <div className="font-mono text-[10px] text-[#9ca3af] break-all">
                      chain: {entry.chain_hash}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
