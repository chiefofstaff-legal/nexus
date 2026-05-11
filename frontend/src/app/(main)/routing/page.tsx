"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface RoutingDecision {
  sensitivity_level: string;
  sensitivity_score: number;
  model_used: string;
  provider: string;
  routing_reason: string;
  pii_types_detected: string[];
  latency_ms: number;
  estimated_cost_usd: number;
}

interface AuditEntry {
  event: string;
  sensitivity_level: string;
  model: string;
  provider: string;
  latency_ms: number;
  cost_usd: number;
  timestamp: string;
  sequence: number;
}

const LEVEL_STYLES: Record<string, string> = {
  public: "border-gray-300 text-[#4b5563]",
  internal: "border-[#ea580c] text-[#9a3412]",
  confidential: "border-black text-black bg-[#1a1a1a] text-white",
};

export default function RoutingPage() {
  const [prompt, setPrompt] = useState("");
  const [response, setResponse] = useState("");
  const [decision, setDecision] = useState<RoutingDecision | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const loadAudit = useCallback(async () => {
    try {
      const result = await api.getRoutingAudit();
      setAudit(result.entries ?? []);
    } catch (e) {
      console.error(e);
    }
  }, []);

  // Auto-load the audit trail the moment the page mounts. Previously the
  // user had to click "Load" before anything appeared — the chain was
  // already there, the UI just wasn't asking for it.
  useEffect(() => {
    loadAudit();
  }, [loadAudit]);

  const handleQuery = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    try {
      const result = await api.routeQuery(prompt);
      setResponse(result.response);
      setDecision(result.decision);
    } catch (e) {
      setResponse(`Error: ${e}`);
    }
    setLoading(false);
    // Refresh immediately so the new routing entry shows up without a click.
    loadAudit();
  };

  const handleClassify = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    try {
      const result = await api.classifySensitivity(prompt);
      const rationale =
        result.confidence_rationale || `PII: ${result.pii_types_detected.join(", ") || "none detected"}`;
      setDecision({
        sensitivity_level: result.sensitivity_level,
        sensitivity_score: result.sensitivity_score,
        model_used: "(council classify-only)",
        provider: result.synthesis_method || "council",
        routing_reason: rationale,
        pii_types_detected: result.pii_types_detected,
        latency_ms: 0,
        estimated_cost_usd: 0,
      });
      const reasoning = result.reasoning || "";
      setResponse(
        `Sensitivity classification via council (no response generated). ` +
          `See /idr for the signed decision record.\n\n` +
          (reasoning ? `Council reasoning:\n${reasoning}` : ""),
      );
    } catch (e) {
      setResponse(`Error: ${e}`);
    }
    setLoading(false);
    loadAudit();
  };

  return (
    <div className="space-y-12">
      {/* Hero — asymmetric */}
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 lg:col-span-3">
          <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] space-y-3">
            <div><span className="text-[#9a3412]">01</span><span className="ml-3">Classify</span></div>
            <div><span className="text-[#9a3412]">02</span><span className="ml-3">Route</span></div>
            <div><span className="text-[#9a3412]">03</span><span className="ml-3">Audit</span></div>
          </div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
            LLM<br />Orchestration
          </h2>
          <p className="text-lg text-[#4b5563] mt-4 max-w-xl">
            Sensitivity-based routing between frontier and on-prem models. Every decision audited.
          </p>
        </div>
      </div>

      {/* Query Input */}
      <div className="border border-gray-300 p-8">
        <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563] block mb-4">
          Test Query
        </span>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter a prompt — include PII (names, emails, account numbers) to trigger sensitivity routing..."
          className="w-full border border-gray-300 px-4 py-3 text-sm h-32 resize-none bg-transparent focus:outline-none focus:border-[#ea580c] transition-colors duration-300"
        />
        <div className="flex gap-4 mt-4">
          <button
            onClick={handleClassify}
            disabled={loading}
            className="border border-gray-300 px-6 py-3 font-mono text-xs tracking-widest uppercase hover:border-[#ea580c] hover:text-[#9a3412] disabled:opacity-50 transition-colors duration-300"
          >
            Classify Only
          </button>
          <button
            onClick={handleQuery}
            disabled={loading}
            className="border border-black bg-[#1a1a1a] text-white px-8 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#ea580c] hover:border-[#ea580c] disabled:opacity-50 transition-colors duration-300"
          >
            {loading ? "Routing..." : "Route & Execute"}
          </button>
        </div>
      </div>

      {/* Routing Decision — asymmetric 3+5+4 */}
      {decision && (
        <div className="grid grid-cols-12 gap-6">
          <div className={`col-span-12 md:col-span-3 border p-6 ${LEVEL_STYLES[decision.sensitivity_level] || "border-gray-300"}`}>
            <span className="font-mono text-[10px] tracking-widest uppercase block mb-2 opacity-60">
              Sensitivity
            </span>
            <div className="text-3xl font-bold tracking-tighter uppercase">
              {decision.sensitivity_level}
            </div>
            <div className="font-mono text-xs mt-2">
              {(decision.sensitivity_score * 100).toFixed(1)}%
            </div>
          </div>
          <div className="col-span-12 md:col-span-5 border border-gray-300 p-6">
            <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-2">
              Model Selected
            </span>
            <div className="text-xl font-bold tracking-tight font-mono">
              {decision.model_used}
            </div>
            <div className="font-mono text-xs text-[#4b5563] mt-1">{decision.provider}</div>
          </div>
          <div className="col-span-12 md:col-span-4 border border-gray-300 p-6">
            <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-2">
              Performance
            </span>
            <div className="font-mono text-xs space-y-1.5">
              <div>Latency <span className="text-black font-bold">{decision.latency_ms.toFixed(0)}ms</span></div>
              <div>Cost <span className="text-black font-bold">${decision.estimated_cost_usd.toFixed(6)}</span></div>
            </div>
          </div>
        </div>
      )}

      {/* PII Detected */}
      {decision && decision.pii_types_detected.length > 0 && (
        <div className="border-l-2 border-[#ea580c] pl-6 py-2">
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-2">
            PII Detected
          </span>
          <div className="flex flex-wrap gap-2">
            {decision.pii_types_detected.map((pii, i) => (
              <span key={i} className="font-mono text-[10px] tracking-wider border border-gray-300 px-2 py-1">
                {pii}
              </span>
            ))}
          </div>
          <p className="font-mono text-xs text-[#4b5563] mt-2">{decision.routing_reason}</p>
        </div>
      )}

      {/* Response */}
      {response && (
        <div className="border border-gray-300 p-8">
          <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563] block mb-4">
            Response
          </span>
          <div className="text-sm text-[#4b5563] whitespace-pre-wrap font-mono bg-black text-gray-300 p-6 leading-relaxed">
            {response}
          </div>
        </div>
      )}

      {/* Audit Trail */}
      <div className="border border-gray-300 p-8">
        <div className="flex items-center justify-between mb-6">
          <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
            Audit Trail
          </span>
          <button
            onClick={loadAudit}
            className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] hover:text-[#9a3412] transition-colors duration-300"
            aria-label="Refresh audit trail"
          >
            Refresh
          </button>
        </div>
        {audit.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full font-mono text-[10px] tracking-wider">
              <thead>
                <tr className="border-b border-gray-300">
                  <th className="text-left py-2 pr-4 uppercase text-[#4b5563]">#</th>
                  <th className="text-left py-2 pr-4 uppercase text-[#4b5563]">Level</th>
                  <th className="text-left py-2 pr-4 uppercase text-[#4b5563]">Model</th>
                  <th className="text-left py-2 pr-4 uppercase text-[#4b5563]">Latency</th>
                  <th className="text-left py-2 pr-4 uppercase text-[#4b5563]">Cost</th>
                  <th className="text-left py-2 uppercase text-[#4b5563]">Time</th>
                </tr>
              </thead>
              <tbody>
                {audit.slice(-20).reverse().map((entry, i) => (
                  <tr key={i} className="border-b border-gray-200 hover:bg-[#d1d5db]/30 transition-colors duration-300">
                    <td className="py-2 pr-4 text-[#9a3412]">{entry.sequence}</td>
                    <td className="py-2 pr-4 uppercase">{entry.sensitivity_level}</td>
                    <td className="py-2 pr-4">{entry.model}</td>
                    <td className="py-2 pr-4">{entry.latency_ms}ms</td>
                    <td className="py-2 pr-4">${entry.cost_usd}</td>
                    <td className="py-2 text-[#4b5563]">{entry.timestamp?.split("T")[1]?.split(".")[0]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="font-mono text-xs text-[#4b5563]">No audit entries. Route a query first.</p>
        )}
      </div>
    </div>
  );
}
