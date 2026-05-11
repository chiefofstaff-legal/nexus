import { test, expect, type Page } from "@playwright/test";

// E2E: open a matter, attach a document, remove it, archive the matter.
// Uses the Playwright route-stub pattern from upload-search-graph.spec.ts so
// the test runs deterministically without requiring the FastAPI backend to
// be live. CI will run the same test against the real backend on PR #35.

interface MatterRecord {
  id: string;
  name: string;
  client: string | null;
  notes: string | null;
  created_at: string;
  archived_at: string | null;
}

interface DocRecord {
  matter_id: string;
  document_id: string;
  added_at: string;
}

function nowIso(): string {
  return new Date().toISOString();
}

// Lightweight in-memory store stubbed onto the API routes.
function newStore() {
  const matters = new Map<string, MatterRecord>();
  const documents: DocRecord[] = [];
  return { matters, documents };
}

async function wireStubs(page: Page, store: ReturnType<typeof newStore>) {
  await page.route("**/api/matters**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    const path = url.pathname;

    // Handle membership endpoints first — most specific match wins.
    const membership = path.match(/^\/api\/matters\/([^/]+)\/documents\/([^/]+)$/);
    const list = path.match(/^\/api\/matters\/([^/]+)\/documents$/);
    const detail = path.match(/^\/api\/matters\/([^/]+)$/);

    if (membership) {
      const [, mid, did] = membership;
      if (method === "DELETE") {
        const idx = store.documents.findIndex((d) => d.matter_id === mid && d.document_id === did);
        if (idx >= 0) store.documents.splice(idx, 1);
        return route.fulfill({ status: 204, body: "" });
      }
    }

    if (list) {
      const [, mid] = list;
      if (method === "GET") {
        const docs = store.documents.filter((d) => d.matter_id === mid);
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(docs) });
      }
      if (method === "POST") {
        const body = JSON.parse(route.request().postData() || "{}");
        const rec: DocRecord = { matter_id: mid, document_id: body.document_id, added_at: nowIso() };
        store.documents.push(rec);
        return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(rec) });
      }
    }

    if (detail) {
      const [, mid] = detail;
      const m = store.matters.get(mid);
      if (method === "GET") {
        if (!m) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "not found" }) });
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(m) });
      }
      if (method === "PATCH") {
        if (!m) return route.fulfill({ status: 404, body: "" });
        const body = JSON.parse(route.request().postData() || "{}");
        Object.assign(m, body);
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(m) });
      }
      if (method === "DELETE") {
        if (!m) return route.fulfill({ status: 404, body: "" });
        m.archived_at = nowIso();
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(m) });
      }
    }

    if (path === "/api/matters") {
      if (method === "GET") {
        const archivedFilter = url.searchParams.get("archived") === "true";
        const items = Array.from(store.matters.values()).filter(
          (m) => archivedFilter === !!m.archived_at,
        );
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(items) });
      }
      if (method === "POST") {
        const body = JSON.parse(route.request().postData() || "{}");
        const id = `m_${Date.now()}`;
        const rec: MatterRecord = {
          id,
          name: body.name,
          client: body.client ?? null,
          notes: body.notes ?? null,
          created_at: nowIso(),
          archived_at: null,
        };
        store.matters.set(id, rec);
        return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(rec) });
      }
    }

    return route.fallback();
  });
}

test.describe("matter dashboard create + associate flow", () => {
  test("create matter, attach + remove document, archive", async ({ page }) => {
    const store = newStore();
    await wireStubs(page, store);

    await page.goto("/matters");
    await expect(page.getByRole("heading", { name: "Matters" })).toBeVisible();

    // 1. Open the new-matter dialog
    await page.getByTestId("new-matter-button").click();
    const matterName = `Test matter ${Date.now()}`;
    await page.getByLabel(/^Name/).fill(matterName);
    await page.getByLabel(/Client/).fill("Acme Corp");
    await page.getByTestId("create-matter-submit").click();

    // 2. The new matter should appear in the list
    await expect(page.getByTestId("matter-card-name").filter({ hasText: matterName })).toBeVisible();

    // 3. Click into the matter
    await page.getByTestId("matter-card-name").filter({ hasText: matterName }).click();
    await expect(page.getByTestId("matter-detail-name")).toHaveText(matterName);

    // 4. Add a document via the membership form
    const docId = "doc_test_xyz";
    await page.getByTestId("add-document-input").fill(docId);
    await page.getByTestId("add-document-submit").click();
    await expect(page.getByTestId("document-row").filter({ hasText: docId })).toBeVisible();

    // 5. Remove the document
    await page.getByTestId("document-remove").click();
    await expect(page.getByTestId("document-row")).toHaveCount(0);

    // 6. Archive the matter (auto-confirm the window.confirm prompt)
    page.once("dialog", (d) => d.accept());
    await page.getByTestId("archive-matter").click();

    // 7. We're back on the active list — the matter is gone
    await expect(page).toHaveURL(/\/matters$/);
    await expect(page.getByTestId("matter-card-name").filter({ hasText: matterName })).toHaveCount(0);

    // 8. Switch to archived — now it's visible
    await page.getByTestId("tab-archived").click();
    await expect(page.getByTestId("matter-card-name").filter({ hasText: matterName })).toBeVisible();
  });
});
