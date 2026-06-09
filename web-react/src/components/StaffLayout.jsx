/**
 * StaffLayout — shell for every /staff/* route.
 *
 * Renders a dark vertical sidebar on the left with grouped links to
 * each staff area, and the routed content on the right. The yellow
 * top header from the public Layout is preserved — staff still need
 * one click back to the public site.
 *
 * Grouping rationale (2026-04-26):
 *   - Visió general  → daily glance: dashboard tiles + Estat panel.
 *   - Cua del dia    → things waiting on staff action (review queues).
 *   - Catàleg        → library editing surfaces.
 *   - Top            → ranking-specific staff views.
 *   - Comunitat      → Grup C admin (Publicacions + Usuaris).
 *   - Diagnòstic     → read-only signals / history / audit.
 *   - Sistema        → global config.
 *
 * On screens ≥ md the group labels are visible above each cluster.
 * Below md the sidebar collapses to a horizontal scroll strip; group
 * labels are hidden there and a subtle vertical divider keeps the
 * groups distinguishable in a single line.
 */
import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import { api } from "../lib/api";
import { STAFF_GROUPS } from "../pages/staff/staffViews";

// One light fetch on mount returns the count of pending
// SolicitudRevisio rows; cached in module-level state so navigating
// between staff pages reuses the value (until full page refresh).
let _cachedBadges = null;
function useStaffBadges() {
  const [badges, setBadges] = useState(_cachedBadges);
  useEffect(() => {
    if (_cachedBadges) return;
    api
      .get("/staff/sollicituds-revisio/?estat=pendent&page=1")
      .then((d) => {
        _cachedBadges = { sollicituds_revisio_pendents: d.n_pendents_total };
        setBadges(_cachedBadges);
      })
      .catch(() => {
        _cachedBadges = { sollicituds_revisio_pendents: 0 };
        setBadges(_cachedBadges);
      });
  }, []);
  return badges || {};
}

// Sidebar groups = the shared registry, keeping only the items flagged
// for the sidebar (every item by default; the panell-only opt-outs drop
// here).
const GROUPS = STAFF_GROUPS.map((g) => ({
  label: g.label,
  items: g.items.filter((it) => it.inSidebar !== false),
})).filter((g) => g.items.length > 0);

const linkBase =
  "text-sm px-3 py-2 rounded transition-colors whitespace-nowrap " +
  "md:w-full md:text-left";

const linkClass = ({ isActive }) =>
  linkBase +
  " " +
  (isActive
    ? "bg-tq-yellow text-tq-ink font-semibold"
    : "text-white/70 hover:text-white hover:bg-white/10");

export default function StaffLayout({ children }) {
  const badges = useStaffBadges();
  return (
    <div className="-mx-6 lg:-mx-12 flex flex-col md:flex-row min-h-[70vh]">
      {/* ── Dark sidebar ── */}
      <aside
        className="bg-tq-ink text-white md:w-56 md:shrink-0 md:min-h-[70vh] border-r border-white/5"
        aria-label="Navegació staff"
      >
        <div className="px-4 py-3 border-b border-white/5 hidden md:block">
          <p className="text-[10px] uppercase tracking-widest text-white/50">
            Panell intern
          </p>
          <p className="text-sm font-semibold">Staff</p>
        </div>

        <nav
          className="flex md:flex-col gap-0.5 px-2 py-2 overflow-x-auto md:overflow-visible"
          aria-label="Seccions staff"
        >
          {GROUPS.map((group, gi) => (
            <div
              key={group.label}
              className={
                "flex md:flex-col gap-0.5 " +
                // On mobile keep groups inline with a subtle divider so
                // the eye can still parse the clusters.
                (gi > 0
                  ? "md:mt-3 border-l md:border-l-0 border-white/10 md:border-0 pl-2 md:pl-0"
                  : "")
              }
            >
              <p
                className="hidden md:block text-[10px] uppercase tracking-widest text-white/70 px-3 mt-2 mb-1 select-none"
                aria-hidden="true"
              >
                {group.label}
              </p>
              {group.items.map(({ to, label, end, badge }) => {
                const n = badge ? badges[badge] : null;
                return (
                  <NavLink key={to} to={to} end={end} className={linkClass}>
                    <span className="inline-flex items-center gap-2">
                      {label}
                      {typeof n === "number" && n > 0 && (
                        <span className="inline-flex items-center justify-center min-w-[1.25rem] px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-tq-yellow text-tq-ink">
                          {n}
                        </span>
                      )}
                    </span>
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      {/* ── Main staff content ── */}
      <div className="flex-1 min-w-0 px-6 lg:px-12 py-6">{children}</div>
    </div>
  );
}
