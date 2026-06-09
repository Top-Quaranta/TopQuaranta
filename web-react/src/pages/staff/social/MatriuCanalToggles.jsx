/**
 * MatriuCanalToggles — the editable distribution-matrix cells for ONE
 * channel (the "què publica" section of each channel view + the
 * Instagram section of the cockpit). Reuses the same backend as the old
 * central grid: GET `/staff/social/matriu/` (filtered to this `canal` on
 * the client) + POST `/staff/social/matriu/toggle/`.
 *
 * An off cell is shown inactive, never hidden. A non-seeded combo (e.g.
 * newsletter × nous albums) paints a blank dash — not a real slot.
 */
import { useEffect, useState } from 'react'
import { api } from '../../../lib/api'

export default function MatriuCanalToggles({ canal }) {
  const [tipus, setTipus] = useState([])
  const [cells, setCells] = useState(null)
  const [busy, setBusy] = useState('')

  function reload() {
    api
      .get('/staff/social/matriu/')
      .then((d) => {
        setTipus(d.tipus || [])
        const map = {}
        for (const c of d.cells || []) {
          if (c.canal === canal) map[c.tipus] = c
        }
        setCells(map)
      })
      .catch(() => setCells({}))
  }

  useEffect(reload, [canal])

  if (cells === null) return null

  async function toggle(t, actiu) {
    setBusy(t)
    try {
      await api.post('/staff/social/matriu/toggle/', { canal, tipus: t, actiu: !actiu })
      reload()
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="flex flex-wrap gap-3">
      {tipus.map((t) => {
        const cell = cells[t.tipus]
        if (!cell || !cell.seeded) {
          return (
            <span key={t.tipus} className="text-xs text-tq-ink/25">
              {t.label} —
            </span>
          )
        }
        return (
          <label
            key={t.tipus}
            className="inline-flex items-center gap-1.5 text-xs cursor-pointer"
          >
            <input
              type="checkbox"
              checked={cell.actiu}
              disabled={busy === t.tipus}
              onChange={() => toggle(t.tipus, cell.actiu)}
              aria-label={`${canal} ${t.label}`}
            />
            <span className={cell.actiu ? 'text-tq-ink/80' : 'text-tq-ink/40'}>
              {t.label}
            </span>
          </label>
        )
      })}
    </div>
  )
}
