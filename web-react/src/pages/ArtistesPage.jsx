/**
 * ArtistesPage — /artistes
 *
 * Editorial redesign (Sprint J): hero ink band with title + filters
 * row, results in a white band with the same square-cover grid we
 * use everywhere else. Filters use the same compact pill vocabulary
 * as the rest of the SPA.
 *
 * Query params mirror the API 1:1 so links stay shareable:
 *   q, territori, comarca, municipi, amb_dones, nou, al_top, page.
 */
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import Alert from '../components/ui/Alert'
import {
  Section, SectionHeader, TerritoriBadge,
  TERR_COLORS, TERRITORI_NOM,
} from '../components/editorial'

/* Pill order — same shape as TopPage. "Tots" first as the null filter. */
const TERRITORIS = [
  { codi: '',    nom: 'Tots' },
  { codi: 'AND', nom: 'Andorra' },
  { codi: 'CAT', nom: 'Catalunya' },
  { codi: 'CNO', nom: 'Catalunya del Nord' },
  { codi: 'FRA', nom: 'Franja de Ponent' },
  { codi: 'BAL', nom: 'Illes Balears' },
  { codi: 'ALG', nom: "L'Alguer" },
  { codi: 'VAL', nom: 'País Valencià' },
]

function initialsFor(nom) {
  if (!nom) return '?'
  const words = nom.split(/\s+/).filter(Boolean)
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[words.length - 1][0]).toUpperCase()
}

/* ── Card: square cover above name + meta. Same dimensions as the
 * HomePage album/discovery tiles so the visual rhythm carries over. */
function ArtistaCard({ a }) {
  const territori = a.territoris?.[0]
  const color = TERR_COLORS[territori] || TERR_COLORS.ALT
  return (
    <Link
      to={`/artista/${a.slug}`}
      className="group block bg-white text-tq-ink rounded-lg overflow-hidden shadow-sm hover:shadow-lg transition-all hover:-translate-y-0.5"
    >
      <div className="aspect-square relative" style={{ backgroundColor: 'var(--mm-color-gray-100)' }}>
        {a.imatge_url ? (
          <img
            src={a.imatge_url}
            alt=""
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div
            className="w-full h-full flex items-center justify-center font-display font-bold text-4xl text-white"
            style={{ backgroundColor: color }}
            aria-hidden="true"
          >
            {initialsFor(a.nom)}
          </div>
        )}
      </div>
      <div className="p-3">
        <p className="font-semibold truncate">{a.nom}</p>
        <p className="text-xs text-tq-ink/60 truncate mt-0.5">
          {a.localitat?.nom || 'Sense localitat'}
        </p>
        <div className="flex flex-wrap gap-1 mt-1 text-[11px]">
          {a.territoris?.slice(0, 2).map(t => (
            <span key={t} className="inline-flex items-center gap-1 font-semibold"
                  style={{ color: TERR_COLORS[t] }}>
              <TerritoriBadge codi={t} className="h-3 w-3" />
              {TERRITORI_NOM[t] || t}
            </span>
          ))}
          {a.genere && <span className="text-tq-ink/40 truncate">· {a.genere}</span>}
        </div>
      </div>
    </Link>
  )
}

/* ── Filter pill (radio-style) — same look as TopPage territori pills. */
function PillButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        'px-3 py-1 rounded-full text-xs font-semibold transition-colors ' +
        (active
          ? 'bg-tq-yellow text-tq-ink'
          : 'bg-white/10 text-white hover:bg-white/20')
      }
    >
      {children}
    </button>
  )
}

/* Toggle pill (checkbox) — visually identical to PillButton but with
 * a sr-only checkbox so keyboard / screen-reader users get a real
 * toggle semantic. */
function FilterCheckbox({ checked, onChange, children, id }) {
  return (
    <label
      htmlFor={id}
      className={
        'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold cursor-pointer transition-colors ' +
        (checked
          ? 'bg-tq-yellow text-tq-ink'
          : 'bg-white/10 text-white hover:bg-white/20')
      }
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        className="sr-only"
      />
      {children}
    </label>
  )
}

export default function ArtistesPage() {
  const [params, setParams] = useSearchParams()
  const q         = params.get('q')         || ''
  const territori = (params.get('territori') || '').toUpperCase()
  const comarca   = params.get('comarca')   || ''
  const municipi  = params.get('municipi')  || ''
  const ambDones  = params.get('amb_dones') === '1'
  const nou       = params.get('nou')       === '1'
  const alTop     = params.get('al_top')    === '1'
  const page      = parseInt(params.get('page') || '1', 10)

  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [qDraft, setQDraft] = useState(q)

  // Cascading reference data — comarques depend on territori, municipis on comarca.
  const [comarques, setComarques] = useState([])
  const [municipis, setMunicipis] = useState([])

  useEffect(() => { setQDraft(q) }, [q])

  useEffect(() => {
    if (!territori) { setComarques([]); return }
    api.get(`/localitzacio/comarques/?territori=${territori}`)
      .then(setComarques)
      .catch(() => setComarques([]))
  }, [territori])

  useEffect(() => {
    if (!comarca) { setMunicipis([]); return }
    api.get(`/localitzacio/municipis/?comarca=${encodeURIComponent(comarca)}`)
      .then(setMunicipis)
      .catch(() => setMunicipis([]))
  }, [comarca])

  useEffect(() => {
    setLoading(true)
    setError(null)
    const qs = new URLSearchParams()
    if (q) qs.set('q', q)
    if (territori) qs.set('territori', territori)
    if (comarca) qs.set('comarca', comarca)
    if (municipi) qs.set('municipi', municipi)
    if (ambDones) qs.set('amb_dones', '1')
    if (nou) qs.set('nou', '1')
    if (alTop) qs.set('al_top', '1')
    if (page > 1) qs.set('page', String(page))
    qs.set('per_page', '40')
    api.get(`/artistes/?${qs}`)
      .then(setData)
      .catch(e => setError(e.message || 'Error'))
      .finally(() => setLoading(false))
  }, [q, territori, comarca, municipi, ambDones, nou, alTop, page])

  const setParam = (changes) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      if (v === '' || v === false || v == null) next.delete(k)
      else next.set(k, v === true ? '1' : String(v))
    }
    next.delete('page')
    setParams(next)
  }

  const hasFilters = q || territori || comarca || municipi || ambDones || nou || alTop

  return (
    <div className="space-y-0">
      {/* ── Hero band: title, count, filters ──────────────────────── */}
      <Section tone="ink">
        <p className="text-[10px] uppercase tracking-widest text-tq-yellow">
          Directori
        </p>
        <h1 className="text-3xl md:text-5xl font-bold font-display mt-1.5 leading-tight">
          Artistes
        </h1>
        <p className="text-sm text-white/70 mt-2">
          {data
            ? `${data.total.toLocaleString('ca-ES')} ${data.total === 1 ? 'artista' : 'artistes'} al sistema`
            : 'Carregant…'}
        </p>

        {/* Filters block — search + territori pills + booleans */}
        <div className="mt-6 space-y-3">
          {/* Search */}
          <form
            onSubmit={e => { e.preventDefault(); setParam({ q: qDraft, comarca: '', municipi: '' }) }}
            className="flex gap-2"
            role="search"
          >
            <label htmlFor="art-q" className="sr-only">Cercar artistes pel nom</label>
            <input
              id="art-q"
              type="search"
              value={qDraft}
              onChange={e => setQDraft(e.target.value)}
              placeholder="Cerca per nom…"
              className="flex-1 min-w-0 px-3 py-1.5 bg-white/5 border border-white/15 rounded-md text-sm text-white placeholder-white/40 focus:outline-none focus:border-tq-yellow"
            />
            <button
              type="submit"
              className="px-4 py-1.5 bg-tq-yellow text-tq-ink rounded-md text-sm font-semibold whitespace-nowrap hover:bg-tq-yellow-deep hover:text-white transition-colors"
            >
              Cercar
            </button>
          </form>

          {/* Territori pills */}
          <nav className="flex flex-wrap gap-1.5" aria-label="Filtre per territori">
            {TERRITORIS.map(t => (
              <PillButton
                key={t.codi || 'tots'}
                active={t.codi === territori}
                onClick={() => setParam({ territori: t.codi, comarca: '', municipi: '' })}
              >
                {t.nom}
              </PillButton>
            ))}
          </nav>

          {/* Cascading dropdowns — only when a territori is picked */}
          {territori && (
            <div className="flex flex-wrap gap-2">
              <label htmlFor="art-comarca" className="sr-only">Comarca</label>
              <select
                id="art-comarca"
                value={comarca}
                onChange={e => setParam({ comarca: e.target.value, municipi: '' })}
                disabled={comarques.length === 0}
                className="px-3 py-1.5 bg-white/5 border border-white/15 rounded-md text-sm text-white focus:outline-none focus:border-tq-yellow disabled:opacity-40"
              >
                <option value="" className="text-tq-ink">Comarca: Totes</option>
                {comarques.map(c => (
                  <option key={c} value={c} className="text-tq-ink">{c}</option>
                ))}
              </select>

              {comarca && (
                <>
                  <label htmlFor="art-municipi" className="sr-only">Municipi</label>
                  <select
                    id="art-municipi"
                    value={municipi}
                    onChange={e => setParam({ municipi: e.target.value })}
                    disabled={municipis.length === 0}
                    className="px-3 py-1.5 bg-white/5 border border-white/15 rounded-md text-sm text-white focus:outline-none focus:border-tq-yellow disabled:opacity-40"
                  >
                    <option value="" className="text-tq-ink">Municipi: Tots</option>
                    {municipis.map(m => (
                      <option key={m.pk} value={m.nom} className="text-tq-ink">{m.nom}</option>
                    ))}
                  </select>
                </>
              )}
            </div>
          )}

          {/* Booleans */}
          <div className="flex flex-wrap gap-2 items-center">
            <FilterCheckbox id="f-dones" checked={ambDones} onChange={v => setParam({ amb_dones: v })}>
              Amb dones
            </FilterCheckbox>
            <FilterCheckbox id="f-nou" checked={nou} onChange={v => setParam({ nou: v })}>
              Llançaments del darrer any
            </FilterCheckbox>
            <FilterCheckbox id="f-top" checked={alTop} onChange={v => setParam({ al_top: v })}>
              Amb cançons al top
            </FilterCheckbox>
            {hasFilters && (
              <button
                type="button"
                onClick={() => setParams({})}
                className="text-xs text-tq-yellow hover:underline ml-auto font-semibold"
              >
                Netejar filtres
              </button>
            )}
          </div>
        </div>
      </Section>

      {/* ── Results band ─────────────────────────────────────────── */}
      <Section tone="white">
        {error && <Alert tone="danger">{error}</Alert>}

        {loading && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="aspect-[4/5] bg-tq-ink/5 rounded-lg animate-pulse" />
            ))}
          </div>
        )}

        {!loading && !error && data?.results?.length === 0 && (
          <p className="text-tq-ink/60 text-sm italic">
            Cap artista amb aquests filtres. Prova de netejar-los.
          </p>
        )}

        {!loading && !error && data?.results?.length > 0 && (
          <>
            <ul className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {data.results.map(a => (
                <li key={a.slug}><ArtistaCard a={a} /></li>
              ))}
            </ul>

            {data.num_pages > 1 && (
              <nav
                className="flex items-center justify-center gap-3 mt-8"
                aria-label="Paginació"
              >
                <button type="button"
                  disabled={!data.has_previous}
                  onClick={() => {
                    const next = new URLSearchParams(params)
                    next.set('page', String(page - 1))
                    setParams(next)
                  }}
                  className="px-3 py-1.5 bg-tq-ink text-white rounded-md text-sm font-semibold disabled:opacity-30 disabled:cursor-not-allowed hover:bg-tq-ink/90 transition-colors">
                  Anterior
                </button>
                <span className="text-xs text-tq-ink/60 tabular-nums">
                  Pàgina {data.page} de {data.num_pages}
                </span>
                <button type="button"
                  disabled={!data.has_next}
                  onClick={() => {
                    const next = new URLSearchParams(params)
                    next.set('page', String(page + 1))
                    setParams(next)
                  }}
                  className="px-3 py-1.5 bg-tq-ink text-white rounded-md text-sm font-semibold disabled:opacity-30 disabled:cursor-not-allowed hover:bg-tq-ink/90 transition-colors">
                  Següent
                </button>
              </nav>
            )}
          </>
        )}
      </Section>
    </div>
  )
}
