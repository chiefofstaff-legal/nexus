"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  mattersClient,
  summaryClient,
  type Matter,
  type MatterDocument,
  type SummarySnapshot,
  relativeTime,
} from "../_lib/matters-client";
import { DocumentMembershipList } from "../_components/DocumentMembershipList";

// Detail page. PATCH-on-blur for editable fields keeps the API surface tiny;
// archive flows back to the list to mirror destructive-action conventions.
export default function MatterDetailPage() {
  const params = useParams<{ id: string }>();
  const matterId = decodeURIComponent(params?.id ?? "");
  const router = useRouter();

  const [matter, setMatter] = useState<Matter | null>(null);
  const [docs, setDocs] = useState<MatterDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  const [notes, setNotes] = useState("");

  const loadMatter = useCallback(async () => {
    if (!matterId) return;
    setLoading(true);
    setError(null);
    try {
      const [m, d] = await Promise.all([
        mattersClient.getMatter(matterId),
        mattersClient.listMatterDocuments(matterId),
      ]);
      setMatter(m);
      setDocs(d);
      setName(m.name);
      setClient(m.client ?? "");
      setNotes(m.notes ?? "");
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, [matterId]);

  useEffect(() => {
    loadMatter();
  }, [loadMatter]);

  const refreshDocs = useCallback(async () => {
    if (!matterId) return;
    try {
      const d = await mattersClient.listMatterDocuments(matterId);
      setDocs(d);
    } catch (e) {
      setError(String(e));
    }
  }, [matterId]);

  const persist = async (patch: Partial<Pick<Matter, "name" | "client" | "notes">>) => {
    if (!matter) return;
    try {
      const updated = await mattersClient.updateMatter(matter.id, patch);
      setMatter(updated);
    } catch (e) {
      setError(String(e));
    }
  };

  const handleArchive = async () => {
    if (!matter) return;
    if (!confirm("Archive this matter? It will be hidden from the active list.")) return;
    try {
      await mattersClient.archiveMatter(matter.id);
      router.push("/matters");
    } catch (e) {
      setError(String(e));
    }
  };

  if (loading && !matter) {
    return (
      <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
        Loading matter…
      </div>
    );
  }

  if (!matter) {
    return (
      <div className="border border-[#dc2626] text-[#dc2626] px-6 py-4 font-mono text-sm">
        {error || "Matter not found"}
      </div>
    );
  }

  const archived = !!matter.archived_at;

  return (
    <div className="space-y-10">
      <DetailHeader
        matter={matter}
        archived={archived}
        onArchive={handleArchive}
      />

      {error && (
        <div
          role="alert"
          className="border border-[#dc2626] text-[#dc2626] px-6 py-3 font-mono text-xs"
        >
          {error}
        </div>
      )}

      <section
        aria-labelledby="details-heading"
        className="border border-[#d1d5db] bg-white"
      >
        <div className="border-b border-[#d1d5db] bg-[#fafafa] px-5 py-4">
          <h3
            id="details-heading"
            className="font-mono text-xs tracking-widest uppercase text-[#4b5563]"
          >
            Details
          </h3>
        </div>
        <div className="p-5 md:p-6 grid grid-cols-1 md:grid-cols-2 gap-5">
          <EditField
            id="detail-name"
            label="Name"
            value={name}
            onChange={setName}
            onBlur={() => name !== matter.name && persist({ name })}
            disabled={archived}
          />
          <EditField
            id="detail-client"
            label="Client"
            value={client}
            onChange={setClient}
            onBlur={() => client !== (matter.client ?? "") && persist({ client })}
            disabled={archived}
          />
          <div className="md:col-span-2">
            <label
              htmlFor="detail-notes"
              className="block font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2"
            >
              Notes
            </label>
            <textarea
              id="detail-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => notes !== (matter.notes ?? "") && persist({ notes })}
              disabled={archived}
              rows={5}
              placeholder="Internal notes for the matter team"
              className="w-full border border-[#d1d5db] bg-white px-3 py-3 text-base md:text-sm focus:outline-none focus:border-[#9a3412] disabled:bg-[#fafafa] disabled:text-[#9ca3af]"
            />
          </div>
        </div>
      </section>

      <DocumentMembershipList
        matterId={matter.id}
        documents={docs}
        onChanged={refreshDocs}
      />

      <SummarySection matterId={matter.id} />
    </div>
  );
}

function DetailHeader({
  matter,
  archived,
  onArchive,
}: {
  matter: Matter;
  archived: boolean;
  onArchive: () => void;
}) {
  return (
    <div className="grid grid-cols-12 gap-8">
      <div className="col-span-12 lg:col-span-3">
        <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-3">
          Created
        </div>
        <div className="font-mono text-xs text-[#1a1a1a]">
          {relativeTime(matter.created_at)}
        </div>
        {archived && matter.archived_at && (
          <>
            <div className="font-mono text-[10px] tracking-widest uppercase text-[#9a3412] mt-5 mb-3">
              Archived
            </div>
            <div className="font-mono text-xs text-[#9a3412]">
              {relativeTime(matter.archived_at)}
            </div>
          </>
        )}
      </div>
      <div className="col-span-12 lg:col-span-9">
        {archived && (
          <div
            role="status"
            data-testid="archived-banner"
            className="mb-4 border border-[#9a3412] bg-[#fef2f2] text-[#9a3412] px-4 py-2 font-mono text-[10px] tracking-widest uppercase"
          >
            Archived — read-only
          </div>
        )}
        <h2
          data-testid="matter-detail-name"
          className="text-4xl md:text-6xl font-bold tracking-tighter leading-[0.9] break-words"
        >
          {matter.name}
        </h2>
        {matter.client && (
          <p className="font-mono text-sm tracking-wider text-[#4b5563] mt-3">
            {matter.client}
          </p>
        )}
        {!archived && (
          <button
            type="button"
            onClick={onArchive}
            data-testid="archive-matter"
            className="mt-6 border border-[#d1d5db] px-5 py-3 font-mono text-xs tracking-widest uppercase text-[#4b5563] hover:border-[#9a3412] hover:text-[#9a3412] transition-colors duration-200 min-h-12"
          >
            Archive matter
          </button>
        )}
      </div>
    </div>
  );
}

function EditField({
  id,
  label,
  value,
  onChange,
  onBlur,
  disabled,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  onBlur: () => void;
  disabled?: boolean;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="block font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2"
      >
        {label}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        disabled={disabled}
        className="w-full border border-[#d1d5db] bg-white px-3 py-3 text-base md:text-sm min-h-12 focus:outline-none focus:border-[#9a3412] disabled:bg-[#fafafa] disabled:text-[#9ca3af]"
      />
    </div>
  );
}

function SummarySection({ matterId }: { matterId: string }) {
  const [snapshot, setSnapshot] = useState<SummarySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [versions, setVersions] = useState<SummarySnapshot[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await summaryClient.getSummary(matterId);
      setSnapshot(s);
      setSelectedVersion(s.version_id);
      // Fetch all versions by iterating — backend has no list endpoint, so we
      // re-fetch the latest version_id count and collect each.
      const collected: SummarySnapshot[] = [s];
      for (let v = s.version_id - 1; v >= 1; v--) {
        try {
          const prev = await summaryClient.getSummaryVersion(matterId, v);
          collected.push(prev);
        } catch {
          break;
        }
      }
      setVersions(collected.reverse());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("404") || msg.toLowerCase().includes("not found")) {
        setError("none");
      } else {
        setError(msg);
      }
    }
    setLoading(false);
  }, [matterId]);

  useEffect(() => { load(); }, [load]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    setError(null);
    try {
      const s = await summaryClient.regenerateSummary(matterId);
      setSnapshot(s);
      setSelectedVersion(s.version_id);
      setVersions((prev) => [...prev, s]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setRegenerating(false);
  };

  const handleVersionChange = async (versionId: number) => {
    setSelectedVersion(versionId);
    const cached = versions.find((v) => v.version_id === versionId);
    if (cached) { setSnapshot(cached); return; }
    try {
      const s = await summaryClient.getSummaryVersion(matterId, versionId);
      setSnapshot(s);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section aria-labelledby="summary-heading" className="border border-[#d1d5db] bg-white">
      <div className="border-b border-[#d1d5db] bg-[#fafafa] px-5 py-4 flex items-center justify-between">
        <h3
          id="summary-heading"
          className="font-mono text-xs tracking-widest uppercase text-[#4b5563]"
        >
          Summary
        </h3>
        <div className="flex items-center gap-3">
          {versions.length > 1 && (
            <select
              value={selectedVersion ?? ""}
              onChange={(e) => handleVersionChange(Number(e.target.value))}
              className="border border-[#d1d5db] bg-white px-2 py-1 font-mono text-[10px] tracking-widest uppercase text-[#4b5563] focus:outline-none focus:border-[#9a3412]"
              aria-label="Select summary version"
            >
              {[...versions].reverse().map((v) => (
                <option key={v.version_id} value={v.version_id}>
                  v{v.version_id} — {relativeTime(v.created_at)}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            onClick={handleRegenerate}
            disabled={regenerating || loading}
            className="border border-[#d1d5db] px-4 py-2 font-mono text-[10px] tracking-widest uppercase text-[#4b5563] hover:border-[#9a3412] hover:text-[#9a3412] transition-colors duration-200 disabled:opacity-40"
          >
            {regenerating ? "Generating…" : "Regenerate"}
          </button>
        </div>
      </div>
      <div className="p-5 md:p-6">
        {loading ? (
          <div className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">
            Loading summary…
          </div>
        ) : error === "none" ? (
          <div className="font-mono text-sm text-[#4b5563]">
            No summary yet — click Regenerate to generate one.
          </div>
        ) : error ? (
          <div className="font-mono text-sm text-[#dc2626]">{error}</div>
        ) : snapshot ? (
          <div className="space-y-4">
            <div className="text-sm text-[#1a1a1a] leading-relaxed whitespace-pre-wrap">
              {snapshot.content}
            </div>
            {snapshot.source_citations.length > 0 && (
              <div>
                <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-2">
                  Sources
                </div>
                <ul className="space-y-1">
                  {snapshot.source_citations.map((cite, i) => (
                    <li key={i} className="font-mono text-xs text-[#6b7280]">
                      {cite}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </section>
  );
}
