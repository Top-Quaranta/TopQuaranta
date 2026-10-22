// @vitest-environment jsdom
/**
 * The 07:00 mail links each pending artist as `/staff/pendents?q=Nom`
 * (analytics/management/commands/enviar_informe_youtube.py). The page
 * must open already filtered on that name: before 2026-10-22 it always
 * started with an empty search and the link landed on page 1 of the
 * whole queue.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../lib/api", () => ({
  api: { get: vi.fn(() => new Promise(() => {})), post: vi.fn() },
}));

import { api } from "../../lib/api";
import PendentsPage from "./PendentsPage";

afterEach(cleanup);

describe("PendentsPage search seeded from the URL", () => {
  it("opens filtered on ?q= so the mail link lands on the row", async () => {
    render(
      <MemoryRouter initialEntries={["/staff/pendents?q=Gioba%20Fellini"]}>
        <PendentsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    const url = api.get.mock.calls[0][0];
    expect(new URLSearchParams(url.split("?")[1]).get("q")).toBe(
      "Gioba Fellini",
    );
  });
});
