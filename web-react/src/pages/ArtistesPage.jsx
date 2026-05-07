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
import Alert from '../components/ui/Alert'
import useApi from '../hooks/useApi'
import {
  Section, TerritoriBadge,
  TERR_COLORS, TERRITORI_NOM,
} from '../components/editorial'
import FilterPanel from '../components/staff/FilterPanel'
import { Field, Select } from '../components/staff/StaffTable'
import { SeoHead } from '../lib/seoHead'

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
  genere: '',
  sort: 'nom',  // 'nom' | 'popularitat'
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

// Sprint S Bloc D pt 3 (2026-05-06): canonical genre choices mirror
// `Artista.GENERE_CANONICAL_CHOICES` on the backend, alphabetical.
// Kept in sync via the `/api/v1/artistes/?genere=<slug>` endpoint.
const GENERES = [
  ['',             'Tots els gèneres'],
  ['cantautor',    'Cantautor'],
  ['electronica',  'Electrònica'],
  ['experimental', 'Experimental'],
  ['folk',         'Folk'],
  ['hardcore',     'Hardcore'],
  ['hip-hop',      'Hip-hop'],
  ['indie',        'Indie'],
  ['infantil',     'Infantil'],
  ['jazz',         'Jazz'],
  ['metal',        'Metal'],
  ['pop',          'Pop'],
  ['punk',         'Punk'],
  ['reggae',       'Reggae'],
  ['rock',         'Rock'],
  ['ska',          'Ska'],
  ['urba',         'Urbà'],
]

const SORT_CHOICES = [
  ['nom',         'Per nom (A→Z)'],
  ['popularitat', 'Per popularitat'],
]

export default function ArtistesPage() {
  const [params, setParams] = useSearchParams()
  const q    = params.get('q') || ''
  const page = parseInt(params.get('page') || '1', 10)
  // `sort` lives inside the FilterPanel state too, but we read it
  // out separately so the fetch effect's deps stay flat.
  const applied = {
    territori: (params.get('territori') || '').toUpperCase(),
    comarca:   params.get('comarca')   || '',
    municipi:  params.get('municipi')  || '',
    amb_dones: params.get('amb_dones') || '',
    nou:       params.get('nou')       || '',
    al_top:    params.get('al_top')    || '',
    genere:    params.get('genere')    || '',
    sort:      params.get('sort')      || 'nom',
  }

  const [qDraft, setQDraft] = useState(q)
  useEffect(() => { setQDraft(q) }, [q])

  // Build the path so useApi keys cancellation+refetch off it. No
  // need to enumerate filters as deps — they're encoded into `path`.
  const _qs = new URLSearchParams()
  if (q) _qs.set('q', q)
  for (const [k, v] of Object.entries(applied)) {
    if (v) _qs.set(k, v)
  }
  if (page > 1) _qs.set('page', String(page))
  // `sort=nom` is the default — keep the URL clean.
  if (applied.sort && applied.sort !== 'nom') _qs.set('sort', applied.sort)
  _qs.set('per_page', '40')
  const { data, error, loading } = useApi(`/artistes/?${_qs}`)

  // Apply a filter set (from FilterPanel) into URL params, dropping
  // empty values + the default sort and resetting pagination.
  const applyFilters = (next) => {
    const out = new URLSearchParams()
    if (q) out.set('q', q)
    for (const [k, v] of Object.entries(next)) {
      if (!v) continue
      // `sort=nom` is the default — keep the URL clean.
      if (k === 'sort' && v === 'nom') continue
      out.set(k, v)
    }
    setParams(out)
    // K1 analytics: which filter dimensions does the audience use
    // most? `directori_filter` dim1 is the first non-empty filter
    // key (territori/comarca/municipi/amb_dones/nou/al_top). One
    // event per apply call, not per dimension.
    const firstKey = Object.entries(next).find(([, v]) => v)?.[0]
    if (firstKey) {
      import('../lib/analytics').then(({ trackEvent }) =>
        trackEvent('directori_filter', firstKey)
      )
    }
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
    // K1 analytics: count non-empty searches. dim1 is the scope so the
    // dashboard can compare which list-page surface gets searched most.
    if (qDraft.trim()) {
      import('../lib/analytics').then(({ trackEvent }) =>
        trackEvent('search_query', 'artistes')
      )
    }
  }

  return (
    <div className="space-y-0">
      <SeoHead entity="artistes" />
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

      {/* Multi-select via toggleable chips. State stored as a
          comma-separated string in `pending.genere` so the URL
          serialisation is trivial: `?genere=punk,ska,hardcore`.
          Mobile-friendly (single-tap to toggle, no modal). */}
      <Field label="Gèneres">
        <div className="flex flex-wrap gap-1.5 mt-1">
          {GENERES.filter(([v]) => v).map(([v, label]) => {
            const selected = (pending.genere || '')
              .split(',')
              .map(s => s.trim())
              .filter(Boolean)
            const isOn = selected.includes(v)
            return (
              <button
                key={v}
                type="button"
                onClick={() => {
                  const next = isOn
                    ? selected.filter(x => x !== v)
                    : [...selected, v]
                  setPending({ genere: next.join(',') })
                }}
                className={
                  'px-2.5 py-1 text-xs rounded-full border transition-colors ' +
                  (isOn
                    ? 'bg-tq-yellow text-tq-ink border-tq-yellow font-semibold'
                    : 'bg-white text-tq-ink/70 border-tq-ink/15 hover:border-tq-ink/40')
                }
                aria-pressed={isOn}
              >
                {label}
              </button>
            )
          })}
        </div>
      </Field>

      <Field label="Ordenar per">
        <Select
          value={pending.sort || 'nom'}
          onChange={e => setPending({ sort: e.target.value })}
        >
          {SORT_CHOICES.map(([v, label]) => (
            <option key={v} value={v}>{label}</option>
          ))}
        </Select>
      </Field>

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
