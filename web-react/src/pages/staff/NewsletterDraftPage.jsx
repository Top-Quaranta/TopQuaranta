/**
 * NewsletterDraftPage — /staff/social/esborrany
 *
 * Review surface for the weekly newsletter draft (opt-out flow). The
 * Saturday cron generates the draft from the consolidated top and emails
 * staff a link here. The draft sends on Sunday UNLESS cancelled — so the
 * default action is "do nothing". Staff can edit the subject / editorial
 * text or cancel.
 *
 * Staff tool, no fancy chrome; reuses the panel's Tailwind tq-* tokens.
 */
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { Input } from '../../components/staff/StaffTable'

const ESTAT_TONE = {
  pendent:   'bg-yellow-100 text-yellow-900',
  enviat:    'bg-emerald-100 text-emerald-900',
  cancellat: 'bg-gray-300 text-gray-800',
}

export default function NewsletterDraftPage() {
  const [params] = useSearchParams()
  const setmana = params.get('setmana') || ''
  const [draft, setDraft] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [subject, setSubject] = useState('')
  const [narrative, setNarrative] = useState('')
  // Faithful full-email preview (rendered server-side, render-only).
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewBusy, setPreviewBusy] = useState(false)
  const [previewErr, setPreviewErr] = useState('')

  const qs = setmana ? `?setmana=${encodeURIComponent(setmana)}` : ''

  function hydrate(d) {
    setDraft(d)
    setSubject(d.subject || '')
    setNarrative(d.narrative_html || '')
  }

  const reload = () =>
    api.get(`/staff/newsletter/esborrany/${qs}`)
      .then(d => { hydrate(d); setErr('') })
      .catch(e => setErr(e.payload?.error || e.message))
  useEffect(() => { reload() }, [setmana])

  // Render the full email server-side, sending the editor's LIVE
  // subject/narrative as overrides so unsaved edits show. The list +
  // covers are rebuilt from the consolidated top by the endpoint.
  async function fetchPreview(subj, narr) {
    setPreviewBusy(true)
    try {
      const res = await api.post(`/staff/newsletter/esborrany/preview/${qs}`, {
        subject: subj,
        narrative_html: narr,
      })
      setPreviewHtml(res.html || '')
      setPreviewErr('')
    } catch (e) {
      setPreviewErr(e.payload?.error || e.message)
    } finally {
      setPreviewBusy(false)
    }
  }

  // Debounce preview refresh as the editor changes (only once a draft is
  // loaded). 600 ms after the last keystroke.
  const debounceRef = useRef(null)
  useEffect(() => {
    if (!draft) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => fetchPreview(subject, narrative), 600)
    return () => debounceRef.current && clearTimeout(debounceRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subject, narrative, draft?.setmana])

  if (err) return <p className="p-6 text-red-700">Error: {err}</p>
  if (!draft) return <p className="p-6">Carregant…</p>

  const editable = draft.estat === 'pendent'
  const dirty = subject !== draft.subject || narrative !== draft.narrative_html

  async function save() {
    setBusy(true)
    try {
      const d = await api.patch(`/staff/newsletter/esborrany/${qs}`, {
        subject, narrative_html: narrative,
      })
      hydrate(d)
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  async function cancel() {
    if (!confirm('Cancel·lar l\'enviament d\'aquesta newsletter? No s\'enviarà diumenge.')) return
    setBusy(true)
    try {
      const d = await api.post(`/staff/newsletter/esborrany/cancellar/${qs}`, {})
      hydrate(d)
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  return (
    <div className="p-4 sm:p-6 max-w-3xl space-y-4">
      <div>
        <h1 className="text-xl font-bold font-display">Esborrany de newsletter</h1>
        <p className="text-xs text-tq-ink/75 mt-1">
          Setmana {draft.setmana} · font {draft.font}
          {draft.editat && ' · editat'}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <span className={
          'inline-block text-[11px] uppercase tracking-wide font-semibold px-2 py-0.5 rounded-full ' +
          (ESTAT_TONE[draft.estat] || 'bg-gray-200 text-gray-800')
        }>
          {draft.estat === 'pendent' ? "S'enviarà" : draft.estat}
        </span>
        <span className="text-xs text-tq-ink/75">
          Enviament previst: <strong>diumenge {draft.send_date}</strong>
          {draft.enviat_at && ` · enviat ${new Date(draft.enviat_at).toLocaleString('ca')}`}
        </span>
      </div>

      {!draft.newsletter_actiu && (
        <p className="text-xs bg-red-50 border border-red-300 rounded-md p-2 text-red-900">
          Atenció: el canal newsletter està pausat (mestre o switch propi).
          Encara que no es cancel·li, no s'enviarà fins reactivar-lo.
        </p>
      )}

      <label className="block">
        <span className="text-[11px] uppercase tracking-widest text-tq-ink/75">Assumpte</span>
        <Input
          value={subject}
          disabled={!editable || busy}
          maxLength={300}
          onChange={e => setSubject(e.target.value)}
          className="mt-1 w-full"
        />
      </label>

      <label className="block">
        <span className="text-[11px] uppercase tracking-widest text-tq-ink/75">
          Text editorial (HTML)
        </span>
        <textarea
          value={narrative}
          disabled={!editable || busy}
          onChange={e => setNarrative(e.target.value)}
          rows={8}
          className="mt-1 w-full border rounded-md p-2 text-sm font-mono"
        />
      </label>

      <div>
        <div className="flex items-center justify-between mb-1">
          <p className="text-[11px] uppercase tracking-widest text-tq-ink/75">
            Vista prèvia (tota la newsletter, tal com s'enviarà)
          </p>
          <button
            type="button"
            onClick={() => fetchPreview(subject, narrative)}
            disabled={previewBusy}
            className="text-xs px-2 py-1 rounded border border-tq-ink/20 hover:bg-gray-100"
          >
            {previewBusy ? 'Renderitzant…' : 'Refresca'}
          </button>
        </div>
        <p className="text-[11px] text-tq-ink/60 mb-1">
          Renderitzada al servidor pel mateix camí que l'enviament (text +
          llista + caràtules reals; fallback al logo si en falta una).
          Reflecteix els canvis no desats de l'editor.
        </p>
        {previewErr && (
          <p className="text-xs text-red-700 mb-1">Error de render: {previewErr}</p>
        )}
        <iframe
          title="Vista prèvia de la newsletter"
          sandbox=""
          srcDoc={previewHtml || '<p style="font-family:sans-serif;color:#999;padding:1rem">Carregant vista prèvia…</p>'}
          className="w-full h-[640px] border rounded-md bg-white"
        />
      </div>

      {editable && (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={save}
            disabled={busy || !dirty}
            className={
              'px-4 py-2 rounded-md text-sm font-semibold ' +
              (dirty ? 'bg-tq-yellow text-tq-ink hover:opacity-90' : 'bg-gray-200 text-tq-ink/60')
            }
          >
            Desa els canvis
          </button>
          <button
            type="button"
            onClick={cancel}
            disabled={busy}
            className="px-4 py-2 rounded-md text-sm font-semibold bg-red-700 text-white hover:bg-red-800"
          >
            Cancel·la l'enviament
          </button>
        </div>
      )}

      <section>
        <h2 className="text-base font-bold font-display mb-1">Top amb què sortirà</h2>
        <p className="text-xs text-tq-ink/75 mb-2">
          Reconstruït en viu des del top final; compara'l amb el text per
          detectar desajustos. La llista definitiva es torna a calcular en
          enviar diumenge.
        </p>
        <ol className="text-sm space-y-0.5">
          {(draft.entries || []).map(e => (
            <li key={e.posicio} className="flex gap-2">
              <span className="tabular-nums text-tq-ink/60 w-6">{e.posicio}.</span>
              <span className="font-semibold">{e.canco_nom}</span>
              <span className="text-tq-ink/75">— {e.artista_nom}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
