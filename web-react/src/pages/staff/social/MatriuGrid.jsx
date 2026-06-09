/**
 * MatriuGrid — the editable distribution matrix (canal × tipus).
 *
 * The THIRD gate over the master switch and the per-channel switches:
 * an unchecked cell means that channel does NOT distribute that content
 * type. Reads `/staff/social/matriu/`, toggles via
 * `/staff/social/matriu/toggle/`. The website + RSS are not in the
 * matrix and never appear here. An "off" cell is shown inactive, never
 * hidden. Non-seeded combos (e.g. newsletter × nous albums) render as a
 * non-toggleable blank — they are not real distribution slots.
 */
import { useEffect, useState } from 'react'
import { api } from '../../../lib/api'

export default function MatriuGrid() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState('')

  function reload() {
    api
      .get('/staff/social/matriu/')
      .then(setData)
      .catch(() => setData(null))
  }

  useEffect(() => {
    reload()
  }, [])

  if (!data) return null

  const cellMap = {}
  for (const c of data.cells) cellMap[`${c.canal}|${c.tipus}`] = c

  async function toggle(canal, tipus, actiu) {
    const key = `${canal}|${tipus}`
    setBusy(key)
    try {
      await api.post('/staff/social/matriu/toggle/', { canal, tipus, actiu: !actiu })
      reload()
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="bg-white text-tq-ink rounded-lg p-4 mb-4">
      <div className="text-sm font-bold uppercase tracking-wide mb-1">
        Matriu de distribució
      </div>
      <p className="text-xs text-tq-ink/60 mb-3">
        Què distribueix cada canal. Desmarcar (canal × tipus) atura eixa
        distribució eixe canal (per a la newsletter, no s'envia). La web i l'RSS
        no es regeixen per la matriu.
      </p>
      <div className="overflow-x-auto">
        <table className="text-sm">
          <thead>
            <tr>
              <th className="text-left py-1 pr-4" />
              {data.tipus.map((t) => (
                <th key={t.tipus} className="px-3 py-1 font-semibold text-center">
                  {t.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.canals.map((c) => (
              <tr key={c.canal} className="border-t border-tq-ink/10">
                <td className="py-2 pr-4 font-semibold">{c.label}</td>
                {data.tipus.map((t) => {
                  const cell = cellMap[`${c.canal}|${t.tipus}`]
                  const key = `${c.canal}|${t.tipus}`
                  if (!cell || !cell.seeded) {
                    return (
                      <td key={key} className="px-3 py-2 text-center text-tq-ink/25">
                        —
                      </td>
                    )
                  }
                  return (
                    <td key={key} className="px-3 py-2 text-center">
                      <label className="inline-flex items-center gap-1 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={cell.actiu}
                          disabled={busy === key}
                          onChange={() => toggle(c.canal, t.tipus, cell.actiu)}
                          aria-label={`${c.label} ${t.label}`}
                        />
                        <span
                          className={
                            cell.actiu ? 'text-tq-ink/80' : 'text-tq-ink/40'
                          }
                        >
                          {cell.actiu ? 'on' : 'off'}
                        </span>
                      </label>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
