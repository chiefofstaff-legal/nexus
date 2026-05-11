import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// H243 falsifier: search page must render and wire SearchModeToggle.
// These tests fail if the toggle is removed from page.tsx or onChange is disconnected.

vi.mock("@/lib/api", () => ({
  api: {
    searchStats: vi.fn().mockResolvedValue({ total_chunks: 0 }),
    searchDocuments: vi.fn().mockResolvedValue({ query: "test", results: [], total: 0 }),
  },
}));

// Dynamic import to avoid top-level async in describe
let SearchPage: typeof import("../page").default;

beforeEach(async () => {
  const mod = await import("../page");
  SearchPage = mod.default;
});

describe("SearchPage — SearchModeToggle integration (H243)", () => {
  it("renders keyword mode button", async () => {
    render(<SearchPage />);
    expect(screen.getByTestId("search-mode-keyword")).not.toBeNull();
  });

  it("renders semantic mode button", async () => {
    render(<SearchPage />);
    expect(screen.getByTestId("search-mode-semantic")).not.toBeNull();
  });

  it("renders hybrid mode button", async () => {
    render(<SearchPage />);
    expect(screen.getByTestId("search-mode-hybrid")).not.toBeNull();
  });

  it("renders EN/DE language selector", async () => {
    render(<SearchPage />);
    const select = screen.getByTestId("search-lang-select") as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toContain("en");
    expect(values).toContain("de");
  });

  it("switching mode updates the active button", async () => {
    render(<SearchPage />);
    fireEvent.click(screen.getByTestId("search-mode-keyword"));
    expect(screen.getByTestId("search-mode-keyword").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("search-mode-semantic").getAttribute("aria-pressed")).toBe("false");
  });
});
