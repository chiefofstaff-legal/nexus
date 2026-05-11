"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface SOPDef {
  id: string;
  name: string;
  description: string;
  category: string;
  steps: number;
}

interface SOPStep {
  id: string;
  prompt: string;
  step_type: string;
  required: boolean;
  options: string[];
  checklist_items: string[];
  on_false: string | null;
}

export default function SOPsPage() {
  const [sops, setSOPs] = useState<SOPDef[]>([]);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState<SOPStep | null>(null);
  const [progress, setProgress] = useState(0);
  const [sopName, setSopName] = useState("");
  const [response, setResponse] = useState<string | boolean>("");
  const [checkedItems, setCheckedItems] = useState<Set<string>>(new Set());
  const [output, setOutput] = useState<Record<string, unknown> | null>(null);
  const [halted, setHalted] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.listSOPs().then(setSOPs).catch(console.error);
  }, []);

  const startSOP = async (sopId: string) => {
    setLoading(true);
    setOutput(null);
    setHalted(null);
    try {
      const result = await api.startSOP(sopId);
      setExecutionId(result.execution_id);
      setCurrentStep(result.current_step);
      setProgress(result.progress);
      setSopName(result.sop_name);
      setResponse("");
      setCheckedItems(new Set());
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const submitResponse = async () => {
    if (!executionId) return;
    setLoading(true);

    let value: unknown = response;
    if (currentStep?.step_type === "boolean") {
      value = response === "true" || response === true;
    } else if (currentStep?.step_type === "checklist") {
      value = Array.from(checkedItems);
    }

    try {
      const result = await api.respondToSOP(executionId, value);
      if (result.completed) {
        setOutput(result.output);
        setCurrentStep(null);
      } else if (result.halted) {
        setHalted(result.reason);
        setCurrentStep(null);
      } else {
        setCurrentStep(result.current_step);
        setProgress(result.progress);
      }
      setResponse("");
      setCheckedItems(new Set());
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const toggleChecklist = (item: string) => {
    setCheckedItems((prev) => {
      const next = new Set(prev);
      if (next.has(item)) next.delete(item);
      else next.add(item);
      return next;
    });
  };

  return (
    <div className="space-y-12">
      {/* Hero */}
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 lg:col-span-3">
          <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] space-y-3">
            <div><span className="text-[#9a3412]">01</span><span className="ml-3">Select</span></div>
            <div><span className="text-[#9a3412]">02</span><span className="ml-3">Execute</span></div>
            <div><span className="text-[#9a3412]">03</span><span className="ml-3">Output</span></div>
          </div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
            SOP<br />Agent
          </h2>
          <p className="text-lg text-[#4b5563] mt-4 max-w-xl">
            AI-guided standard operating procedures for law firm workflows.
          </p>
        </div>
      </div>

      {/* SOP List */}
      {!executionId && !output && (
        <div className="grid grid-cols-12 gap-6">
          {sops.map((sop, i) => (
            <div key={sop.id} className="col-span-12 md:col-span-4 border border-gray-300 p-6 hover:border-[#ea580c] transition-colors duration-300 group">
              <div className="flex items-start justify-between mb-3">
                <span className="font-mono text-2xl font-bold text-[#9a3412]">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
                  {sop.category.replace("_", " ")}
                </span>
              </div>
              <h3 className="text-xl font-bold tracking-tight mb-2">{sop.name}</h3>
              <p className="text-sm text-[#4b5563] mb-4 leading-relaxed">{sop.description}</p>
              <div className="flex items-center justify-between">
                <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
                  {sop.steps} steps
                </span>
                <button
                  onClick={() => startSOP(sop.id)}
                  disabled={loading}
                  className="border-l-2 border-[#ea580c] bg-[#1a1a1a] text-white px-6 py-2.5 font-mono text-xs tracking-widest uppercase hover:bg-[#ea580c] disabled:opacity-50 transition-colors duration-300"
                >
                  Start
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Active SOP */}
      {executionId && currentStep && (
        <div className="grid grid-cols-12 gap-8">
          <div className="col-span-12 lg:col-span-3">
            <div className="border border-gray-300 p-6">
              <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-2">
                Progress
              </span>
              <div className="text-4xl font-bold tracking-tighter">{progress.toFixed(0)}%</div>
              <div className="w-full bg-gray-300 h-0.5 mt-3">
                <div
                  className="bg-[#ea580c] h-0.5 transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="font-mono text-[10px] tracking-wider text-[#4b5563] mt-3">{sopName}</p>
            </div>
          </div>

          <div className="col-span-12 lg:col-span-9 border border-gray-300 p-8">
            <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-2">
              {currentStep.id.replace(/_/g, " ")}
              {currentStep.required && <span className="text-[#9a3412] ml-2">Required</span>}
            </span>
            <p className="text-2xl font-bold tracking-tight mb-6">{currentStep.prompt}</p>

            {currentStep.step_type === "text_input" && (
              <textarea
                value={response as string}
                onChange={(e) => setResponse(e.target.value)}
                className="w-full border border-gray-300 px-4 py-3 text-sm h-24 resize-none bg-transparent focus:outline-none focus:border-[#ea580c] transition-colors duration-300"
                placeholder="Enter your response..."
              />
            )}

            {currentStep.step_type === "boolean" && (
              <div className="flex gap-4">
                <button
                  onClick={() => setResponse("true")}
                  className={`px-8 py-3 font-mono text-xs tracking-widest uppercase border transition-colors duration-300 ${
                    response === "true"
                      ? "border-[#ea580c] bg-[#ea580c] text-white"
                      : "border-gray-300 hover:border-[#ea580c]"
                  }`}
                >
                  Yes
                </button>
                <button
                  onClick={() => setResponse("false")}
                  className={`px-8 py-3 font-mono text-xs tracking-widest uppercase border transition-colors duration-300 ${
                    response === "false"
                      ? "border-black bg-[#1a1a1a] text-white"
                      : "border-gray-300 hover:border-black"
                  }`}
                >
                  No
                </button>
              </div>
            )}

            {currentStep.step_type === "select" && (
              <div className="space-y-2">
                {currentStep.options.map((option) => (
                  <button
                    key={option}
                    onClick={() => setResponse(option)}
                    className={`block w-full text-left px-6 py-3 font-mono text-xs tracking-wider uppercase border transition-colors duration-300 ${
                      response === option
                        ? "border-[#ea580c] border-l-2 bg-[#1a1a1a] text-white"
                        : "border-gray-300 hover:border-[#ea580c]"
                    }`}
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}

            {currentStep.step_type === "checklist" && (
              <div className="space-y-2">
                {currentStep.checklist_items.map((item) => (
                  <label key={item} className="flex items-center gap-4 p-3 border border-gray-300 hover:border-[#ea580c] cursor-pointer transition-colors duration-300">
                    <input
                      type="checkbox"
                      checked={checkedItems.has(item)}
                      onChange={() => toggleChecklist(item)}
                      className="w-4 h-4 accent-orange-600"
                    />
                    <span className="text-sm">{item}</span>
                  </label>
                ))}
              </div>
            )}

            {currentStep.step_type === "file_upload" && (
              <div className="border border-dashed border-gray-300 p-8 text-center">
                <p className="font-mono text-xs text-[#4b5563] tracking-wider uppercase">
                  File upload — simulated for POC
                </p>
                <button
                  onClick={() => setResponse("file_uploaded_placeholder.pdf")}
                  className="mt-4 border border-gray-300 px-6 py-2.5 font-mono text-xs tracking-widest uppercase hover:border-[#ea580c] hover:text-[#9a3412] transition-colors duration-300"
                >
                  Simulate Upload
                </button>
              </div>
            )}

            {currentStep.on_false && (
              <p className="font-mono text-[10px] tracking-wider text-[#9a3412] mt-3 border-l-2 border-[#ea580c] pl-3">
                Selecting No will halt — {currentStep.on_false}
              </p>
            )}

            <button
              onClick={submitResponse}
              disabled={loading || (!response && currentStep.step_type !== "checklist")}
              className="mt-6 border-l-2 border-[#ea580c] bg-[#1a1a1a] text-white px-8 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#ea580c] disabled:opacity-30 transition-colors duration-300"
            >
              {loading ? "Processing..." : "Continue"}
            </button>
          </div>
        </div>
      )}

      {/* Halted */}
      {halted && (
        <div className="border-l-4 border-[#ea580c] bg-[#1a1a1a] text-white p-8">
          <span className="font-mono text-xs tracking-widest uppercase text-[#9a3412] block mb-2">
            Procedure Halted
          </span>
          <p className="text-lg">{halted}</p>
          <button
            onClick={() => { setHalted(null); setExecutionId(null); }}
            className="mt-6 border border-white text-white px-6 py-2.5 font-mono text-xs tracking-widest uppercase hover:bg-white hover:text-black transition-colors duration-300"
          >
            Back
          </button>
        </div>
      )}

      {/* Completed */}
      {output && (
        <div className="space-y-6">
          <div className="border-l-4 border-[#ea580c] pl-6 py-2">
            <span className="font-mono text-xs tracking-widest uppercase text-[#9a3412] block">
              Complete
            </span>
            <p className="text-xl font-bold tracking-tight mt-1">{(output as Record<string, string>).sop_name}</p>
          </div>
          <div className="border border-gray-300 p-6">
            <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-4">
              Output
            </span>
            <pre className="font-mono text-xs bg-black text-gray-300 p-6 overflow-x-auto leading-relaxed">
              {JSON.stringify(output, null, 2)}
            </pre>
          </div>
          <button
            onClick={() => { setOutput(null); setExecutionId(null); }}
            className="border-l-2 border-[#ea580c] bg-[#1a1a1a] text-white px-8 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#ea580c] transition-colors duration-300"
          >
            Back to SOPs
          </button>
        </div>
      )}
    </div>
  );
}
