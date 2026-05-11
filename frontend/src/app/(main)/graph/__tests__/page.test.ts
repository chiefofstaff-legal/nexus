/**
 * Unit tests for graph page pure helper functions.
 *
 * Mutation-killing strategy: each test verifies a SPECIFIC output value so
 * that mutating the implementation (e.g. changing ">" to ">=", swapping
 * Math.round with Math.floor, dropping "+Z" suffix) causes at least one
 * assertion to fail.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import {
  formatStamp,
  computeCoverage,
  matchesQuery,
  countMatches,
  pickEdgeWeight,
  triggerPngDownload,
  filterNodeVisibility,
  applyEdgeMode,
  type GraphElement,
} from "../page";

// ---- Minimal CyInstance mock factory ----
function makeMockCy(nodeLabels: string[], edgeWeights: number[] = []) {
  const nodeStyles: Record<string, Record<string, string>> = {};
  const edgeStyles: Record<string, Record<string, string>> = {};
  let nodeIdx = 0;
  let edgeIdx = 0;

  const mockNodes = nodeLabels.map((label, i) => ({
    data: () => ({ id: `n${i}`, label }),
    style: (k: string, v: string) => {
      nodeStyles[`n${i}`] = { ...nodeStyles[`n${i}`], [k]: v };
    },
  }));

  const mockEdges = edgeWeights.map((w, i) => ({
    data: () => ({ id: `e${i}`, weight: String(w), source: `n0`, target: `n${i + 1}` }),
    style: (k: string, v: string) => {
      edgeStyles[`e${i}`] = { ...edgeStyles[`e${i}`], [k]: v };
    },
  }));

  return {
    cy: {
      nodes: () => ({
        forEach: (fn: (n: typeof mockNodes[0]) => void) => mockNodes.forEach(fn),
        style: (k: string, v: string) => mockNodes.forEach((n) => n.style(k, v)),
        length: mockNodes.length,
      }),
      edges: () => ({
        forEach: (fn: (e: typeof mockEdges[0]) => void) => mockEdges.forEach(fn),
        style: (k: string, v: string) => mockEdges.forEach((e) => e.style(k, v)),
        length: mockEdges.length,
      }),
    },
    nodeStyles,
    edgeStyles,
  };
}

// ============================================================
// formatStamp
// ============================================================
describe("formatStamp", () => {
  it("returns HH:MM:SSZ slice from ISO string", () => {
    const d = new Date("2026-04-22T14:30:00.000Z");
    expect(formatStamp(d)).toBe("14:30:00Z");
  });

  it("zero-pads single-digit hours and minutes", () => {
    const d = new Date("2026-04-22T03:05:09.000Z");
    expect(formatStamp(d)).toBe("03:05:09Z");
  });

  it("always ends with Z suffix", () => {
    const d = new Date("2026-01-01T00:00:00.000Z");
    expect(formatStamp(d)).toMatch(/Z$/);
  });
});

// ============================================================
// computeCoverage
// ============================================================
describe("computeCoverage", () => {
  it("returns 0 when both args are 0 (avoids division by zero)", () => {
    expect(computeCoverage(0, 0)).toBe(0);
  });

  it("returns 50 when entities equal relationships", () => {
    expect(computeCoverage(10, 10)).toBe(50);
  });

  it("returns 100 when relationships are 0", () => {
    expect(computeCoverage(5, 0)).toBe(100);
  });

  it("rounds to nearest integer — 2/(2+3)=40%, not 39 or 41", () => {
    expect(computeCoverage(2, 3)).toBe(40);
  });

  it("rounds up correctly for 2/3 ≈ 67%", () => {
    expect(computeCoverage(2, 1)).toBe(67);
  });
});

// ============================================================
// matchesQuery
// ============================================================
describe("matchesQuery", () => {
  it("returns true for empty query (show-all guard)", () => {
    expect(matchesQuery("anything", "")).toBe(true);
  });

  it("returns true for case-insensitive substring match", () => {
    expect(matchesQuery("Peter Müller", "peter")).toBe(true);
  });

  it("returns false when query not in label", () => {
    expect(matchesQuery("Peter Müller", "schneider")).toBe(false);
  });

  it("matches mid-string substring", () => {
    expect(matchesQuery("Hauser Employment Contract", "employ")).toBe(true);
  });
});

// ============================================================
// countMatches
// ============================================================
describe("countMatches", () => {
  it("returns 0 for empty query (all hidden — caller decides whether to show)", () => {
    const els: GraphElement[] = [{ data: { label: "Alice" } }, { data: { label: "Bob" } }];
    expect(countMatches(els, "")).toBe(0);
  });

  it("returns 0 for empty elements array", () => {
    expect(countMatches([], "alice")).toBe(0);
  });

  it("counts exact matches correctly", () => {
    const els: GraphElement[] = [
      { data: { label: "Alice Smith" } },
      { data: { label: "Bob Jones" } },
      { data: { label: "alice court" } },
    ];
    expect(countMatches(els, "alice")).toBe(2);
  });

  it("skips elements with no label field", () => {
    const els: GraphElement[] = [{ data: {} }, { data: { label: "Alice" } }];
    expect(countMatches(els, "alice")).toBe(1);
  });
});

// ============================================================
// pickEdgeWeight
// ============================================================
describe("pickEdgeWeight", () => {
  it("reads weight field when present", () => {
    expect(pickEdgeWeight({ weight: "5" })).toBe(5);
  });

  it("falls back to strength field when weight absent", () => {
    expect(pickEdgeWeight({ strength: "3" })).toBe(3);
  });

  it("returns 1 when neither weight nor strength present", () => {
    expect(pickEdgeWeight({})).toBe(1);
  });

  it("returns 1 for NaN input (non-numeric string)", () => {
    expect(pickEdgeWeight({ weight: "heavy" })).toBe(1);
  });

  it("returns 1 for Infinity (not finite)", () => {
    expect(pickEdgeWeight({ weight: "Infinity" })).toBe(1);
  });

  it("handles fractional weights", () => {
    expect(pickEdgeWeight({ weight: "2.5" })).toBe(2.5);
  });
});

// ============================================================
// triggerPngDownload
// ============================================================
describe("triggerPngDownload", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sets href and download on a created anchor, clicks it, then removes it", () => {
    const mockAnchor = { href: "", download: "", click: vi.fn() };
    const createElement = vi.spyOn(document, "createElement").mockReturnValue(
      mockAnchor as unknown as HTMLElement,
    );
    const appendChild = vi.spyOn(document.body, "appendChild").mockImplementation(
      () => mockAnchor as unknown as Node,
    );
    const removeChild = vi.spyOn(document.body, "removeChild").mockImplementation(
      () => mockAnchor as unknown as Node,
    );

    triggerPngDownload("data:image/png;base64,TEST", "nexus-graph-123.png");

    expect(createElement).toHaveBeenCalledWith("a");
    expect(mockAnchor.href).toBe("data:image/png;base64,TEST");
    expect(mockAnchor.download).toBe("nexus-graph-123.png");
    expect(mockAnchor.click).toHaveBeenCalledOnce();
    expect(appendChild).toHaveBeenCalledWith(mockAnchor);
    expect(removeChild).toHaveBeenCalledWith(mockAnchor);
  });

  it("uses the exact filename passed — does not alter it", () => {
    const mockAnchor = { href: "", download: "", click: vi.fn() };
    vi.spyOn(document, "createElement").mockReturnValue(mockAnchor as unknown as HTMLElement);
    vi.spyOn(document.body, "appendChild").mockImplementation(() => mockAnchor as unknown as Node);
    vi.spyOn(document.body, "removeChild").mockImplementation(() => mockAnchor as unknown as Node);

    triggerPngDownload("data:image/png;base64,X", "custom-export.png");

    expect(mockAnchor.download).toBe("custom-export.png");
  });
});

// ============================================================
// filterNodeVisibility
// ============================================================
describe("filterNodeVisibility", () => {
  it("hides non-matching nodes", () => {
    const { cy, nodeStyles } = makeMockCy(["Alice", "Bob"]);
    filterNodeVisibility(cy as never, "alice");
    expect(nodeStyles["n0"].display).toBe("element");
    expect(nodeStyles["n1"].display).toBe("none");
  });

  it("shows ALL nodes for empty query (matchesQuery returns true)", () => {
    const { cy, nodeStyles } = makeMockCy(["Alice", "Bob"]);
    filterNodeVisibility(cy as never, "");
    expect(nodeStyles["n0"].display).toBe("element");
    expect(nodeStyles["n1"].display).toBe("element");
  });

  it("is case-insensitive", () => {
    const { cy, nodeStyles } = makeMockCy(["ALICE"]);
    filterNodeVisibility(cy as never, "alice");
    expect(nodeStyles["n0"].display).toBe("element");
  });
});

// ============================================================
// applyEdgeMode
// ============================================================
describe("applyEdgeMode", () => {
  it("ALL: shows every edge", () => {
    const { cy, edgeStyles } = makeMockCy(["A", "B", "C"], [1, 2]);
    applyEdgeMode(cy as never, "ALL");
    expect(edgeStyles["e0"].display).toBe("element");
    expect(edgeStyles["e1"].display).toBe("element");
  });

  it("NONE: hides every edge", () => {
    const { cy, edgeStyles } = makeMockCy(["A", "B", "C"], [1, 2]);
    applyEdgeMode(cy as never, "NONE");
    expect(edgeStyles["e0"].display).toBe("none");
    expect(edgeStyles["e1"].display).toBe("none");
  });

  it("SOME: keeps top 25% by weight (at least 1), hides the rest", () => {
    // 4 edges with weights [1, 10, 5, 2]; top 25% = 1 edge = the one with weight 10
    const { cy, edgeStyles } = makeMockCy(["A", "B", "C", "D", "E"], [1, 10, 5, 2]);
    applyEdgeMode(cy as never, "SOME");
    // e1 has weight 10 — should be kept
    expect(edgeStyles["e1"].display).toBe("element");
    // e0 has weight 1 — should be hidden
    expect(edgeStyles["e0"].display).toBe("none");
  });

  it("SOME: always keeps at least 1 edge even with single-edge graphs", () => {
    const { cy, edgeStyles } = makeMockCy(["A", "B"], [5]);
    applyEdgeMode(cy as never, "SOME");
    expect(edgeStyles["e0"].display).toBe("element");
  });

  it("SOME: boundary — ceil(4 * 0.25) = 1 edge shown; indices 1, 2, 3 are hidden", () => {
    // 4 edges, weights [10, 5, 3, 1]. After sort descending: e0(10), e1(5), e2(3), e3(1).
    // keepN = ceil(4 * 0.25) = 1. Only i=0 passes `i < 1`. Mutating `<` to `<=`
    // would show i=0 AND i=1, causing e1 to flip to "element" — caught below.
    const { cy, edgeStyles } = makeMockCy(["A", "B", "C", "D", "E"], [10, 5, 3, 1]);
    applyEdgeMode(cy as never, "SOME");
    expect(edgeStyles["e0"].display).toBe("element"); // weight 10 — top 25%
    expect(edgeStyles["e1"].display).toBe("none");    // weight 5  — outside 25%
    expect(edgeStyles["e2"].display).toBe("none");    // weight 3  — outside 25%
    expect(edgeStyles["e3"].display).toBe("none");    // weight 1  — outside 25%
  });
});
