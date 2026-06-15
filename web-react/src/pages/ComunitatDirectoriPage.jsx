/**
 * ComunitatDirectoriPage — /comunitat/directori (redisseny web).
 *
 * Authenticated directory of opted-in members. Reskinned to the new
 * language: glass header + dark filter controls + glass member cards.
 * Endpoint + logic conserved. (Drops the last editorial.jsx import on
 * the public surface — territory names now come from rd/terr.)
 */
import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import useApi from '../hooks/useApi'
import { Glass, Kicker, Crit } from '../components/rd/primitives'
import { terr } from '../components/rd/terr'

const TERRITORIS = [
  ['', 'Tots els territoris'],
  ...['CAT', 'VAL', 'BAL', 'AND', 'CNO', 'FRA', 'ALG', 'ALT'].map(c => [c, terr(c).nom]),
]
const selCls = 'px-3 py-1.5 rounded-lg border border-white/15 bg-white/[0.07] text-sm text-white focus:outline-none focus:border-tq-yellow'

export default function ComunitatDirectoriPage() {
  const { profile, loading } = useAuth()
  const [q, setQ] = useState('')
  const [rol, setRol] = useState('')
  const [territori, setTerritori] = useState('')
  const [obert, setObert] = useState(false)
  const [page, setPage] = useState(1)

  // Slice E: directory funnel instrumentation.
  function fire(clau, dim1 = '') {
    import('../lib/analytics').then(({ trackEvent }) => trackEvent(clau, dim1))
  }
  useEffect(() => {
    fire('comunitat_directori_vista')
  }, [])

  const _p = new URLSearchParams({ page })
  if (q) _p.set('q', q)
  if (rol) _p.set('rol', rol)
  if (territori) _p.set('territori', territori)
  if (obert) _p.set('obert', '1')
  const { data } = useApi(profile ? `/comunitat/directori/?${_p}` : null)

  if (loading) return null
  if (!profile) return <Navigate to="/compte/accedir?next=/comunitat/directori" replace />

  return (
    <section className="max-w-4xl mx-auto text-white">
      <Glass className="rd-com-pitch mb-5">
        <Kicker color="var(--color-tq-yellow)">comunitat · directori</Kicker>
        <Crit as="h1" className="rd-com-title" style={{ marginTop: 6 }}>MÚSICS OBERTS A CONNECTAR</Crit>
        <p className="rd-com-body" style={{ marginTop: 8 }}>
          Filtra per rol, instrument o territori per trobar la persona que
          busques. Només hi apareix qui ha decidit ser visible — si no hi ets,
          marca la casella al teu{' '}
          <Link to="/comunitat/perfil" className="rd-prose-link">perfil</Link>.
        </p>
      </Glass>

      <div className="flex flex-wrap gap-2 mb-4 items-center">
        <label htmlFor="dir-q" className="sr-only">Cercar al directori</label>
        <input id="dir-q" value={q} onChange={e => { setPage(1); setQ(e.target.value) }}
          placeholder="Cerca nom, instrument, bio…" className={selCls + ' placeholder-white/40'} />
        <label htmlFor="dir-rol" className="sr-only">Rol musical</label>
        <select id="dir-rol" value={rol} onChange={e => { setPage(1); setRol(e.target.value); fire('comunitat_directori_filtre', 'rol') }} className={selCls}>
          <option value="" className="text-tq-ink">Rol: tots</option>
          {(data?.rol_choices || []).map(([v, l]) => <option key={v} value={v} className="text-tq-ink">{l}</option>)}
        </select>
        <label htmlFor="dir-terr" className="sr-only">Territori</label>
        <select id="dir-terr" value={territori} onChange={e => { setPage(1); setTerritori(e.target.value); fire('comunitat_directori_filtre', 'territori') }} className={selCls}>
          {TERRITORIS.map(([c, l]) => <option key={c} value={c} className="text-tq-ink">{l}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm text-white/80">
          <input type="checkbox" checked={obert} onChange={e => { setPage(1); setObert(e.target.checked); fire('comunitat_directori_filtre', 'obert') }} />
          Obert a col·laboracions
        </label>
      </div>

      {!data && <p className="rd-empty">Carregant…</p>}
      {data?.results?.length === 0 && <p className="rd-empty">Cap usuari amb aquests filtres.</p>}

      <ul className="grid sm:grid-cols-2 gap-3">
        {data?.results?.map(u => (
          <li key={u.usuari_id}>
            <Glass className="p-4">
              <div className="flex items-start gap-3">
                {u.imatge_url ? (
                  <img src={u.imatge_url} alt="" className="w-12 h-12 rounded-full object-cover" />
                ) : (
                  <div className="w-12 h-12 rounded-full bg-white/10 flex items-center justify-center text-xs font-bold">
                    {(u.nom_public || u.username).slice(0, 2).toUpperCase()}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="font-bold truncate text-white">
                    {u.nom_public}
                    {u.visible_directori === false && (
                      <span className="inline-block ml-2 text-[10px] font-semibold uppercase bg-white/10 text-white/60 px-1.5 py-0.5 rounded align-middle"
                        title="Aquest perfil no és visible al directori per a la resta d'usuaris">Perfil no públic</span>
                    )}
                  </p>
                  <p className="text-[11px] text-white/60">{u.rol_musical}{u.instruments && ` · ${u.instruments}`}</p>
                  {u.localitat && <p className="text-[11px] text-white/50 mt-0.5">{u.localitat}</p>}
                  {u.obert_colaboracions && (
                    <span className="inline-block mt-1 text-[10px] font-semibold uppercase bg-tq-yellow text-tq-ink px-2 py-0.5 rounded">Obert a col·laboracions</span>
                  )}
                  {u.artistes_gestionats?.length > 0 && (
                    <p className="text-xs mt-2 text-white/70">
                      Gestiona:{' '}
                      {u.artistes_gestionats.map((a, i) => (
                        <span key={a.slug}>{i > 0 && ', '}<Link to={`/artista/${a.slug}`} className="rd-prose-link">{a.nom}</Link></span>
                      ))}
                    </p>
                  )}
                </div>
              </div>
              <div className="mt-3 flex justify-end">
                <Link to={`/comunitat/missatges?amb=${u.usuari_id}`} className="rd-btn rd-btn--hot" style={{ fontSize: 12, padding: '7px 13px' }}>✉ Missatge</Link>
              </div>
            </Glass>
          </li>
        ))}
      </ul>

      {data?.num_pages > 1 && (
        <nav className="rd-pager" style={{ marginTop: 20, justifyContent: 'flex-start' }} aria-label="Paginació">
          <button type="button" disabled={!data.has_previous} onClick={() => setPage(p => p - 1)} className="rd-btn rd-btn--ghost">Anterior</button>
          <span className="text-sm text-white/60 tabular-nums">Pàg {data.page} de {data.num_pages} · {data.total} usuaris</span>
          <button type="button" disabled={!data.has_next} onClick={() => setPage(p => p + 1)} className="rd-btn rd-btn--ghost">Següent</button>
        </nav>
      )}
    </section>
  )
}
