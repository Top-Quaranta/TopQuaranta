/**
 * ArtistesPage — /artistes
 *
 * Editorial layout (Sprint J/J ter): hero ink band with title +
 * inline search + a staff-style FilterPanel button (cascading
 * territori/comarca/municipi + booleans). Results live in a white
 * band as a 4-col cover grid. Same shared editorial primitives the
 * rest of the public SPA uses.
 *
 * Query params mirror the API 1:1 so URLs stay shareable:
 *   q, territori, comarca, municipi, amb_dones, nou, al_top, page.
 */
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import Alert from '../components/ui/Alert'
import {
  Section, TerritoriBadge,
  TERR_COLORS, TERRITORI_NOM,
} from '../components/editorial'
import FilterPanel from '../components/staff/FilterPanel'
import { Field, Select } from '../components/staff/StaffTable'

const TERRITORIS = [
  ['',    'Tots els territoris'],
  ['AND', 'Andorra'],
  ['CAT', 'Catalunya'],
  ['CNO', 'Catalunya del Nord'],
  ['FRA', 'Franja de Ponent'],
  ['BAL', 'Illes Balears'],
  ['ALG', "L'Alguer"],
  ['VAL', 'País Valencià'],
]

const FILTER_DEFAULTS = {
  territori: '',
  comarca: '',
  municipi: '',
  amb_dones: '',  // '1' or ''
  nou: '',
  al_top: '',
}

function initialsFor(nom) {
  if (!nom) return '?'
  const words = nom.split(/\s+/).filter(Boolean)
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[words.length - 1][0]).toUpperCase()
}

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
          <img src={a.imatge_url} alt="" className="w-full h-full object-cover" loading="lazy" />
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

export default function ArtistesPage() {
  const [params, setParams] = useSearchParams()
  const q    = params.get('q') || ''
  const page = parseInt(params.get('page') || '1', 10)
  const applied = {
    territori: (params.get('territori') || '').toUpperCase(),
    comarca:   params.get('comarca')   || '',
    municipi:  params.get('municipi')  || '',
    amb_dones: params.get('amb_dones') || '',
    nou:       params.get('nou')       || '',
    al_top:    params.get('al_top')    || '',
  }

  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [qDraft, setQDraft] = useState(q)

  useEffect(() => { setQDraft(q) }, [q])

  // Fetch results whenever the URL state changes.
  useEffect(() => {
    setLoading(true)
    setError(null)
    const qs = new URLSearchParams()
    if (q) qs.set('q', q)
    for (const [k, v] of Object.entries(applied)) {
      if (v) qs.set(k, v)
    }
    if (page > 1) qs.set('page', String(page))
    qs.set('per_page', '40')
    api.get(`/artistes/?${qs}`)
      .then(setData)
      .catch(e => setError(e.message || 'Error'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, applied.territori, applied.comarca, applied.municipi,
      applied.amb_dones, applied.nou, applied.al_top, page])

  // Apply a filter set (from FilterPanel) into URL params, dropping
  // empty values and resetting pagination.
  const applyFilters = (next) => {
    const out = new URLSearchParams()
    if (q) out.set('q', q)
    for (const [k, v] of Object.entries(next)) {
      if (v) out.set(k, v)
    }
    setParams(out)
  }

  const submitSearch = () => {
    const out = new URLSearchParams(params)
    if (qDraft) out.set('q', qDraft); else out.delete('q')
    out.delete('page')
    // Clear cascading geo filters when search changes — they were
    // chosen against the previous result set.
    out.delete('comarca')
    out.delete('municipi')
    setParams(out)
  }

  return (
    <div className="space-y-0">
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

        {/* Search inline + filter button. Search lives outside the
            panel because it's the most common entry point and benefits
            from being one keystroke away. */}
        <form
          onSubmit={e => { e.preventDefault(); submitSearch() }}
          className="flex flex-wrap gap-2 mt-5 items-center"
          role="search"
        >
          <label htmlFor="art-q" className="sr-only">Cercar artistes pel nom</label>
          <input
            id="art-q"
            type="search"
            value={qDraft}
            onChange={e => setQDraft(e.target.value)}
            placeholder="Cerca per nom…"
            className="flex-1 min-w-[12rem] px-3 py-1.5 bg-white/5 border border-white/15 rounded-md text-sm text-white placeholder-white/40 focus:outline-none focus:border-tq-yellow"
          />
          <button
            type="submit"
            className="px-4 py-1.5 bg-tq-yellow text-tq-ink rounded-md text-sm font-semibold hover:bg-tq-yellow-deep hover:text-white transition-colors"
          >
            Cercar
          </button>
          <FilterPanel
            applied={applied}
            defaults={FILTER_DEFAULTS}
            onApply={applyFilters}
          >
            {(p, setP) => <ArtistesFilters pending={p} setPending={setP} />}
          </FilterPanel>
        </form>
      </Section>

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

/* ── Filter panel body (renders inside the staff FilterPanel) ─────── */

function ArtistesFilters({ pending, setPending }) {
  const [comarques, setComarques] = useState([])
  const [municipis, setMunicipis] = useState([])

  // Load comarques whenever a territori is chosen in the panel.
  useEffect(() => {
    if (!pending.territori) { setComarques([]); return }
    api.get(`/localitzacio/comarques/?territori=${pending.territori}`)
      .then(setComarques)
      .catch(() => setComarques([]))
  }, [pending.territori])

  useEffect(() => {
    if (!pending.comarca) { setMunicipis([]); return }
    api.get(`/localitzacio/municipis/?comarca=${encodeURIComponent(pending.comarca)}`)
      .then(setMunicipis)
      .catch(() => setMunicipis([]))
  }, [pending.comarca])

  return (
    <>
      <Field label="Territori">
        <Select
          value={pending.territori}
          onChange={e => setPending({
            territori: e.target.value, comarca: '', municipi: '',
          })}
        >
          {TERRITORIS.map(([c, l]) => (
            <option key={c || 'tots'} value={c}>{l}</option>
          ))}
        </Select>
      </Field>

      {pending.territori && (
        <Field label="Comarca">
          <Select
            value={pending.comarca}
            onChange={e => setPending({ comarca: e.target.value, municipi: '' })}
            disabled={comarques.length === 0}
          >
            <option value="">Totes les comarques</option>
            {comarques.map(c => <option key={c} value={c}>{c}</option>)}
          </Select>
        </Field>
      )}

      {pending.comarca && (
        <Field label="Municipi">
          <Select
            value={pending.municipi}
            onChange={e => setPending({ municipi: e.target.value })}
            disabled={municipis.length === 0}
          >
            <option value="">Tots els municipis</option>
            {municipis.map(m => <option key={m.pk} value={m.nom}>{m.nom}</option>)}
          </Select>
        </Field>
      )}

      <div className="border-t border-black/10 pt-3 mt-1 flex flex-col gap-2">
        <label className="flex items-center gap-2 text-xs font-semibold text-tq-ink/80">
          <input
            type="checkbox"
            checked={pending.amb_dones === '1'}
            onChange={e => setPending({ amb_dones: e.target.checked ? '1' : '' })}
          />
          Amb dones
        </label>
        <label className="flex items-center gap-2 text-xs font-semibold text-tq-ink/80">
          <input
            type="checkbox"
            checked={pending.nou === '1'}
            onChange={e => setPending({ nou: e.target.checked ? '1' : '' })}
          />
          Llançaments del darrer any
        </label>
        <label className="flex items-center gap-2 text-xs font-semibold text-tq-ink/80">
          <input
            type="checkbox"
            checked={pending.al_top === '1'}
            onChange={e => setPending({ al_top: e.target.checked ? '1' : '' })}
          />
          Amb cançons al top
        </label>
      </div>
    </>
  )
}
