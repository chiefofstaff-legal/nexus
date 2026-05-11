"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api";

// Pre-load cytoscape at module level so renderGraph has no dynamic-import
// overhead after the first page load.
let _cy: typeof import("cytoscape") | null = null;
async function getCytoscape() {
  if (!_cy) _cy = (await import("cytoscape")).default;
  return _cy;
}

export interface GraphElement {
  data: Record<string, string>;
  classes?: string;
}
export interface GraphData {
  elements: Array<GraphElement>;
  total_entities?: number;
  capped?: boolean;
  shown?: number;
}

export interface ConnectedEdge {
  label: string;
  direction: "out" | "in";
}

export interface EntityInfo {
  id: string;
  name: string;
  entity_type: string;
  properties: Record<string, string>;
  source_document: string | null;
  connected: ConnectedEdge[];
  in_degree: number;
  out_degree: number;
}

/* Swiss Nihilism legal entity typing — shape carries the category, hue reinforces. */
export interface TypeStyle {
  colour: string;
  shape: "ellipse" | "round-rectangle" | "diamond" | "hexagon" | "round-tag" | "round-triangle";
  label: string;
}
export const TYPE_STYLES: Record<string, TypeStyle> = {
  person:       { colour: "#1a1a1a", shape: "ellipse",          label: "Person"       },
  organisation: { colour: "#374151", shape: "round-rectangle",  label: "Organisation" },
  case:         { colour: "#ea580c", shape: "diamond",          label: "Case"         },
  document:     { colour: "#9ca3af", shape: "round-tag",        label: "Document"     },
  event:        { colour: "#4b5563", shape: "round-triangle",   label: "Event"        },
  location:     { colour: "#6b7280", shape: "hexagon",          label: "Location"     },
  money:        { colour: "#16a34a", shape: "round-rectangle",  label: "Money"        },
  date:         { colour: "#2563eb", shape: "round-triangle",   label: "Date"         },
  statute:      { colour: "#7c3aed", shape: "diamond",          label: "Statute"      },
};

/* ---- Shared cytoscape type aliases ---- */
type CyNodeLike = { data: () => Record<string, string>; style: (k: string, v: string) => void };
type CyCollection = {
  forEach: (fn: (n: CyNodeLike) => void) => void;
  style: (k: string, v: string) => void;
  length: number;
};
type CyInstance = {
  destroy: () => void;
  nodes: (sel?: string) => CyCollection;
  edges: (sel?: string) => CyCollection;
  fit: (sel?: unknown, padding?: number) => void;
  center: () => void;
  png: (opts: Record<string, unknown>) => string;
  layout: (opts: Record<string, unknown>) => { run: () => void };
  on: (evt: string, selOrHandler: unknown, maybe?: unknown) => void;
  elements: (sel?: string) => CyCollection;
};

/* ---- Layout dispatch table ---- */
export type LayoutKey = "FORCE" | "RADIAL" | "CLUSTER";
export const LAYOUT_OPTIONS: Record<LayoutKey, Record<string, unknown>> = {
  FORCE:   { name: "cose",      animate: false, nodeRepulsion: () => 8000, idealEdgeLength: () => 80, padding: 40, maxSimulationTime: 2500 },
  RADIAL:  { name: "concentric", animate: false, padding: 40, minNodeSpacing: 40 },
  CLUSTER: { name: "concentric", animate: false, padding: 40, minNodeSpacing: 60, levelWidth: () => 2 },
};

export type EdgeMode = "NONE" | "SOME" | "ALL";
export const EDGE_NEXT: Record<EdgeMode, EdgeMode> = { NONE: "SOME", SOME: "ALL", ALL: "NONE" };

/* ---- Legend SVG glyphs ---- */
function EntityGlyph({ shape, colour }: { shape: TypeStyle["shape"]; colour: string }) {
  const size = 14;
  const half = size / 2;
  const common = { fill: colour, stroke: colour };
  const glyphMap: Record<TypeStyle["shape"], React.ReactNode> = {
    ellipse:           <circle cx={half} cy={half} r={half - 0.5} {...common} />,
    "round-rectangle": <rect x={0.5} y={2.5} width={size - 1} height={size - 5} rx={2} {...common} />,
    diamond:           <polygon points={`${half},0 ${size},${half} ${half},${size} 0,${half}`} {...common} />,
    hexagon: (
      <polygon
        points={`${half},0 ${size},${size * 0.33} ${size},${size * 0.66} ${half},${size} 0,${size * 0.66} 0,${size * 0.33}`}
        {...common}
      />
    ),
    "round-tag":      <rect x={0.5} y={3.5} width={size - 1} height={size - 7} rx={4} {...common} />,
    "round-triangle": <polygon points={`${half},0 ${size},${size} 0,${size}`} {...common} />,
  };
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      {glyphMap[shape]}
    </svg>
  );
}

/* ---- Pure helpers (all exported for unit testing) ---- */
export function formatStamp(d: Date): string {
  return d.toISOString().slice(11, 19) + "Z";
}

export function computeCoverage(totalEntities: number, totalRelationships: number): number {
  const denom = totalEntities + totalRelationships;
  if (!denom) return 0;
  return Math.round((totalEntities / denom) * 100);
}

export function matchesQuery(label: string, query: string): boolean {
  if (!query) return true;
  return label.toLowerCase().includes(query.toLowerCase());
}

export function countMatches(elements: GraphElement[], query: string): number {
  if (!query) return 0;
  let n = 0;
  for (const el of elements) {
    if (el.data.label && matchesQuery(el.data.label, query)) n += 1;
  }
  return n;
}

export function pickEdgeWeight(data: Record<string, string>): number {
  const raw = data.weight ?? data.strength ?? "1";
  const n = Number(raw);
  return Number.isFinite(n) ? n : 1;
}

export function triggerPngDownload(dataUrl: string, filename: string): void {
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export function filterNodeVisibility(cy: CyInstance, query: string): void {
  cy.nodes().forEach((n) => {
    const label = n.data().label ?? "";
    n.style("display", matchesQuery(label, query) ? "element" : "none");
  });
}

export function applyEdgeMode(cy: CyInstance, mode: EdgeMode): void {
  const all = cy.edges();
  if (mode === "ALL")  { all.style("display", "element"); return; }
  if (mode === "NONE") { all.style("display", "none");    return; }
  const weighted: Array<{ edge: CyNodeLike; w: number }> = [];
  all.forEach((e) => weighted.push({ edge: e, w: pickEdgeWeight(e.data()) }));
  weighted.sort((a, b) => b.w - a.w);
  const keepN = Math.max(1, Math.ceil(weighted.length * 0.25));
  weighted.forEach((entry, i) => {
    entry.edge.style("display", i < keepN ? "element" : "none");
  });
}

// Wrap fullscreen Promises — they reject if the element is already in/out of
// fullscreen or if user-gesture requirements aren't met.
function enterFullscreen(el: HTMLElement | null): void {
  if (!el) return;
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {});
    return;
  }
  el.requestFullscreen().catch(() => {});
}

// Static Cytoscape style sheet — extracted so renderGraph stays focused on
// mounting logic rather than style authoring.
const GRAPH_STYLES = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "font-size": "9px",
      "font-family": "ui-monospace, SFMono-Regular, Consolas, monospace",
      "text-valign": "bottom",
      "text-margin-y": 6,
      width: 24,
      height: 24,
      "background-color": "#1a1a1a",
      "border-width": 1,
      "border-color": "#d1d5db",
      color: "#525252",
    } as Record<string, unknown>,
  },
  ...Object.entries(TYPE_STYLES).map(([type, s]) => ({
    selector: `.${type}`,
    style: { "background-color": s.colour, "border-color": s.colour, shape: s.shape },
  })),
  {
    selector: "edge",
    style: {
      label: "data(label)",
      "font-size": "7px",
      "font-family": "ui-monospace, SFMono-Regular, Consolas, monospace",
      "text-rotation": "autorotate",
      "text-margin-y": -8,
      "line-color": "#d1d5db",
      "target-arrow-color": "#d1d5db",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      width: 1,
      color: "#9ca3af",
    } as Record<string, unknown>,
  },
  { selector: "node:selected", style: { "border-color": "#ea580c", "border-width": 3 } },
];

// Hoisted to module level — computed once, not on every GraphPage mount.
const ALL_TYPES_VISIBLE: Record<string, boolean> = Object.keys(TYPE_STYLES).reduce(
  (acc, key) => ({ ...acc, [key]: true }),
  {} as Record<string, boolean>,
);

/* ---- Extracted UI components (DRY) ---- */

function ToolbarButton({
  onClick,
  active,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`border px-3 py-2 transition-colors duration-200 font-mono text-[10px] tracking-widest uppercase ${
        active
          ? "border-[#ea580c] text-[#ea580c]"
          : "border-gray-300 text-[#4b5563] hover:border-[#ea580c] hover:text-[#ea580c]"
      }`}
    >
      {children}
    </button>
  );
}

function StatCard({ label, value, testId }: { label: string; value: number | string; testId?: string }) {
  return (
    <div data-testid={testId} className="col-span-6 md:col-span-3 border border-gray-300 p-6">
      <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-1">{label}</span>
      <div className="text-4xl font-bold tracking-tighter">{value}</div>
    </div>
  );
}

function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="mt-6 border border-gray-300 p-6">
      <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">{title}</span>
      <p className="text-sm text-[#4b5563] mt-2">{message}</p>
    </div>
  );
}

/* ---- useCytoscapeGraph hook (SRP: all cytoscape lifecycle extracted) ---- */
function useCytoscapeGraph(cyRef: React.RefObject<HTMLDivElement | null>) {
  const cyInstance = useRef<CyInstance | null>(null);
  // renderGenRef guards against rapid-refresh race: async renderGraph that
  // completes after a newer call started will bail out via generation check.
  const renderGenRef = useRef(0);
  // elements in state (not ref) so resultCount memo sees updates correctly.
  const [elements, setElements] = useState<GraphElement[]>([]);
  const [layoutRunning, setLayoutRunning] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [layout, setLayout] = useState<LayoutKey>("FORCE");
  const [edgeMode, setEdgeMode] = useState<EdgeMode>("ALL");
  const [labelsOn, setLabelsOn] = useState(true);

  const buildSelection = useCallback((cy: CyInstance, data: Record<string, string>): EntityInfo => {
    const nodeId = data.id;
    const connected: ConnectedEdge[] = [];
    let inDeg = 0;
    let outDeg = 0;
    cy.edges().forEach((edge) => {
      const e = edge.data();
      if (e.source === nodeId) {
        outDeg += 1;
        if (connected.length < 3) connected.push({ label: e.target_label ?? e.target, direction: "out" });
      } else if (e.target === nodeId) {
        inDeg += 1;
        if (connected.length < 3) connected.push({ label: e.source_label ?? e.source, direction: "in" });
      }
    });
    const OMIT = new Set(["id", "label", "type", "source_document"]);
    const restProps = Object.fromEntries(Object.entries(data).filter(([k]) => !OMIT.has(k)));
    return {
      id: nodeId,
      name: data.label,
      entity_type: data.type,
      properties: restProps,
      source_document: data.source_document || null,
      connected,
      in_degree: inDeg,
      out_degree: outDeg,
    };
  }, []);

  const renderGraph = useCallback(async (
    data: GraphData,
    onNodeTap: (entity: EntityInfo) => void,
    onBgTap: () => void,
  ) => {
    if (!cyRef.current || !data.elements?.length) return;
    const gen = ++renderGenRef.current;
    setElements(data.elements);
    const cytoscape = await getCytoscape();
    if (gen !== renderGenRef.current) return; // Stale — newer render started
    if (cyInstance.current) cyInstance.current.destroy();

    setLayoutRunning(true);
    const cy = cytoscape({
      container: cyRef.current,
      elements: data.elements,
      style: GRAPH_STYLES,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      layout: LAYOUT_OPTIONS.FORCE as any,
    }) as unknown as CyInstance;

    cy.on("layoutstop", () => setLayoutRunning(false));
    cy.on("tap", "node", (evt: unknown) => {
      const e = evt as { target: CyNodeLike };
      onNodeTap(buildSelection(cy, e.target.data()));
    });
    cy.on("tap", (evt: unknown) => {
      const e = evt as { target: unknown };
      if (e.target === (cy as unknown)) onBgTap();
    });
    cyInstance.current = cy;
    setLastRefresh(new Date());
  }, [cyRef, buildSelection]);

  const applyLayout = useCallback((key: LayoutKey) => {
    const cy = cyInstance.current;
    if (!cy) return;
    cy.layout(LAYOUT_OPTIONS[key]).run();
    setLayout(key);
  }, []);

  const cycleEdges = useCallback(() => {
    const cy = cyInstance.current;
    if (!cy) return;
    const next = EDGE_NEXT[edgeMode];
    applyEdgeMode(cy, next);
    setEdgeMode(next);
  }, [edgeMode]);

  const toggleLabels = useCallback(() => {
    const cy = cyInstance.current;
    if (!cy) return;
    const next = !labelsOn;
    cy.nodes().style("label", next ? "data(label)" : "");
    setLabelsOn(next);
  }, [labelsOn]);

  const resetView = useCallback(() => {
    const cy = cyInstance.current;
    if (!cy) return;
    cy.fit(undefined, 40);
    cy.center();
  }, []);

  const exportPng = useCallback(() => {
    const cy = cyInstance.current;
    if (!cy) return;
    const url = cy.png({ bg: "#ffffff", scale: 2, full: true });
    triggerPngDownload(url, `nexus-graph-${Date.now()}.png`);
  }, []);

  const applyTypeFilter = useCallback((typeKey: string, visible: boolean) => {
    const cy = cyInstance.current;
    if (!cy) return;
    cy.nodes(`.${typeKey}`).style("display", visible ? "element" : "none");
  }, []);

  const applySearch = useCallback((query: string, resultCount: number) => {
    const cy = cyInstance.current;
    if (!cy) return;
    filterNodeVisibility(cy, query);
    if (query && resultCount > 0) cy.fit(undefined, 60);
  }, []);

  return {
    elements, layoutRunning, lastRefresh, layout, edgeMode, labelsOn,
    renderGraph, applyLayout, cycleEdges, toggleLabels, resetView, exportPng,
    applyTypeFilter, applySearch,
  };
}

/* ---- Main component ---- */
export default function GraphPage() {
  const cyRef = useRef<HTMLDivElement>(null);
  const [stats, setStats] = useState<{
    total_entities?: number;
    total_relationships?: number;
    by_type?: Record<string, number>;
  }>({});
  const [selectedEntity, setSelectedEntity] = useState<EntityInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [graphCap, setGraphCap] = useState<{ capped: boolean; shown: number; total: number } | null>(null);
  const [query, setQuery] = useState("");
  const [visibleTypes, setVisibleTypes] = useState<Record<string, boolean>>(ALL_TYPES_VISIBLE);

  const {
    elements, layoutRunning, lastRefresh, layout, edgeMode, labelsOn,
    renderGraph, applyLayout, cycleEdges, toggleLabels, resetView, exportPng,
    applyTypeFilter, applySearch,
  } = useCytoscapeGraph(cyRef);

  const coverage = useMemo(
    () => computeCoverage(stats.total_entities ?? 0, stats.total_relationships ?? 0),
    [stats.total_entities, stats.total_relationships],
  );
  // elements is React state (not a ref), so this memo re-runs on graph load.
  const resultCount = useMemo(() => countMatches(elements, query), [elements, query]);

  const toggleType = (type: string) => {
    setVisibleTypes((prev) => {
      const next = { ...prev, [type]: !prev[type] };
      applyTypeFilter(type, next[type]);
      return next;
    });
  };

  const loadGraph = useCallback(async () => {
    setLoading(true);
    try {
      const [graphData, statsData] = await Promise.all([api.getGraph(), api.entityStats()]);
      setStats(statsData);
      setGraphCap(
        graphData.capped
          ? { capped: true, shown: graphData.shown ?? 0, total: graphData.total_entities ?? 0 }
          : null,
      );
      await renderGraph(graphData, setSelectedEntity, () => setSelectedEntity(null));
    } catch (e) {
      console.error("Failed to load graph:", e);
    }
    setLoading(false);
  }, [renderGraph]);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  useEffect(() => {
    applySearch(query, resultCount);
  }, [query, resultCount, applySearch]);

  const isEmpty = !loading && (!stats.total_entities || stats.total_entities === 0);
  const allHidden = !Object.values(visibleTypes).some(Boolean);

  return (
    <div className="space-y-12">
      {/* LIVE strip */}
      <div className="grid grid-cols-12 gap-4 border-t border-b border-gray-300 py-3">
        <div className="col-span-4 md:col-span-3 flex items-center gap-3">
          <span
            className={`inline-block w-2 h-2 rounded-full ${loading ? "bg-[#ea580c] animate-pulse" : "bg-[#16a34a]"}`}
            aria-hidden
          />
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">Live</span>
        </div>
        <div className="col-span-4 md:col-span-3">
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">Coverage</span>{" "}
          <span className="font-mono text-[10px] tracking-widest uppercase text-black">{coverage}%</span>
        </div>
        <div className="col-span-4 md:col-span-6 text-right">
          <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">Last Refresh</span>{" "}
          <span className="font-mono text-[10px] tracking-widest uppercase text-black">
            {lastRefresh ? formatStamp(lastRefresh) : "—"}
          </span>
        </div>
      </div>

      {/* Hero */}
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 lg:col-span-3">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] mb-3">Filter by type</div>
          <div className="font-mono text-xs tracking-widest uppercase space-y-2">
            {Object.entries(TYPE_STYLES).map(([key, s]) => {
              const visible = visibleTypes[key] !== false;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => toggleType(key)}
                  aria-pressed={visible}
                  className={`flex items-center gap-3 w-full text-left px-2 py-1 transition-opacity duration-200 ${
                    visible ? "opacity-100" : "opacity-30"
                  } hover:bg-[#fafafa]`}
                >
                  <EntityGlyph shape={s.shape} colour={s.colour} />
                  <span className={visible ? "text-[#4b5563]" : "text-[#9ca3af] line-through"}>{s.label}</span>
                </button>
              );
            })}
          </div>
          <div className="mt-4 font-mono text-[9px] tracking-wider text-[#9ca3af] px-2">
            Click a row to hide / show that entity type.
          </div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
            Entity<br />Graph
          </h2>
          <p className="text-lg text-[#4b5563] mt-4 max-w-xl">
            Knowledge graph of people, organisations, cases, and documents extracted from ingested files.
          </p>
          <button
            onClick={loadGraph}
            disabled={loading}
            className="mt-6 border border-black bg-[#1a1a1a] text-white px-8 py-3 font-mono text-xs tracking-widest uppercase hover:bg-[#ea580c] hover:border-[#ea580c] disabled:opacity-50 transition-colors duration-300"
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-12 gap-6">
        <StatCard label="Entities"      value={stats.total_entities      || 0} testId="stat-entities" />
        <StatCard label="Relationships" value={stats.total_relationships || 0} />
        {stats.by_type &&
          Object.entries(stats.by_type)
            .slice(0, 2)
            .map(([type, count]) => <StatCard key={type} label={`${type}s`} value={count} />)}
      </div>

      {/* Cap notice */}
      {graphCap?.capped && (
        <div className="border border-[#b08d57] bg-[#fffbf0] px-6 py-3 font-mono text-xs tracking-wider text-[#92400e]">
          Showing the {graphCap.shown} most-connected entities of {graphCap.total} total.
          Use the type filters to focus on a subset, or click a node to explore its subgraph.
        </div>
      )}

      {/* Search */}
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12">
          <label className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563] block mb-2">Search</label>
          <div className="flex items-center gap-3 border border-gray-300 px-4 py-3 bg-white">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter nodes by label..."
              className="flex-1 outline-none font-mono text-sm bg-transparent"
            />
            {query && (
              <>
                <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
                  {resultCount} found
                </span>
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  aria-label="Clear search"
                  className="font-mono text-xs tracking-widest uppercase text-[#4b5563] hover:text-[#ea580c] transition-colors"
                >
                  X
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Graph + Sidebar */}
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-9 relative">
          <div ref={cyRef} data-testid="cytoscape-container" className="border border-gray-300 bg-white w-full" style={{ height: 700 }} />
          {layoutRunning && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/70 pointer-events-none">
              <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563] animate-pulse">
                Computing layout…
              </span>
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {(Object.keys(LAYOUT_OPTIONS) as LayoutKey[]).map((key) => (
              <ToolbarButton key={key} onClick={() => applyLayout(key)} active={layout === key}>
                {key}
              </ToolbarButton>
            ))}
            <ToolbarButton onClick={resetView}>Reset</ToolbarButton>
            <ToolbarButton onClick={toggleLabels} active={labelsOn}>Labels</ToolbarButton>
            <ToolbarButton onClick={cycleEdges}>Edges: {edgeMode}</ToolbarButton>
            <ToolbarButton onClick={() => enterFullscreen(cyRef.current)}>Fullscreen</ToolbarButton>
            <ToolbarButton onClick={exportPng}>Export PNG</ToolbarButton>
          </div>
          {isEmpty && (
            <EmptyState
              title="Graph empty"
              message="No entities have been ingested yet. Upload documents on the Documents page and the graph will populate automatically."
            />
          )}
          {!isEmpty && allHidden && (
            <EmptyState
              title="All types hidden"
              message="Every entity type is currently filtered out. Re-enable at least one type from the legend to visualise the graph."
            />
          )}
        </div>

        <div className="col-span-12 lg:col-span-3">
          {selectedEntity ? (
            <div className="border border-[#ea580c] p-6">
              <div className="flex items-center gap-2 mb-3">
                {TYPE_STYLES[selectedEntity.entity_type] ? (
                  <EntityGlyph
                    shape={TYPE_STYLES[selectedEntity.entity_type].shape}
                    colour={TYPE_STYLES[selectedEntity.entity_type].colour}
                  />
                ) : (
                  <span className="w-3 h-3 inline-block" style={{ backgroundColor: "#6b7280" }} />
                )}
                <span className="font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
                  {selectedEntity.entity_type}
                </span>
              </div>
              <h3 className="text-xl font-bold tracking-tight">{selectedEntity.name}</h3>
              {selectedEntity.source_document && (
                <p className="font-mono text-[10px] tracking-wider text-[#4b5563] mt-2">
                  Source: {selectedEntity.source_document}
                </p>
              )}
              <div className="mt-4 font-mono text-[10px] tracking-widest uppercase text-[#4b5563]">
                In {selectedEntity.in_degree} / Out {selectedEntity.out_degree}
              </div>
              {selectedEntity.connected.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {selectedEntity.connected.map((c, i) => (
                    <li key={i} className="font-mono text-[10px] tracking-wider text-black">
                      <span className="text-[#4b5563]">{c.direction === "out" ? "→" : "←"}</span> {c.label}
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-4 space-y-1.5">
                {Object.entries(selectedEntity.properties)
                  .filter(([k]) => !["id", "label", "type"].includes(k))
                  .map(([key, value]) => (
                    <div key={key} className="font-mono text-[10px] tracking-wider">
                      <span className="text-[#4b5563]">{key}</span>{" "}
                      <span className="text-black">{value}</span>
                    </div>
                  ))}
              </div>
            </div>
          ) : (
            <div className="border border-gray-300 p-6">
              <span className="font-mono text-xs tracking-widest uppercase text-[#4b5563]">Select a node</span>
              <p className="text-sm text-[#4b5563] mt-2">
                Click any entity in the graph to inspect its properties and connections.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
