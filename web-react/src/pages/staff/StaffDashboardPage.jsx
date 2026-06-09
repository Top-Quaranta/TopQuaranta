/**
 * StaffDashboardPage — landing for /staff.
 *
 * Tools grouped by the same taxonomy as the left sidebar
 * (`StaffLayout::GROUPS`) so the visual hierarchy stays consistent
 * and the operator's mental model is reused: whatever they're used to
 * scanning down on the side, they now also scan down here. Each group
 * gets its own banner; tools render as cards with a description and an
 * optional live counter pulled from `/api/v1/staff/dashboard/`.
 *
 * Adding a new staff tool: drop it in the right `GROUPS` entry and
 * (if it has a queue) wire its counter through `count`.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { STAFF_GROUPS } from "./staffViews";

function CountBadge({ n }) {
  if (!n) return null;
  return (
    <span className="ml-auto inline-flex items-center justify-center text-[11px] font-semibold bg-tq-yellow text-tq-ink rounded-full px-2 py-0.5 min-w-[1.5rem]">
      {n}
    </span>
  );
}

function Tile({ to, title, desc, count }) {
  return (
    <Link
      to={to}
      className="group flex flex-col p-4 bg-white text-tq-ink rounded-lg border border-black/5 hover:border-tq-ink/30 hover:shadow transition-all"
    >
      <div className="flex items-start gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <CountBadge n={count} />
      </div>
      <p className="text-xs opacity-70 mt-1 leading-snug">{desc}</p>
    </Link>
  );
}

// Panell tiles = the shared registry, keeping only the items flagged for
// the panell (drops the sidebar-only self-link). `countKey` indexes into
// the dashboard counters payload; `title` falls back to `label`.
const GROUPS = STAFF_GROUPS.map((g) => ({
  label: g.label,
  items: g.items
    .filter((it) => it.inPanell !== false)
    .map((it) => ({ ...it, title: it.title || it.label })),
})).filter((g) => g.items.length > 0);

export default function StaffDashboardPage() {
  const [counts, setCounts] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    api
      .get("/staff/dashboard/")
      .then((data) => {
        if (active) setCounts(data);
      })
      .catch((e) => {
        if (active) setError(e.message || "Error");
      });
    return () => {
      active = false;
    };
  }, []);

  const c = counts || {};

  return (
    <section>
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-white">Panell intern</h1>
        <p className="text-sm text-white/70">
          Eines d'administració TopQuaranta
          {counts && (
            <span className="ml-2 opacity-90">
              · {c.usuaris_total} usuaris actius
            </span>
          )}
        </p>
      </header>

      {error && (
        <p className="mb-4 text-sm text-red-300">
          No s'han pogut carregar els comptadors: {error}
        </p>
      )}

      <div className="space-y-7">
        {GROUPS.map((group) => (
          <div key={group.label}>
            <h2 className="text-[11px] uppercase tracking-widest text-white/60 mb-2">
              {group.label}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {group.items.map((item) => (
                <Tile
                  key={item.to}
                  to={item.to}
                  title={item.title}
                  desc={item.desc}
                  count={item.countKey ? c[item.countKey] : undefined}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
