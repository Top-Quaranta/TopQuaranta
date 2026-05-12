/**
 * ComunitatDirectoriPage — /comunitat/directori
 *
 * Authenticated-users-only directory of people who've opted in
 * (visible_directori=True). No individual profile page exists —
 * this listing is the maximum exposure surface.
 */
import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import useApi from '../hooks/useApi'
import { TERRITORI_NOM } from '../components/editorial'

// Directory filter options. The explicit code list controls which
// territoris appear in the picker (PPCC and CAR are intentionally
// omitted: PPCC aggregates the rest, CAR has no community yet).
// Labels come from the canonical map so a rename only happens once.
const TERRITORIS = [
  ['', 'Tots els territoris'],
  ...['CAT', 'VAL', 'BAL', 'AND', 'CNO', 'FRA', 'ALG', 'ALT'].map(c => [c, TERRITORI_NOM[c]]),
]

export default function ComunitatDirectoriPage() {
  const { profile, loading } = useAuth()
  const [q, setQ] = useState('')
  const [rol, setRol] = useState('')
  const [territori, setTerritori] = useState('')
  const [obert, setObert] = useState(false)
  const [page, setPage] = useState(1)

  // Build path so useApi keys cancellation+refetch off it.
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
      {/* Header card — same shape as ComunitatPage so the sub-pages
          read as siblings. */}
      <div className="bg-tq-ink/40 border border-white/10 rounded-lg p-4 md:p-5 mb-5">
        <p className="text-[10px] uppercase tracking-widest text-tq-yellow">
          Comunitat · Directori
        </p>
        <h1 className="text-xl md:text-2xl font-bold font-display mt-1 leading-tight">
          Músics i creadors oberts a connectar
        </h1>
        <p className="text-sm text-white/80 mt-2 leading-relaxed">
          Filtra per rol, instrument o territori per trobar la persona
          que busques. Només hi apareix qui ha decidit ser visible — si
          no hi ets, marca la casella al teu{' '}
          <Link to="/comunitat/perfil" className="underline hover:text-tq-yellow transition-colors">perfil</Link>.
        </p>
      </div>

      {/* Filters row — labels are sr-only because each control's
          first option / placeholder reads as the label visually. */}
      <div className="flex flex-wrap gap-2 mb-4">
        <label htmlFor="dir-q" className="sr-only">Cercar al directori</label>
        <input
          id="dir-q"
          value={q}
          onChange={e => { setPage(1); setQ(e.target.value) }}
          placeholder="Cerca nom, instrument, bio…"
          className="px-3 py-1.5 rounded border border-white/20 bg-white/5 text-sm text-white placeholder-white/40 focus:outline-none focus:border-tq-yellow"
        />
        <label htmlFor="dir-rol" className="sr-only">Rol musical</label>
        <select id="dir-rol" value={rol} onChange={e => { setPage(1); setRol(e.target.value) }}
                className="px-3 py-1.5 rounded border border-white/20 bg-white/5 text-sm text-white focus:outline-none focus:border-tq-yellow">
          <option value="" className="text-tq-ink">Rol: tots</option>
          {(data?.rol_choices || []).map(([v, l]) => (
            <option key={v} value={v} className="text-tq-ink">{l}</option>
          ))}
        </select>
        <label htmlFor="dir-terr" className="sr-only">Territori</label>
        <select id="dir-terr" value={territori} onChange={e => { setPage(1); setTerritori(e.target.value) }}
                className="px-3 py-1.5 rounded border border-white/20 bg-white/5 text-sm text-white focus:outline-none focus:border-tq-yellow">
          {TERRITORIS.map(([c, l]) => (
            <option key={c} value={c} className="text-tq-ink">{l}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={obert} onChange={e => { setPage(1); setObert(e.target.checked) }} />
          Obert a col·laboracions
        </label>
      </div>

      {!data && <p className="text-sm text-white/70">Carregant…</p>}
      {data?.results?.length === 0 && (
        <p className="text-sm text-white/60 italic">Cap usuari amb aquests filtres.</p>
      )}

      <ul className="grid sm:grid-cols-2 gap-3">
        {data?.results?.map(u => (
          <li key={u.usuari_id} className="bg-white text-tq-ink rounded-lg p-4">
            <div className="flex items-start gap-3">
              {u.imatge_url ? (
                <img src={u.imatge_url} alt="" className="w-12 h-12 rounded-full object-cover" />
              ) : (
                <div className="w-12 h-12 rounded-full bg-tq-ink/10 flex items-center justify-center text-xs font-bold">
                  {(u.nom_public || u.username).slice(0, 2).toUpperCase()}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <p className="font-bold truncate">{u.nom_public}</p>
                <p className="text-[11px] opacity-70">
                  {u.rol_musical}
                  {u.instruments && ` · ${u.instruments}`}
                </p>
                {u.localitat && <p className="text-[11px] opacity-60 mt-0.5">{u.localitat}</p>}
                {u.obert_colaboracions && (
                  <span className="inline-block mt-1 text-[10px] font-semibold uppercase bg-tq-yellow text-tq-ink px-2 py-0.5 rounded">
                    Obert a col·laboracions
                  </span>
                )}
                {u.artistes_gestionats?.length > 0 && (
                  <p className="text-xs mt-2">
                    Gestiona:{' '}
                    {u.artistes_gestionats.map((a, i) => (
                      <span key={a.slug}>
                        {i > 0 && ', '}
                        <Link to={`/artista/${a.slug}`} className="underline hover:text-tq-yellow-deep">{a.nom}</Link>
                      </span>
                    ))}
                  </p>
                )}
              </div>
            </div>
            <div className="mt-3 flex justify-end">
              <Link
                to={`/comunitat/missatges?amb=${u.usuari_id}`}
                className="text-xs font-semibold px-3 py-1.5 bg-tq-ink text-tq-yellow rounded hover:bg-tq-ink/90"
              >
                ✉ Missatge
              </Link>
            </div>
          </li>
        ))}
      </ul>

      {data?.num_pages > 1 && (
        <div className="flex items-center gap-2 mt-4 text-xs text-white/60">
          <button disabled={!data.has_previous} onClick={() => setPage(p => p - 1)}
                  className="px-3 py-1 rounded border border-white/20 disabled:opacity-40">Anterior</button>
          <span>Pàg {data.page} de {data.num_pages} · {data.total} usuaris</span>
          <button disabled={!data.has_next} onClick={() => setPage(p => p + 1)}
                  className="px-3 py-1 rounded border border-white/20 disabled:opacity-40">Següent</button>
        </div>
      )}
    </section>
  )
}
