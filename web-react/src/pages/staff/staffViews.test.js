/**
 * Guards for the single staff-views registry (staffViews.jsx).
 *
 * The registry is the one source of truth for both the sidebar
 * (StaffLayout) and the panell tiles (StaffDashboardPage). These tests
 * lock down: (1) every entry points at a route actually declared under
 * /staff/* in App.jsx; (2) both surfaces derive from it; (3) no
 * previously-hardcoded route is silently dropped; (4) Instagram + Spotify
 * (the two that used to be missing) are present in both surfaces.
 */
import { readFileSync } from "node:fs";
import { describe, it, expect } from "vitest";

import { STAFF_GROUPS, STAFF_VIEWS } from "./staffViews";

const APP = readFileSync(new URL("../../App.jsx", import.meta.url), "utf8");

const sidebarItems = STAFF_GROUPS.flatMap((g) =>
  g.items.filter((it) => it.inSidebar !== false),
);
const panellItems = STAFF_GROUPS.flatMap((g) =>
  g.items.filter((it) => it.inPanell !== false),
);

describe("STAFF_VIEWS registry", () => {
  it("every entry has a /staff path and a label, paths unique", () => {
    const seen = new Set();
    for (const it of STAFF_VIEWS) {
      expect(it.to.startsWith("/staff")).toBe(true);
      expect(typeof it.label).toBe("string");
      expect(it.label.length).toBeGreaterThan(0);
      expect(seen.has(it.to)).toBe(false);
      seen.add(it.to);
    }
  });

  it("every entry resolves to a <Route> declared under /staff/* in App.jsx", () => {
    for (const it of STAFF_VIEWS) {
      const rel = it.to.replace(/^\/staff/, "") || "/";
      expect(APP.includes(`path="${rel}"`)).toBe(true);
    }
  });

  it("both the sidebar and the panell derive non-empty lists", () => {
    expect(sidebarItems.length).toBeGreaterThan(0);
    expect(panellItems.length).toBeGreaterThan(0);
    // The self-link /staff is sidebar-only.
    expect(sidebarItems.some((it) => it.to === "/staff")).toBe(true);
    expect(panellItems.some((it) => it.to === "/staff")).toBe(false);
  });

  it("keeps every previously-hardcoded route (no loss in the merge)", () => {
    const must = [
      "/staff",
      "/staff/estat",
      "/staff/analytics",
      "/staff/pendents",
      "/staff/propostes",
      "/staff/solicituds",
      "/staff/sollicituds-revisio",
      "/staff/feedback",
      "/staff/artistes",
      "/staff/artistes/sense-instagram",
      "/staff/cancons",
      "/staff/albums",
      "/staff/top",
      "/staff/publicacions",
      "/staff/usuaris",
      "/staff/social",
      "/staff/social/publicacions",
      "/staff/social/mastodon",
      "/staff/social/bluesky",
      "/staff/social/telegram",
      "/staff/social/newsletter",
      "/staff/social/spotify",
      "/staff/senyal",
      "/staff/historial",
      "/staff/auditlog",
      "/staff/configuracio",
    ];
    const have = new Set(STAFF_VIEWS.map((it) => it.to));
    for (const p of must) expect(have.has(p)).toBe(true);
  });

  it("Instagram and Spotify appear in BOTH the sidebar and the panell", () => {
    for (const to of ["/staff/social/instagram", "/staff/social/spotify"]) {
      expect(sidebarItems.some((it) => it.to === to)).toBe(true);
      expect(panellItems.some((it) => it.to === to)).toBe(true);
    }
  });

  it("panell tiles all carry a description", () => {
    for (const it of panellItems) {
      expect(typeof it.desc).toBe("string");
      expect(it.desc.length).toBeGreaterThan(0);
    }
  });
});
