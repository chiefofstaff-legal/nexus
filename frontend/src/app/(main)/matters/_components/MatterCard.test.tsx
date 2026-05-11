import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MatterCard } from "./MatterCard";
import type { Matter } from "../_lib/matters-client";

// Plain Vitest assertions only — the existing project doesn't pull in
// @testing-library/jest-dom, so toHaveTextContent / toBeInTheDocument
// are unavailable. Asserting on textContent / queryByText null-checks
// covers the same behaviour with the matchers that ship with vitest.

const baseMatter: Matter = {
  id: "m_001",
  name: "Helvetica Corp v. Schmidt",
  client: "Helvetica Corp",
  notes: null,
  created_at: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
  archived_at: null,
};

describe("MatterCard", () => {
  it("renders the name, client, and document count", () => {
    render(<MatterCard matter={baseMatter} documentCount={3} />);
    expect(screen.getByTestId("matter-card-name").textContent).toBe(
      "Helvetica Corp v. Schmidt",
    );
    expect(screen.getByTestId("matter-card-client").textContent).toBe(
      "Helvetica Corp",
    );
    expect(screen.getByTestId("matter-card-doc-count").textContent).toBe("3");
  });

  it("shows an em-dash placeholder when client is null", () => {
    render(<MatterCard matter={{ ...baseMatter, client: null }} documentCount={0} />);
    expect(screen.getByTestId("matter-card-client").textContent).toBe("—");
  });

  it("uses the Archived label when archived_at is set", () => {
    const archived: Matter = {
      ...baseMatter,
      archived_at: new Date().toISOString(),
    };
    render(<MatterCard matter={archived} documentCount={1} />);
    expect(screen.queryByText("Archived")).not.toBeNull();
    expect(screen.queryByText("Active")).toBeNull();
  });

  it("falls back to em-dash when documentCount is undefined", () => {
    render(<MatterCard matter={baseMatter} />);
    expect(screen.getByTestId("matter-card-doc-count").textContent).toBe("—");
  });
});
