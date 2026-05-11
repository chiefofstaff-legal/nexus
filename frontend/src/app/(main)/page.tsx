"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// -- Types -------------------------------------------------------------------

interface TimeSummary {
  total_hours: number;
  total_value_chf: number;
  entry_count: number;
}

interface TimeEntry {
  id: string;
  matter: string | null;
  description: string;
  duration_minutes: number;
  value_chf: number;
  timestamp: string;
}

interface Task {
  id: string;
  title: string;
  assignee: string;
  status: string;
  matter?: string | null;
  deadline?: string | null;
  priority?: string | null;
}

interface DashboardKpis {
  billable_hours: number;
  billable_value: number;
  open_tasks: number;
  documents_indexed: number;
  pending_drafts: number;
}

interface RecentIdr {
  idr_id: string;
  timestamp: string;
  decision_point: string;
  decision: string;
  confidence: number;
  sequence?: number;
}

const DEFAULT_KPIS: DashboardKpis = {
  billable_hours: 0,
  billable_value: 0,
  open_tasks: 0,
  documents_indexed: 0,
  pending_drafts: 0,
};

// -- Primitives --------------------------------------------------------------

function KpiCard({
  eyebrow,
  value,
  caption,
  accent,
}: {
  eyebrow: string;
  value: string;
  caption: string;
  accent?: boolean;
}) {
  const borderCls = accent ? "border-[#b08d57]" : "border-[#d1d5db]";
  const valueCls = accent ? "text-[#0a1628]" : "text-[#0a1628]";
  return (
    <div className={`border ${borderCls} bg-white p-6 md:p-7`}>
      <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
        {eyebrow}
      </div>
      <div className={`text-4xl md:text-5xl font-bold tracking-tighter mt-3 ${valueCls}`}>
        {value}
      </div>
      <div className="font-mono text-[10px] tracking-wider text-[#6b7280] mt-2">
        {caption}
      </div>
    </div>
  );
}

function QuickAction({
  href,
  label,
  caption,
}: {
  href: string;
  label: string;
  caption: string;
}) {
  return (
    <a
      href={href}
      className="group block border border-[#0a1628] bg-[#0a1628] text-white p-6 md:p-8 hover:bg-[#b08d57] hover:border-[#b08d57] transition-colors duration-200"
    >
      <div className="font-mono text-[10px] tracking-widest uppercase text-[#b08d57] group-hover:text-white mb-3">
        Quick action
      </div>
      <div className="text-2xl md:text-3xl font-bold tracking-tighter">
        {label}
      </div>
      <div className="font-mono text-xs tracking-wider text-[#9ca3af] group-hover:text-white mt-3">
        {caption} →
      </div>
    </a>
  );
}

// -- Dashboard page ----------------------------------------------------------

export default function DashboardPage() {
  const [kpis, setKpis] = useState<DashboardKpis>(DEFAULT_KPIS);
  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [idrs, setIdrs] = useState<RecentIdr[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await loadDashboardData();
        if (!cancelled) {
          setKpis(data.kpis);
          setEntries(data.entries);
          setTasks(data.tasks);
          setIdrs(data.idrs);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setError(String(e));
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-12">
      <PositioningBanner />
      <KpiGrid kpis={kpis} loading={loading} />
      <QuickActions />
      <ActivityGrid entries={entries} tasks={tasks} idrs={idrs} loading={loading} />
      {error && <ErrorStrip message={error} />}
    </div>
  );
}

// -- Data loader (single fan-out, resilient to partial failure) --------------

async function loadDashboardData(): Promise<{
  kpis: DashboardKpis;
  entries: TimeEntry[];
  tasks: Task[];
  idrs: RecentIdr[];
}> {
  const [summary, entriesRes, tasksRes, docsRes, idrsRes] = await Promise.allSettled([
    api.timeSummary(),
    api.listTimeEntries(),
    api.listTasks(),
    api.listDocuments(),
    api.getIdrsRecent(5),
  ]);

  const ts = settled<TimeSummary>(summary);
  const entries = settled<{ entries: TimeEntry[] }>(entriesRes)?.entries ?? [];
  const tasks = settled<{ tasks: Task[] }>(tasksRes)?.tasks ?? [];
  const docs = settled<{ documents: unknown[] }>(docsRes)?.documents ?? [];
  const idrs = (settled<{ entries: RecentIdr[] }>(idrsRes)?.entries ?? []).slice(0, 5);

  const openTasks = tasks.filter((t) => t.status !== "DONE" && t.status !== "done").length;
  const pendingDrafts = tasks.filter((t) => {
    const title = (t.title ?? "").toLowerCase();
    return title.includes("draft") && t.status !== "DONE" && t.status !== "done";
  }).length;

  return {
    kpis: {
      billable_hours: ts?.total_hours ?? 0,
      billable_value: ts?.total_value_chf ?? 0,
      open_tasks: openTasks,
      documents_indexed: docs.length,
      pending_drafts: pendingDrafts,
    },
    entries: entries.slice(0, 5),
    tasks: tasks.filter((t) => t.status !== "DONE" && t.status !== "done").slice(0, 5),
    idrs,
  };
}

function settled<T>(r: PromiseSettledResult<unknown>): T | null {
  return r.status === "fulfilled" ? (r.value as T) : null;
}

// -- Sections ----------------------------------------------------------------

function PositioningBanner() {
  return (
    <div className="border border-[#b08d57] bg-[#0a1628] text-white p-6 md:p-8">
      <div className="font-mono text-[10px] tracking-widest uppercase text-[#b08d57] mb-2">
        Positioning
      </div>
      <h1 className="text-3xl md:text-4xl font-bold tracking-tighter leading-tight">
        You are losing billable hours.<br />This fixes it immediately.
      </h1>
      <p className="text-sm md:text-base text-[#9ca3af] mt-4 max-w-2xl">
        Voice-first capture. Swiss-aware routing. HMAC-audited decisions.
        Built for Swiss law firms who bill in six-minute increments.
      </p>
    </div>
  );
}

function KpiGrid({ kpis, loading }: { kpis: DashboardKpis; loading: boolean }) {
  if (loading) return <KpiSkeleton />;
  const hours = kpis.billable_hours.toFixed(1);
  const value = kpis.billable_value.toLocaleString("en-GB");
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-5">
      <KpiCard
        eyebrow="Today billable"
        value={hours}
        caption={`hours · CHF ${value}`}
        accent
      />
      <KpiCard
        eyebrow="Open tasks"
        value={String(kpis.open_tasks)}
        caption="awaiting action"
      />
      <KpiCard
        eyebrow="Documents"
        value={String(kpis.documents_indexed)}
        caption="indexed + classified"
      />
      <KpiCard
        eyebrow="Pending drafts"
        value={String(kpis.pending_drafts)}
        caption="in delegation queue"
      />
    </div>
  );
}

function KpiSkeleton() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-5">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="border border-[#d1d5db] bg-white p-6 md:p-7 animate-pulse">
          <div className="h-3 bg-[#e5e7eb] w-24" />
          <div className="h-10 bg-[#e5e7eb] w-20 mt-4" />
          <div className="h-3 bg-[#e5e7eb] w-32 mt-3" />
        </div>
      ))}
    </div>
  );
}

function QuickActions() {
  const actions = [
    { href: "/time", label: "Capture time", caption: "Voice log" },
    { href: "/delegation", label: "Delegate task", caption: "Assign work" },
    { href: "/drafting", label: "New draft", caption: "Template or voice" },
    { href: "/search", label: "Search documents", caption: "Semantic lookup" },
  ];
  return (
    <div>
      <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-4">
        Quick actions
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {actions.map((a) => (
          <QuickAction key={a.href} {...a} />
        ))}
      </div>
    </div>
  );
}

function ActivityGrid({
  entries,
  tasks,
  idrs,
  loading,
}: {
  entries: TimeEntry[];
  tasks: Task[];
  idrs: RecentIdr[];
  loading: boolean;
}) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ActivityPanel title="Recent time entries" link={{ href: "/time", label: "All time" }}>
          {loading ? (
            <FeedSkeleton />
          ) : entries.length === 0 ? (
            <EmptyRow message="No time logged yet — speak into Capture to start." />
          ) : (
            entries.map((e) => <TimeRow key={e.id} entry={e} />)
          )}
        </ActivityPanel>
        <ActivityPanel title="Open tasks" link={{ href: "/delegation", label: "All tasks" }}>
          {loading ? (
            <FeedSkeleton />
          ) : tasks.length === 0 ? (
            <EmptyRow message="No open tasks — delegate one via voice." />
          ) : (
            tasks.map((t) => <TaskRow key={t.id} task={t} />)
          )}
        </ActivityPanel>
      </div>
      <ActivityPanel title="Recent decisions" link={{ href: "/idr", label: "Audit log" }}>
        {loading ? (
          <FeedSkeleton />
        ) : idrs.length === 0 ? (
          <EmptyRow message="No decisions logged yet — route a query to start the audit chain." />
        ) : (
          idrs.map((r) => <IdrRow key={r.idr_id} record={r} />)
        )}
      </ActivityPanel>
    </div>
  );
}

function ActivityPanel({
  title,
  link,
  children,
}: {
  title: string;
  link: { href: string; label: string };
  children: React.ReactNode;
}) {
  return (
    <div className="border border-[#d1d5db] bg-white">
      <div className="px-5 py-4 border-b border-[#e5e7eb] flex items-center justify-between">
        <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
          {title}
        </span>
        <a
          href={link.href}
          className="font-mono text-[10px] tracking-widest uppercase text-[#0a1628] hover:text-[#b08d57] transition-colors duration-200"
        >
          {link.label} →
        </a>
      </div>
      <div className="divide-y divide-[#f1f3f5]">{children}</div>
    </div>
  );
}

function TimeRow({ entry }: { entry: TimeEntry }) {
  const hours = (entry.duration_minutes / 60).toFixed(1);
  return (
    <div className="px-5 py-4 flex items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="text-sm font-bold text-[#0a1628] truncate">
          {entry.matter || "Untagged matter"}
        </div>
        <div className="text-xs text-[#4b5563] mt-1 truncate">
          {entry.description}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-sm font-bold text-[#0a1628]">
          CHF {entry.value_chf.toFixed(0)}
        </div>
        <div className="font-mono text-[10px] tracking-wider text-[#6b7280] mt-1">
          {hours}h
        </div>
      </div>
    </div>
  );
}

function TaskRow({ task }: { task: Task }) {
  return (
    <div className="px-5 py-4 flex items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="text-sm font-bold text-[#0a1628] truncate">
          {task.title}
        </div>
        <div className="text-xs text-[#4b5563] mt-1 truncate">
          {task.matter ? `${task.matter} · ` : ""}
          {task.assignee}
        </div>
      </div>
      <span className="shrink-0 font-mono text-[10px] tracking-widest uppercase border border-[#d1d5db] px-2 py-1 text-[#374151]">
        {task.status}
      </span>
    </div>
  );
}

function IdrRow({ record }: { record: RecentIdr }) {
  const pct = Math.round((record.confidence ?? 0) * 100);
  const time = record.timestamp?.split("T")[1]?.split(".")[0] ?? "";
  return (
    <div className="px-5 py-4 flex items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="text-sm font-bold text-[#0a1628] truncate">
          {record.decision_point || "Routing decision"}
        </div>
        <div className="font-mono text-[10px] tracking-wider text-[#4b5563] mt-1">
          {record.decision} · {time}
        </div>
      </div>
      <span className="shrink-0 font-mono text-[10px] tracking-wider border border-[#d1d5db] px-2 py-1 text-[#374151]">
        {pct}%
      </span>
    </div>
  );
}

function FeedSkeleton() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <div key={i} className="px-5 py-4 animate-pulse flex justify-between">
          <div className="space-y-2">
            <div className="h-3 bg-[#e5e7eb] w-40" />
            <div className="h-3 bg-[#e5e7eb] w-56" />
          </div>
          <div className="h-3 bg-[#e5e7eb] w-12" />
        </div>
      ))}
    </>
  );
}

function EmptyRow({ message }: { message: string }) {
  return (
    <div className="px-5 py-8 font-mono text-xs tracking-wider text-[#6b7280] text-center">
      {message}
    </div>
  );
}

function ErrorStrip({ message }: { message: string }) {
  return (
    <div className="border border-[#dc2626] text-[#dc2626] px-6 py-4 font-mono text-xs tracking-wider">
      Dashboard partial: {message}
    </div>
  );
}
