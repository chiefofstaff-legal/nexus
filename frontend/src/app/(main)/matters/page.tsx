"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  mattersClient,
  type Matter,
  type MatterDocument,
} from "./_lib/matters-client";
import { MatterCard } from "./_components/MatterCard";
import { CreateMatterDialog } from "./_components/CreateMatterDialog";

type Tab = "active" | "archived";

// Index page. Mirrors /idr's hero (asymmetric 12-col grid, large display type)
// and the document-list pattern (card grid, mobile-fluid, desktop fixed). The
// document-count map is fetched lazily per matter to avoid a backend join.
export default function MattersPage() {
  const [matters, setMatters] = useState<Matter[]>([]);
  const [docCounts, setDocCounts] = useState<Record<string, number>>({});
  const [tab, setTab] = useState<Tab>("active");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = (await mattersClient.listMatters(tab === "archived")) ?? [];
      setMatters(list);
      // Lazy fetch document counts in parallel — failures collapse to 0.
      const counts = await Promise.all(
        list.map(async (m): Promise<[string, number]> => {
          try {
            const docs: MatterDocument[] = await mattersClient.listMatterDocuments(m.id);
            return [m.id, docs.length];
          } catch {
            return [m.id, 0];
          }
        }),
      );
      setDocCounts(Object.fromEntries(counts));
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, [tab]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCreated = (m: Matter) => {
    if (tab === "active") {
      setMatters((prev) => [m, ...prev]);
      setDocCounts((prev) => ({ ...prev, [m.id]: 0 }));
    }
  };

  const total = matters.length;
  const subhead = useMemo(() => {
    if (loading) return "Loading…";
    return `${total} ${tab === "active" ? "active" : "archived"} ${total === 1 ? "matter" : "matters"}`;
  }, [loading, total, tab]);

  return (
    <div className="space-y-12">
      <Hero
        subhead={subhead}
        tab={tab}
        onTabChange={setTab}
        onNew={() => setDialogOpen(true)}
      />

      {error && (
        <div
          role="alert"
          className="border border-[#dc2626] text-[#dc2626] px-6 py-4 font-mono text-sm"
        >
          {error}
        </div>
      )}

      {!loading && matters.length === 0 ? (
        <EmptyMatters onNew={() => setDialogOpen(true)} archived={tab === "archived"} />
      ) : (
        <div
          data-testid="matter-grid"
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6"
        >
          {matters.map((m) => (
            <MatterCard key={m.id} matter={m} documentCount={docCounts[m.id]} />
          ))}
        </div>
      )}

      {/* Mobile floating action — desktop uses the header button */}
      <button
        type="button"
        onClick={() => setDialogOpen(true)}
        aria-label="New matter"
        className="md:hidden fixed bottom-6 right-6 z-30 bg-[#1a1a1a] text-white border border-[#1a1a1a] px-6 py-4 font-mono text-xs tracking-widest uppercase hover:bg-[#9a3412] hover:border-[#9a3412] shadow-lg min-h-12 min-w-12"
      >
        + New
      </button>

      <CreateMatterDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={handleCreated}
      />
    </div>
  );
}

function Hero({
  subhead,
  tab,
  onTabChange,
  onNew,
}: {
  subhead: string;
  tab: Tab;
  onTabChange: (t: Tab) => void;
  onNew: () => void;
}) {
  return (
    <div className="grid grid-cols-12 gap-8">
      <div className="col-span-12 lg:col-span-3">
        <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] space-y-3">
          <div><span className="text-[#9a3412]">01</span><span className="ml-3">Open</span></div>
          <div><span className="text-[#9a3412]">02</span><span className="ml-3">Attach</span></div>
          <div><span className="text-[#9a3412]">03</span><span className="ml-3">Track</span></div>
          <div><span className="text-[#9a3412]">04</span><span className="ml-3">Archive</span></div>
        </div>
      </div>
      <div className="col-span-12 lg:col-span-9">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
              Matters
            </h2>
            <p className="text-lg text-[#4b5563] mt-4 max-w-xl">{subhead}</p>
          </div>
          <button
            type="button"
            onClick={onNew}
            data-testid="new-matter-button"
            className="hidden md:inline-flex border border-[#1a1a1a] bg-[#1a1a1a] text-white px-6 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#9a3412] hover:border-[#9a3412] transition-colors duration-300 min-h-12"
          >
            New matter
          </button>
        </div>

        {/* Active / Archived toggle */}
        <div
          role="tablist"
          aria-label="Filter matters"
          className="mt-6 flex border border-[#d1d5db] w-fit"
        >
          <TabButton selected={tab === "active"} onClick={() => onTabChange("active")} label="Active" testId="tab-active" />
          <TabButton selected={tab === "archived"} onClick={() => onTabChange("archived")} label="Archived" testId="tab-archived" />
        </div>
      </div>
    </div>
  );
}

function TabButton({
  selected,
  onClick,
  label,
  testId,
}: {
  selected: boolean;
  onClick: () => void;
  label: string;
  testId: string;
}) {
  const cls = selected
    ? "bg-[#1a1a1a] text-white"
    : "bg-white text-[#4b5563] hover:text-[#1a1a1a]";
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      data-testid={testId}
      onClick={onClick}
      className={`px-5 py-3 font-mono text-xs tracking-widest uppercase min-h-12 transition-colors duration-200 ${cls}`}
    >
      {label}
    </button>
  );
}

function EmptyMatters({ onNew, archived }: { onNew: () => void; archived: boolean }) {
  return (
    <div className="border border-[#d1d5db] bg-white px-6 py-12 md:py-16 text-center">
      <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563] mb-3">
        {archived ? "Nothing archived" : "No matters yet"}
      </div>
      <p className="text-base md:text-lg text-[#4b5563] max-w-md mx-auto mb-6">
        {archived
          ? "Archived matters will appear here when you wind one down."
          : "Open a matter to start attaching documents and tracking work against a single client engagement."}
      </p>
      {!archived && (
        <button
          type="button"
          onClick={onNew}
          className="border border-[#1a1a1a] bg-[#1a1a1a] text-white px-6 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#9a3412] hover:border-[#9a3412] transition-colors duration-300 min-h-12"
        >
          Open the first matter
        </button>
      )}
    </div>
  );
}
