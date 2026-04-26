/**
 * ComunitatPage — /comunitat
 *
 * Editorial redesign (Sprint J): unified-feed page sitting inside
 * `ComunitatLayout` (which already provides the dark sidebar). We
 * skip full-bleed bands here because the layout owns the sidebar
 * identity — instead we use a header card + clean post list so the
 * page reads as a sibling of the staff dashboard.
 *
 * Authenticated users see internal + public + their own posts; the
 * anonymous public feed lives at /comunitat/public (separate page).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { stripMarkdown } from '../lib/strip-markdown'
import { useAuth } from '../context/AuthContext'

const FILTRE_OPTS = [
  ['',          'Tot'],
  ['internes',  'Internes'],
  ['publiques', 'Públiques'],
  ['meves',     'Meves'],
]

function PillFilter({ value, onChange }) {
  return (
    <div className="flex gap-1 flex-wrap" role="tablist" aria-label="Filtre de feed">
      {FILTRE_OPTS.map(([v, l]) => (
        <button
          key={v}
          type="button"
          role="tab"
          aria-selected={value === v}
          onClick={() => onChange(v)}
          className={
            'text-xs font-semibold px-3 py-1 rounded-full transition-colors ' +
            (value === v
              ? 'bg-tq-yellow text-tq-ink'
              : 'bg-white/10 text-white/80 hover:bg-white/20')
          }
        >
          {l}
        </button>
      ))}
    </div>
  )
}

function formatDate(iso) {
  return iso ? iso.slice(0, 10) : ''
}

/* Estat label tones — same vocabulary the staff publication panel
 * uses, but rendered against white tiles rather than dark surfaces.
 * Each tone passes 4.5:1 on white. */
function EstatBadge({ estat }) {
  const tone = {
    esborrany: 'bg-gray-200 text-gray-800',
    pendent:   'bg-yellow-100 text-yellow-900',
    publicat:  'bg-emerald-100 text-emerald-900',
    rebutjat:  'bg-red-100 text-red-900',
  }[estat] || 'bg-gray-200 text-gray-800'
  return (
    <span className={'text-[10px] uppercase tracking-wide font-semibold px-2 py-0.5 rounded-full ' + tone}>
      {estat}
    </span>
  )
}

/* Anonymous landing — wrapped in the same hero card style we use
 * for authenticated visitors, just with a different action set. */
function AnonView() {
  return (
    <section className="max-w-3xl mx-auto text-white">
      <div className="bg-tq-ink/40 border border-white/10 rounded-lg p-5 md:p-6">
        <p className="text-[10px] uppercase tracking-widest text-tq-yellow">
          Comunitat
        </p>
        <h1 className="text-2xl md:text-3xl font-bold font-display mt-1.5 leading-tight">
          Un espai per a músics i amants de la música en català
        </h1>
        <p className="text-sm text-white/80 mt-3 leading-relaxed">
          El feed intern és per a usuaris registrats. Mentrestant, pots
          llegir les publicacions públiques.
        </p>
        <div className="flex flex-wrap gap-2 mt-4">
          <Link
            to="/comunitat/public"
            className="px-4 py-2 bg-tq-yellow text-tq-ink rounded-md text-sm font-semibold hover:bg-tq-yellow-deep hover:text-white transition-colors"
          >
            Feed públic
          </Link>
          <Link
            to="/compte/accedir?mode=registre"
            className="px-4 py-2 border border-white/20 text-white rounded-md text-sm font-semibold hover:bg-white/10 transition-colors"
          >
            Registra't
          </Link>
        </div>
      </div>
    </section>
  )
}

export default function ComunitatPage() {
  const { profile } = useAuth()
  const [filtre, setFiltre] = useState('')
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [visibleDirectori, setVisibleDirectori] = useState(false)

  useEffect(() => {
    if (!profile) return
    const params = new URLSearchParams({ filtre, page })
    api.get(`/comunitat/publicacions/?${params}`).then(setData).catch(() => setData(null))
  }, [profile, filtre, page])

  useEffect(() => {
    if (!profile) return
    api.get('/compte/dashboard/')
      .then(d => setVisibleDirectori(!!d.perfil?.visible_directori))
      .catch(() => {})
  }, [profile])

  if (!profile) return <AnonView />

  return (
    <section className="max-w-3xl mx-auto text-white">
      {/* Hero card — pitch + state-aware CTA */}
      <div className="bg-tq-ink/40 border border-white/10 rounded-lg p-4 md:p-5 mb-5">
        <p className="text-[10px] uppercase tracking-widest text-tq-yellow">
          Comunitat
        </p>
        <h1 className="text-xl md:text-2xl font-bold font-display mt-1 leading-tight">
          Un espai per a músics i amants de la música en català
        </h1>
        <p className="text-sm text-white/80 mt-2 leading-relaxed">
          Connecta, col·labora i comparteix projectes. Si fas música,
          activa el teu perfil al directori i fes saber que estàs obert
          a col·laboracions.
        </p>
        <div className="mt-3">
          <Link
            to={visibleDirectori ? '/comunitat/directori' : '/comunitat/perfil'}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-tq-yellow text-tq-ink text-xs font-semibold hover:bg-tq-yellow-deep hover:text-white transition-colors"
          >
            {visibleDirectori ? 'Explora el directori' : 'Activa el teu perfil'}
          </Link>
        </div>
      </div>

      <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
        <div>
          <h2 className="text-lg font-bold font-display">Feed</h2>
          <p className="text-xs text-white/60">
            Internes (només registrats) + públiques + les teves.
          </p>
        </div>
        <PillFilter value={filtre} onChange={v => { setPage(1); setFiltre(v) }} />
      </div>

      {!data && <p className="text-sm text-white/70">Carregant…</p>}
      {data?.results?.length === 0 && (
        <p className="text-sm text-white/60 italic">Cap publicació encara.</p>
      )}
      <ul className="space-y-3">
        {data?.results?.map(p => (
          <li key={p.pk}>
            <Link
              to={`/comunitat/${p.pk}`}
              className="block bg-white text-tq-ink rounded-lg p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <h3 className="font-bold font-display text-lg truncate">{p.titol}</h3>
                <div className="flex gap-1 shrink-0">
                  {p.visibilitat === 'publica' && (
                    <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-900">
                      Pública
                    </span>
                  )}
                  <EstatBadge estat={p.estat} />
                </div>
              </div>
              <p className="text-sm text-tq-ink/70 line-clamp-3 whitespace-pre-wrap">
                {stripMarkdown(p.cos)}
              </p>
              <p className="text-[11px] text-tq-ink/50 mt-2">
                per {p.autor.nom_public}
                {p.autor.is_staff && ' · staff'}
                {p.publicat_at && ` · ${formatDate(p.publicat_at)}`}
              </p>
            </Link>
          </li>
        ))}
      </ul>

      {data?.num_pages > 1 && (
        <nav className="flex items-center gap-3 mt-5 text-xs text-white/70" aria-label="Paginació">
          <button
            type="button"
            disabled={!data.has_previous}
            onClick={() => setPage(p => p - 1)}
            className="px-3 py-1.5 rounded border border-white/20 disabled:opacity-30 disabled:cursor-not-allowed font-semibold"
          >
            Anterior
          </button>
          <span className="tabular-nums">Pàg {data.page} de {data.num_pages}</span>
          <button
            type="button"
            disabled={!data.has_next}
            onClick={() => setPage(p => p + 1)}
            className="px-3 py-1.5 rounded border border-white/20 disabled:opacity-30 disabled:cursor-not-allowed font-semibold"
          >
            Següent
          </button>
        </nav>
      )}
    </section>
  )
}
