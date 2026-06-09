/**
 * MatriuCanalToggles — the distribution-matrix cells for ONE channel (the
 * "què publica" section of each channel view + the Instagram section of
 * the cockpit). The SAME component renders every channel (mastodon /
 * bluesky / telegram / instagram / newsletter).
 *
 * Each seeded (canal × tipus) cell is one table row:
 *   - dia: a READ-ONLY indicator of the publish day(s), derived from the
 *     real calendar/cron on the backend (`dies_publicacio`): e.g.
 *     "Dissabte" for the global top, "Dilluns i dimecres" for the
 *     territorial, "Diumenge" for the newsletter, "—" where the channel
 *     never publishes that tipus. NOT editable — the calendar fixes it.
 *   - actiu: the on/off switch for the cell (the only editable control).
 * Backend: GET `/staff/social/matriu/` (filtered to this `canal` on the
 * client) + POST `/staff/social/matriu/toggle/` (sends `actiu` only).
 *
 * A non-seeded combo (e.g. newsletter × nous albums) paints a blank dash
 * — not a real slot.
 */
import { useEffect, useState } from "react";
import { api } from "../../../lib/api";

// Format a list of weekday ints (0=Mon … 6=Sun) into a Catalan label
// using the backend `dies` map: first capitalised, the rest lower-cased,
// joined with " i " ("Dilluns i dimecres"). Empty → em-dash.
function formatDies(dayInts, diesMap) {
  if (!dayInts || dayInts.length === 0) return "—";
  const labels = dayInts.map(
    (v) => diesMap.find((d) => d.value === v)?.label || String(v),
  );
  return labels.map((l, i) => (i === 0 ? l : l.toLowerCase())).join(" i ");
}

export default function MatriuCanalToggles({ canal }) {
  const [tipus, setTipus] = useState([]);
  const [dies, setDies] = useState([]);
  const [cells, setCells] = useState(null);
  const [busy, setBusy] = useState("");

  function reload() {
    api
      .get("/staff/social/matriu/")
      .then((d) => {
        setTipus(d.tipus || []);
        setDies(d.dies || []);
        const map = {};
        for (const c of d.cells || []) {
          if (c.canal === canal) map[c.tipus] = c;
        }
        setCells(map);
      })
      .catch(() => setCells({}));
  }

  useEffect(reload, [canal]);

  if (cells === null) return null;

  async function toggleActiu(t, actiu) {
    setBusy(t);
    try {
      await api.post("/staff/social/matriu/toggle/", {
        canal,
        tipus: t,
        actiu: !actiu,
      });
      reload();
    } finally {
      setBusy("");
    }
  }

  const rows = tipus.map((t) => ({ t, cell: cells[t.tipus] }));

  return (
    <table className="text-xs border-collapse">
      <thead>
        <tr className="text-tq-ink/50 text-left">
          <th className="pr-4 font-medium py-1">Tipus</th>
          <th className="pr-4 font-medium py-1">Dia</th>
          <th className="font-medium py-1">Actiu</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ t, cell }) => {
          if (!cell || !cell.seeded) {
            return (
              <tr key={t.tipus} className="text-tq-ink/25">
                <td className="pr-4 py-1">{t.label}</td>
                <td className="pr-4 py-1">—</td>
                <td className="py-1">—</td>
              </tr>
            );
          }
          const disabled = busy === t.tipus;
          return (
            <tr key={t.tipus}>
              <td className="pr-4 py-1">
                <span
                  className={cell.actiu ? "text-tq-ink/80" : "text-tq-ink/40"}
                >
                  {t.label}
                </span>
              </td>
              {/* Read-only indicator: the publish day comes from the
                  calendar/cron, it is not editable here. */}
              <td className="pr-4 py-1 text-tq-ink/60">
                {formatDies(cell.dies_publicacio, dies)}
              </td>
              <td className="py-1">
                <input
                  type="checkbox"
                  checked={cell.actiu}
                  disabled={disabled}
                  aria-label={`${canal} ${t.label} actiu`}
                  onChange={() => toggleActiu(t.tipus, cell.actiu)}
                />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
