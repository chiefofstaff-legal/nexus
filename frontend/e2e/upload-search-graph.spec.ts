import { test, expect, type Page } from "@playwright/test";

// Minimal fixture shapes that match the contracts in src/lib/api.ts
const FIXTURES = {
  timeSummary: { total_hours: 1.5, total_value_chf: 675, entry_count: 2 },
  timeEntries: { entries: [] },
  tasks: { tasks: [] },
  documents: { documents: [] },
  idrsRecent: { entries: [] },
  graph: {
    elements: [
      { data: { id: "n1", label: "Helvetica Corp", type: "ORG" }, group: "nodes" },
    ],
    total_entities: 1,
  },
  entityStats: { total_entities: 1, total_relationships: 0, by_type: {} },
  searchResults: {
    query: "confidentiality",
    results: [
      {
        text: "The parties agree to maintain strict confidentiality.",
        relevance: 0.88,
        metadata: { doc_id: "d1", filename: "nda.pdf", document_type: "nda" },
      },
    ],
    total: 1,
  },
};

function stub(page: Page, pattern: string, body: unknown): Promise<void> {
  return page.route(pattern, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(body) })
  );
}

test.describe("upload-search-graph flow", () => {
  test("dashboard renders KPI grid with fixture values", async ({ page }) => {
    await Promise.all([
      stub(page, "**/api/time/summary**", FIXTURES.timeSummary),
      stub(page, "**/api/time/entries**", FIXTURES.timeEntries),
      stub(page, "**/api/tasks/list**", FIXTURES.tasks),
      stub(page, "**/api/documents/list**", FIXTURES.documents),
      stub(page, "**/api/idrs/recent**", FIXTURES.idrsRecent),
    ]);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /You are losing billable hours/ })
    ).toBeVisible();
    await expect(page.getByText("Quick actions", { exact: true }).first()).toBeVisible();
    // Verifies total_value_chf=675 from fixture was consumed and rendered in the KPI card
    await expect(page.getByText(/CHF 675/)).toBeVisible();
  });

  test("graph page renders Cytoscape container and entity stats", async ({ page }) => {
    await Promise.all([
      stub(page, "**/api/entities/graph**", FIXTURES.graph),
      stub(page, "**/api/entities/stats**", FIXTURES.entityStats),
    ]);

    await page.goto("/graph");
    await expect(page.getByRole("heading", { name: /Entity Graph/i })).toBeVisible();
    // data-testid added to the Cytoscape container div in graph/page.tsx
    await expect(page.getByTestId("cytoscape-container")).toBeVisible();
    // Verifies total_entities=1 from fixture was consumed and rendered in the Entities StatCard
    await expect(page.getByTestId("stat-entities")).toContainText("1");
  });

  test("search accepts query and renders result text", async ({ page }) => {
    await Promise.all([
      stub(page, "**/api/documents/search**", FIXTURES.searchResults),
      stub(page, "**/api/documents/search-stats**", {
        total_chunks: 42,
        collection_name: "nexus_documents",
      }),
    ]);

    await page.goto("/search");
    const input = page.getByPlaceholder(
      "e.g. confidentiality obligations under Swiss law"
    );
    await expect(input).toBeVisible();

    await input.fill("confidentiality");
    await page.getByRole("button", { name: "Search" }).click();

    await expect(
      page.getByText("The parties agree to maintain strict confidentiality.")
    ).toBeVisible();
  });
});
