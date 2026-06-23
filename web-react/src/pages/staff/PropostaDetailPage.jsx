/**
 * PropostaDetailPage — /staff/propostes/:pk
 *
 * Detail + approve / reject / merge. When approving triggers a 409 with
 * a `conflicts` list (some Deezer ID already belongs to another artist),
 * the conflict list becomes an interactive panel showing per-artist:
 *   - whether the existing artist is aprovat or pendent_review
 *   - direct links to the staff edit page + the public profile
 *   - a "Fusionar" button that merges the proposal into that artist
 *   - a "Rebutjar" fallback
 *
 * The merge call (`/staff/propostes/<pk>/fusionar/`) copies the
 * proposal's new Deezer IDs, localitzacions and missing social URLs
 * into the existing artist, marks the proposal aprovat+artista_creat,
 * and if the target was still pendent_review flips it to aprovat.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { Btn, PageHeader, Pill, TableCard } from '../../components/rd/surface'

function ConflictPanel({ conflicts, onMerge, onReject, busy }) {
  return (
    <div className="mb-4 bg-white text-tq-ink rounded-lg p-4 border border-yellow-300">
      <p className="text-[11px] uppercase tracking-widest font-semibold text-yellow-700 mb-1">
        Conflicte de Deezer ID
      </p>
      <p className="text-sm mb-3">
        Algun dels Deezer IDs de la proposta ja pertany a un altre artista
        del sistema. Tria què fer per cada cas:
      </p>
      <ul className="space-y-3">
        {conflicts.map(c => (
          <li key={c.deezer_id} className="border-t border-black/10 pt-3">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <p className="font-semibold">
                  Deezer ID <code className="bg-black/5 px-1 rounded">{c.deezer_id}</code>{' '}
                  → «{c.owner_nom}»
                </p>
                <p className="text-xs mt-1 flex flex-wrap gap-2 items-center">
                  <span className="opacity-60">estat:</span>
                  {c.owner_aprovat ? (
                    <Pill tone="green">Aprovat (verificat)</Pill>
                  ) : c.owner_pendent_review ? (
                    <Pill tone="yellow">Pendent</Pill>
                  ) : (
                    <Pill tone="gray">Descartat</Pill>
                  )}
                  <span className="opacity-60">·</span>
                  <Link
                    to={`/staff/artistes/${c.owner_pk}`}
                    className="underline hover:text-tq-yellow-deep"
                  >
                    editar
                  </Link>
                  {c.owner_slug && (
                    <>
                      <span className="opacity-60">·</span>
                      <Link
                        to={`/artista/${c.owner_slug}`}
                        className="underline hover:text-tq-yellow-deep"
                      >
                        perfil públic
                      </Link>
                    </>
                  )}
                </p>
              </div>
              <div className="flex gap-1 shrink-0">
                <Btn onClick={() => onMerge(c.owner_pk, c.owner_nom)} disabled={busy}>
                  Fusionar aquí
                </Btn>
              </div>
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-4 pt-3 border-t border-black/10 flex items-center gap-2">
        <p className="text-xs opacity-70 flex-1">
          Cap dels artistes existents és el bo?
        </p>
        <Btn tone="danger" onClick={onReject} disabled={busy}>
          Rebutjar proposta
        </Btn>
      </div>
    </div>
  )
}

export default function PropostaDetailPage() {
  const { pk } = useParams()
  const navigate = useNavigate()
  const [p, setP] = useState(null)
  const [err, setErr] = useState('')
  const [conflicts, setConflicts] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get(`/staff/propostes/${pk}/`).then(setP).catch(e => setErr(e.message))
  }, [pk])

  if (err && !p) return <p className="text-red-300">{err}</p>
  if (!p) return <p className="text-white/70">Carregant…</p>

  async function aprovar() {
    if (!confirm(`Crear l'artista «${p.nom}»?`)) return
    setBusy(true); setErr(''); setConflicts(null)
    try {
      const out = await api.post(`/staff/propostes/${pk}/aprovar/`)
      navigate(`/staff/artistes/${out.artista_pk}`)
    } catch (e) {
      if (e.status === 409 && e.payload?.conflicts) {
        setConflicts(e.payload.conflicts)
        setErr('')
      } else {
        setErr(e.payload?.error || e.message)
      }
    } finally { setBusy(false) }
  }

  async function fusionar(targetPk, targetNom) {
    if (!confirm(`Fusionar la proposta amb «${targetNom}»?\n\n` +
                 `S'afegiran els Deezer IDs, localitzacions i enllaços que ` +
                 `no tingui ja. La proposta quedarà marcada com aprovada.`)) return
    setBusy(true); setErr('')
    try {
      const out = await api.post(`/staff/propostes/${pk}/fusionar/`, {
        artista_pk: targetPk,
      })
      navigate(`/staff/artistes/${out.artista_pk}`)
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  async function rebutjar() {
    if (!confirm('Rebutjar aquesta proposta?')) return
    setBusy(true); setErr('')
    try {
      await api.post(`/staff/propostes/${pk}/rebutjar/`)
      navigate('/staff/propostes')
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  return (
    <section>
      <PageHeader
        title={p.nom}
        subtitle={<>Proposta de {p.usuari.email} · {p.created_at?.slice(0, 10)}</>}
        right={
          <>
            <Btn tone="outline" size="md" onClick={() => navigate('/staff/propostes')}>Tornar</Btn>
            {p.estat === 'pendent' && !conflicts && (
              <>
                <Btn size="md" onClick={aprovar} disabled={busy}>Aprovar</Btn>
                <Btn tone="danger" size="md" onClick={rebutjar} disabled={busy}>Rebutjar</Btn>
              </>
            )}
          </>
        }
      />

      {conflicts && (
        <ConflictPanel
          conflicts={conflicts}
          onMerge={fusionar}
          onReject={rebutjar}
          busy={busy}
        />
      )}
      {err && (
        <pre className="text-red-300 mb-3 whitespace-pre-wrap font-sans text-sm">{err}</pre>
      )}

      <div className="mb-3">
        <Pill tone={p.estat === 'aprovat' ? 'green' : p.estat === 'rebutjat' ? 'gray' : 'yellow'}>{p.estat}</Pill>
        {p.artista_creat && (
          <Link to={`/staff/artistes/${p.artista_creat.pk}`} className="ml-2 underline text-white/90 text-sm">
            Artista creat
          </Link>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <TableCard className="p-4">
          <h2 className="font-semibold mb-2">Justificació</h2>
          <p className="text-sm whitespace-pre-wrap">{p.justificacio || <em className="opacity-60">—</em>}</p>
        </TableCard>

        <TableCard className="p-4">
          <h2 className="font-semibold mb-2">Localitzacions</h2>
          {p.localitzacions?.length ? (
            <ul className="text-sm space-y-1">
              {p.localitzacions.map((l, i) => <li key={i}>· {l}</li>)}
            </ul>
          ) : (
            <p className="text-sm opacity-60">—</p>
          )}
        </TableCard>

        <TableCard className="p-4">
          <h2 className="font-semibold mb-2">Deezer</h2>
          {p.deezer_ids?.length ? (
            <ul className="text-sm space-y-1">
              {p.deezer_ids.map(id => <li key={id}>· {id}</li>)}
            </ul>
          ) : (
            <p className="text-sm opacity-60">—</p>
          )}
        </TableCard>

        <TableCard className="p-4">
          <h2 className="font-semibold mb-2">Xarxes</h2>
          {Object.keys(p.social || {}).length ? (
            <ul className="text-sm space-y-1">
              {Object.entries(p.social).map(([k, v]) => (
                <li key={k}>
                  <span className="font-semibold">{k}:</span>{' '}
                  <a href={v} target="_blank" rel="noopener" className="underline break-all">{v}</a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm opacity-60">—</p>
          )}
        </TableCard>
      </div>
    </section>
  )
}
