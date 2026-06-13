/**
 * ArtistesPage — /artistes (redisseny web).
 *
 * Dark hero with the Anton title + live search + sort pills + territory
 * quick-pills, plus the advanced FilterPanel (comarca/municipi/genere/
 * booleans). Grid of glass tiles below. House vocabulary.
 *
 * URL contract UNCHANGED: q, territori, comarca, municipi, amb_dones,
 * nou, al_top, genere, sort, page. Real /artistes/ data + pagination.
 */
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import useApi from '../hooks/useApi'
import { api } from '../lib/api'
import FilterPanel from '../components/staff/FilterPanel'
import { Field, Select } from '../components/staff/StaffTable'
import { Band, Glow, Glass, Kicker, Crit, TerrLogo, RdCover } from '../components/rd/primitives'
import { terr, shade } from '../components/rd/terr'
import { SeoHead } from '../lib/seoHead'
import { deezerImg } from '../lib/img'

/* Panel territori list (advanced filter). */
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

/* Quick territory pills in the hero (Tots + the directori territories). */
const TERR_QUICK = ['', 'CAT', 'VAL', 'BAL', 'AND', 'CNO', 'FRA', 'ALG', 'ALT']

const FILTER_DEFAULTS = {
  territori: '', comarca: '', municipi: '',
  amb_dones: '', nou: '', al_top: '', genere: '', sort: 'nom',
}

function initialsFor(nom) {
  if (!nom) return '?'
  const words = nom.split(/\s+/).filter(Boolean)
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[words.length - 1][0]).toUpperCase()
}

function ArtistaCard({ a }) {
  const code = a.territoris?.[0]
  const t = code ? terr(code) : null
  const deep = t ? t.deep : '#33373d'
  return (
    <Link to={`/artista/${a.slug}`} className="rd-art-card rd-glass group">
      <div
        className="rd-art-tile"
        style={a.imatge_url ? undefined : { background: `linear-gradient(155deg, ${shade(deep, 0.14)} 0%, ${shade(deep, -0.28)} 100%)` }}
      >
        {a.imatge_url ? (
          <img src={deezerImg(a.imatge_url, 500)} alt="" loading="lazy" className="w-full h-full object-cover" />
        ) : (
          <span className="rd-art-ini" style={{ color: t ? t.accent : '#9aa0a6' }} aria-hidden="true">
            {initialsFor(a.nom)}
          </span>
        )}
        {code && <span className="rd-art-chip"><TerrLogo code={code} className="h-[17px] w-[17px]" /></span>}
      </div>
      <div className="rd-art-meta">
        <p className="rd-art-name">{a.nom}</p>
        <p className="rd-art-stats">{a.localitat?.nom || 'Sense localitat'}{a.genere ? ` · ${a.genere}` : ''}</p>
        {t && <span className="rd-art-terrname" style={{ color: t.accent }}>{t.nom}</span>}
      </div>
    </Link>
  )
}

/* Canonical genre choices (mirror the /artistes/?genere=<slug> endpoint). */
const GENERES = [
  ['', 'Tots els gèneres'], ['cantautor', 'Cantautor'], ['electronica', 'Electrònica'],
  ['experimental', 'Experimental'], ['folk', 'Folk'], ['hardcore', 'Hardcore'],
  ['hip-hop', 'Hip-hop'], ['indie', 'Indie'], ['infantil', 'Infantil'], ['jazz', 'Jazz'],
  ['metal', 'Metal'], ['pop', 'Pop'], ['punk', 'Punk'], ['reggae', 'Reggae'],
  ['rock', 'Rock'], ['ska', 'Ska'], ['urba', 'Urbà'],
]
const SORT_CHOICES = [
  ['nom', 'Per nom (A→Z)'],
  ['popularitat', 'Per popularitat'],
]

export default function ArtistesPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const page = parseInt(params.get('page') || '1', 10)
  const applied = {
    territori: (params.get('territori') || '').toUpperCase(),
    comarca: params.get('comarca') || '',
    municipi: params.get('municipi') || '',
    amb_dones: params.get('amb_dones') || '',
    nou: params.get('nou') || '',
    al_top: params.get('al_top') || '',
    genere: params.get('genere') || '',
    sort: params.get('sort') || 'nom',
  }

  const [qDraft, setQDraft] = useState(q)
  useEffect(() => { setQDraft(q) }, [q])

  const _qs = new URLSearchParams()
  if (q) _qs.set('q', q)
  for (const [k, v] of Object.entries(applied)) { if (v) _qs.set(k, v) }
  if (page > 1) _qs.set('page', String(page))
  if (applied.sort && applied.sort !== 'nom') _qs.set('sort', applied.sort)
  _qs.set('per_page', '40')
  const { data, error, loading, reload } = useApi(`/artistes/?${_qs}`)

  const applyFilters = (next) => {
    const out = new URLSearchParams()
    if (q) out.set('q', q)
    for (const [k, v] of Object.entries(next)) {
      if (!v) continue
      if (k === 'sort' && v === 'nom') continue
      out.set(k, v)
    }
    setParams(out)
    const firstKey = Object.entries(next).find(([, v]) => v)?.[0]
    if (firstKey) {
      import('../lib/analytics').then(({ trackEvent }) => trackEvent('directori_filter', firstKey))
    }
  }

  const submitSearch = () => {
    const out = new URLSearchParams(params)
    if (qDraft) out.set('q', qDraft); else out.delete('q')
    out.delete('page'); out.delete('comarca'); out.delete('municipi')
    setParams(out)
    if (qDraft.trim()) {
      import('../lib/analytics').then(({ trackEvent }) => trackEvent('search_query', 'artistes'))
    }
  }

  const selectTerritori = (code) => applyFilters({ ...applied, territori: code, comarca: '', municipi: '' })
  const selectSort = (v) => applyFilters({ ...applied, sort: v })

  const goPage = (n) => { const next = new URLSearchParams(params); next.set('page', String(n)); setParams(next) }

  return (
    <>
      <SeoHead entity="artistes" />
      <Band tone="top-hero">
        <Glow variant="a" />
        <Kicker className="block mb-2">el directori de músics en català</Kicker>
        <Crit as="h1" className="rd-top-h1">ELS <span style={{ color: 'var(--color-tq-yellow)' }}>ARTISTES</span></Crit>

        <div className="rd-art-tools">
          <form onSubmit={e => { e.preventDefault(); submitSearch() }} role="search" className="contents">
            <label htmlFor="art-q" className="sr-only">Cerca un artista pel nom</label>
            <input
              id="art-q" type="search" value={qDraft} onChange={e => setQDraft(e.target.value)}
              placeholder="Busca un artista…" className="rd-art-search"
            />
          </form>
          <div className="flex gap-2">
            {SORT_CHOICES.map(([v]) => (
              <button key={v} type="button" onClick={() => selectSort(v)}
                className={`rd-pill${applied.sort === v ? ' rd-pill-on' : ''}`}
                style={applied.sort === v ? { background: 'var(--color-tq-yellow)', color: '#0a0a0a' } : undefined}>
                {v === 'nom' ? 'A → Z' : 'Popularitat'}
              </button>
            ))}
            <FilterPanel applied={applied} defaults={FILTER_DEFAULTS} onApply={applyFilters}>
              {(p, setP) => <ArtistesFilters pending={p} setPending={setP} />}
            </FilterPanel>
          </div>
        </div>

        <nav className="rd-terr-pills" aria-label="Filtra per territori">
          {TERR_QUICK.map(code => {
            const on = code === applied.territori
            const label = code === '' ? 'Tots' : terr(code).nom
            return (
              <button key={code || 'tots'} type="button" onClick={() => selectTerritori(code)}
                className={`rd-pill${on ? ' rd-pill-on' : ''}`}
                style={on ? { background: 'var(--color-tq-yellow)', color: '#0a0a0a' } : undefined}>
                {label}
              </button>
            )
          })}
        </nav>
      </Band>

      <Band tone="ink2">
        {error ? (
          <Glass className="p-6 text-center">
            <p className="text-white/70 text-sm">No s'han pogut carregar els artistes.</p>
            <button type="button" onClick={reload} className="rd-btn rd-btn--ghost mt-3">Reintentar</button>
          </Glass>
        ) : loading ? (
          <div className="rd-art-grid">
            {Array.from({ length: 12 }).map((_, i) => <div key={i} style={{ aspectRatio: '4/5', borderRadius: 18, background: 'rgba(255,255,255,0.06)' }} />)}
          </div>
        ) : (data?.results || []).length === 0 ? (
          <p className="rd-empty">Cap artista coincideix amb la cerca. Prova de netejar els filtres.</p>
        ) : (
          <>
            <p className="rd-art-count">
              {data.total?.toLocaleString('ca-ES')} {data.total === 1 ? 'artista' : 'artistes'}
            </p>
            <ul className="rd-art-grid">
              {data.results.map(a => <li key={a.slug}><ArtistaCard a={a} /></li>)}
            </ul>
            {data.num_pages > 1 && (
              <nav className="rd-pager" aria-label="Paginació">
                <button type="button" disabled={!data.has_previous} onClick={() => goPage(page - 1)} className="rd-btn rd-btn--ghost">Anterior</button>
                <span className="text-sm text-white/60 tabular-nums">Pàgina {data.page} de {data.num_pages}</span>
                <button type="button" disabled={!data.has_next} onClick={() => goPage(page + 1)} className="rd-btn rd-btn--ghost">Següent</button>
              </nav>
            )}
          </>
        )}
      </Band>
    </>
  )
}

/* ── Advanced filters (renders inside the FilterPanel popover) ─────── */
/* The cascade clears its dependent list synchronously when the parent
   selection empties — a deliberate fetch-effect pattern, so the
   set-state-in-effect hint is disabled for this component. */
/* eslint-disable react-hooks/set-state-in-effect */
function ArtistesFilters({ pending, setPending }) {
  const [comarques, setComarques] = useState([])
  const [municipis, setMunicipis] = useState([])

  useEffect(() => {
    if (!pending.territori) { setComarques([]); return }
    api.get(`/localitzacio/comarques/?territori=${pending.territori}`).then(setComarques).catch(() => setComarques([]))
  }, [pending.territori])

  useEffect(() => {
    if (!pending.comarca) { setMunicipis([]); return }
    api.get(`/localitzacio/municipis/?comarca=${encodeURIComponent(pending.comarca)}`).then(setMunicipis).catch(() => setMunicipis([]))
  }, [pending.comarca])

  return (
    <>
      <Field label="Territori">
        <Select value={pending.territori} onChange={e => setPending({ territori: e.target.value, comarca: '', municipi: '' })}>
          {TERRITORIS.map(([c, l]) => <option key={c || 'tots'} value={c}>{l}</option>)}
        </Select>
      </Field>
      {pending.territori && (
        <Field label="Comarca">
          <Select value={pending.comarca} onChange={e => setPending({ comarca: e.target.value, municipi: '' })} disabled={comarques.length === 0}>
            <option value="">Totes les comarques</option>
            {comarques.map(c => <option key={c} value={c}>{c}</option>)}
          </Select>
        </Field>
      )}
      {pending.comarca && (
        <Field label="Municipi">
          <Select value={pending.municipi} onChange={e => setPending({ municipi: e.target.value })} disabled={municipis.length === 0}>
            <option value="">Tots els municipis</option>
            {municipis.map(m => <option key={m.pk} value={m.nom}>{m.nom}</option>)}
          </Select>
        </Field>
      )}
      <Field label="Gèneres">
        <div className="flex flex-wrap gap-1.5 mt-1">
          {GENERES.filter(([v]) => v).map(([v, label]) => {
            const selected = (pending.genere || '').split(',').map(s => s.trim()).filter(Boolean)
            const isOn = selected.includes(v)
            return (
              <button key={v} type="button"
                onClick={() => setPending({ genere: (isOn ? selected.filter(x => x !== v) : [...selected, v]).join(',') })}
                className={'px-2.5 py-1 text-xs rounded-full border transition-colors ' + (isOn ? 'bg-tq-yellow text-tq-ink border-tq-yellow font-semibold' : 'bg-white text-tq-ink/70 border-tq-ink/15 hover:border-tq-ink/40')}
                aria-pressed={isOn}>
                {label}
              </button>
            )
          })}
        </div>
      </Field>
      <Field label="Ordenar per">
        <Select value={pending.sort || 'nom'} onChange={e => setPending({ sort: e.target.value })}>
          {SORT_CHOICES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </Select>
      </Field>
      <div className="border-t border-black/10 pt-3 mt-1 flex flex-col gap-2">
        <label className="flex items-center gap-2 text-xs font-semibold text-tq-ink/80">
          <input type="checkbox" checked={pending.amb_dones === '1'} onChange={e => setPending({ amb_dones: e.target.checked ? '1' : '' })} /> Amb dones
        </label>
        <label className="flex items-center gap-2 text-xs font-semibold text-tq-ink/80">
          <input type="checkbox" checked={pending.nou === '1'} onChange={e => setPending({ nou: e.target.checked ? '1' : '' })} /> Llançaments del darrer any
        </label>
        <label className="flex items-center gap-2 text-xs font-semibold text-tq-ink/80">
          <input type="checkbox" checked={pending.al_top === '1'} onChange={e => setPending({ al_top: e.target.checked ? '1' : '' })} /> Amb cançons al top
        </label>
      </div>
    </>
  )
}
