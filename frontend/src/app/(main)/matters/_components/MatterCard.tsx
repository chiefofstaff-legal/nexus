"use client";

import Link from "next/link";
import { type Matter, relativeTime } from "../_lib/matters-client";

interface MatterCardProps {
  matter: Matter;
  documentCount?: number;
}

// Card surfaces the four signals operators scan for: name (identity), client
// (filter), age (recency), and document count (load). Colour palette mirrors
// the IDR list rows so the eye trains on one visual grammar across pages.
export function MatterCard({ matter, documentCount }: MatterCardProps) {
  const archived = !!matter.archived_at;
  return (
    <Link
      href={`/matters/${encodeURIComponent(matter.id)}`}
      className={`block border bg-white p-5 md:p-6 min-h-32 transition-colors duration-200 hover:border-[#9a3412] ${
        archived ? "border-[#d1d5db] opacity-60" : "border-[#d1d5db]"
      }`}
      data-testid="matter-card"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <span className="font-mono text-[10px] tracking-widest uppercase text-[#9a3412]">
          {archived ? "Archived" : "Active"}
        </span>
        <span className="font-mono text-[10px] tracking-wider text-[#9ca3af]">
          {relativeTime(matter.created_at)}
        </span>
      </div>
      <h3
        data-testid="matter-card-name"
        className="text-lg md:text-xl font-bold tracking-tight text-[#1a1a1a] break-words leading-tight mb-2"
      >
        {matter.name}
      </h3>
      <div
        data-testid="matter-card-client"
        className="font-mono text-xs tracking-wider text-[#4b5563] break-words mb-4 min-h-4"
      >
        {matter.client || "—"}
      </div>
      <div className="flex items-center justify-between border-t border-[#e5e7eb] pt-3">
        <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
          Documents
        </span>
        <span
          data-testid="matter-card-doc-count"
          className="font-mono text-xs tracking-widest text-[#1a1a1a]"
        >
          {documentCount ?? "—"}
        </span>
      </div>
    </Link>
  );
}
