"use client";

import type { ChangeEvent } from "react";

export type SearchMode = "keyword" | "semantic" | "hybrid";
export type SearchLang = "en" | "de";

export interface SearchModeToggleValue {
  mode: SearchMode;
  lang: SearchLang;
}

interface SearchModeToggleProps {
  mode: SearchMode;
  lang: SearchLang;
  onChange: (value: SearchModeToggleValue) => void;
  disabled?: boolean;
}

const MODE_OPTIONS: { value: SearchMode; label: string; hint: string }[] = [
  { value: "keyword", label: "Keyword", hint: "Exact phrase match" },
  { value: "semantic", label: "Semantic", hint: "Meaning-based" },
  { value: "hybrid", label: "Hybrid", hint: "Best of both" },
];

const LANG_OPTIONS: { value: SearchLang; label: string }[] = [
  { value: "en", label: "EN — English" },
  { value: "de", label: "DE — German" },
];

export function SearchModeToggle({
  mode,
  lang,
  onChange,
  disabled = false,
}: SearchModeToggleProps) {
  const handleModeClick = (next: SearchMode) => {
    if (next === mode) return;
    onChange({ mode: next, lang });
  };

  const handleLangChange = (e: ChangeEvent<HTMLSelectElement>) => {
    onChange({ mode, lang: e.target.value as SearchLang });
  };

  return (
    <div
      data-testid="search-mode-toggle"
      className="flex flex-col sm:flex-row gap-2 sm:gap-3 items-stretch sm:items-center"
    >
      <div
        role="group"
        aria-label="Search mode"
        className="inline-flex border border-[#d1d5db] divide-x divide-[#d1d5db]"
      >
        {MODE_OPTIONS.map((opt) => {
          const active = opt.value === mode;
          return (
            <button
              key={opt.value}
              type="button"
              data-testid={`search-mode-${opt.value}`}
              aria-pressed={active}
              title={opt.hint}
              onClick={() => handleModeClick(opt.value)}
              disabled={disabled}
              className={
                "px-4 py-2 font-mono text-[10px] tracking-widest uppercase transition-colors duration-200 disabled:opacity-40 " +
                (active
                  ? "bg-[#0a1628] text-white"
                  : "bg-white text-[#374151] hover:bg-[#f3f4f6]")
              }
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      <select
        data-testid="search-lang-select"
        aria-label="Search language"
        value={lang}
        onChange={handleLangChange}
        disabled={disabled}
        className="border border-[#d1d5db] px-3 py-2 text-sm bg-white font-mono focus:outline-none focus:border-[#0a1628] transition-colors duration-200 disabled:opacity-40"
      >
        {LANG_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
