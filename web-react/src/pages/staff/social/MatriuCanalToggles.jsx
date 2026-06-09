/**
 * MatriuCanalToggles — the editable distribution-matrix cells for ONE
 * channel (the "què publica" section of each channel view + the
 * Instagram section of the cockpit). The SAME component renders every
 * channel (mastodon / bluesky / telegram / instagram / newsletter).
 *
 * Each seeded (canal × tipus) cell is one table row with two controls:
 *   - dia: a weekday dropdown ("sense restricció" = no day gate = the
 *     default; otherwise publish only on that weekday).
 *   - actiu: the on/off switch for the cell.
 * Backend: GET `/staff/social/matriu/` (filtered to this `canal` on the
 * client) + POST `/staff/social/matriu/toggle/` (sends `actiu` OR
 * `dia_setmana`; a day edit never flips the switch).
 *
 * A non-seeded combo (e.g. newsletter × nous albums) paints a blank dash
 * — not a real slot.
 */
import { useEffect, useState } from "react";
import { api } from "../../../lib/api";

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

  async function send(t, body) {
    setBusy(t);
    try {
      await api.post("/staff/social/matriu/toggle/", {
        canal,
        tipus: t,
        ...body,
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
              <td className="pr-4 py-1">
                <select
                  className="border border-tq-ink/20 rounded px-1 py-0.5 bg-white"
                  value={cell.dia_setmana ?? ""}
                  disabled={disabled}
                  aria-label={`${canal} ${t.label} dia`}
                  onChange={(e) =>
                    send(t.tipus, {
                      dia_setmana:
                        e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                >
                  <option value="">Sense restricció</option>
                  {dies.map((d) => (
                    <option key={d.value} value={d.value}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </td>
              <td className="py-1">
                <input
                  type="checkbox"
                  checked={cell.actiu}
                  disabled={disabled}
                  aria-label={`${canal} ${t.label} actiu`}
                  onChange={() => send(t.tipus, { actiu: !cell.actiu })}
                />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
