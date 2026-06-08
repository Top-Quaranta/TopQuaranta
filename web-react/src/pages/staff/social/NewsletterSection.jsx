/**
 * NewsletterSection — Section 1 of the Newsletter channel view (llesca 3).
 *
 * Live can-generate indicator + consolidated-week selector + on-demand
 * "Generate (engine)" + the shared NewsletterDraftEditor for the chosen
 * week. The selector lists only weeks with a consolidated TopSetmanal
 * (so every option is generatable); the banner reflects whether the
 * automatic Saturday routine could generate the CURRENT week right now.
 */
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../../lib/api'
import { Btn, Pill, Select, TableCard } from '../../../components/staff/StaffTable'
import NewsletterDraftEditor from './NewsletterDraftEditor'

export default function NewsletterSection() {
  const [info, setInfo] = useState(null)
  const [selected, setSelected] = useState('')
  const [busy, setBusy] = useState(false)
  const [genErr, setGenErr] = useState('')
  const [reloadToken, setReloadToken] = useState(0)

  function refresh() {
    return api
      .get('/staff/newsletter/setmanes/')
      .then((d) => {
        setInfo(d)
        // Default to the latest consolidated week the first time.
        setSelected((cur) => cur || d.setmanes?.[0]?.setmana || '')
      })
      .catch(() => setInfo({ setmanes: [], current: null }))
  }
  useEffect(() => {
    refresh()
  }, [])

  const selectedRow = useMemo(
    () => (info?.setmanes || []).find((w) => w.setmana === selected),
    [info, selected]
  )
  const current = info?.current
  const currentReady = current?.status === 'ready'

  async function generate() {
    if (!selected) return
    setBusy(true)
    setGenErr('')
    try {
      await api.post(
        `/staff/newsletter/esborrany/generar/?setmana=${encodeURIComponent(selected)}`
      )
      setReloadToken((t) => t + 1)
      await refresh()
    } catch (e) {
      setGenErr(e.payload?.error || e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h2 className="mb-2 text-base font-bold text-white font-display">
        Esborrany sota demanda
      </h2>
      <TableCard className="p-4 space-y-4">
        {/* Live indicator for the current (automatic) week. */}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-[11px] uppercase tracking-widest text-tq-ink/60">
            Setmana actual
          </span>
          {current ? (
            <>
              <Pill tone={currentReady ? 'green' : 'gray'}>
                {currentReady ? 'Consolidada' : 'No consolidada'}
              </Pill>
              <span className="text-tq-ink/75">
                {currentReady
                  ? 'la rutina podria generar-la ara.'
                  : 'la rutina no podria generar-la ara (top no consolidat).'}
              </span>
            </>
          ) : (
            <span className="text-tq-ink/60">Carregant estat…</span>
          )}
        </div>

        {/* Week selector (consolidated weeks only) + generate. */}
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs font-semibold text-tq-ink/80">
            <span>Setmana consolidada</span>
            <Select
              aria-label="Setmana"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              {(info?.setmanes || []).length === 0 && (
                <option value="">— cap setmana consolidada —</option>
              )}
              {(info?.setmanes || []).map((w) => (
                <option key={w.setmana} value={w.setmana}>
                  {w.setmana}
                  {w.has_draft ? ` · esborrany ${w.estat}` : ''}
                </option>
              ))}
            </Select>
          </label>
          <Btn tone="primary" disabled={busy || !selected} onClick={generate}>
            {selectedRow?.has_draft ? 'Regenerar (motor)' : 'Generar (motor)'}
          </Btn>
          <span className="text-[11px] text-tq-ink/60 max-w-sm">
            Genera el text amb el motor (sense efectes secundaris). No envia mai;
            l'enviament real és el cron de diumenge.
          </span>
        </div>
        {genErr && <p className="text-sm text-red-700">{genErr}</p>}

        {/* The shared editor for the chosen week. */}
        <div className="border-t border-tq-ink/10 pt-4">
          <NewsletterDraftEditor
            setmana={selected}
            reloadToken={reloadToken}
            onChanged={refresh}
          />
        </div>
      </TableCard>
    </div>
  )
}
