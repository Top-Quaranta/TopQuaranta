/**
 * TopPage — /top
 *
 * Editorial redesign (Sprint J): a hero band with the big title +
 * territori + week navigator, a 1–40 list in two columns, and
 * footer credit pointing at /com-funciona for the methodology.
 *
 * Reads from the URL: ?t=<territori-code>, ?s=<YYYY-MM-DD setmana>.
 * Both default to the latest stored week of PPCC ("Global").
 *
 * Backend gives us `prev_setmana` / `next_setmana` so the navigator
 * can disable the arrows at the boundaries — a visitor never lands
 * on an empty week.
 */
import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { api } from '../lib/api'
import Alert from '../components/ui/Alert'
import { cancoUrl } from '../lib/urls'
import MmIcon from '../components/MmIcon'
import { TrendCue, TERRITORI_NOM } from '../components/editorial'
import { fmtDataLlarga } from '../lib/format'
import { SeoHead } from '../lib/seoHead'

/* Pill order — alphabetical by user-facing name, "Global" first.
 * "Altres" stays at the end. */
const TERRITORIS = [
  { codi: 'PPCC', nom: 'Global' },
  { codi: 'AND',  nom: 'Andorra' },
  { codi: 'CAT',  nom: 'Catalunya' },
  { codi: 'CNO',  nom: 'Catalunya del Nord' },
  { codi: 'FRA',  nom: 'Franja de Ponent' },
  { codi: 'BAL',  nom: 'Illes Balears' },
  { codi: 'ALG',  nom: "L'Alguer" },
  { codi: 'VAL',  nom: 'País Valencià' },
  { codi: 'ALT',  nom: 'Altres' },
]

/* Rolling Saturday from a Monday-indexed setmana (the algorithm
 * stores the Monday of the ISO week; the publish day is Saturday). */
function setmanaToDissabte(iso) {
  if (!iso) return null
  const d = new Date(iso + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() + 5)
  return d.toISOString().slice(0, 10)
}

/* ── One row of the top list. Mirrors HomePage's TopRow. */
function TopRow({ e }) {
  const credits = [
    e.artista?.nom,
    ...(e.artistes_col || []).map(c => c.nom),
  ].filter(Boolean).join(', ')
  return (
    <li>
      <Link
        to={cancoUrl({
          cancoSlug: e.canco?.slug,
          artistaSlug: e.artista?.slug,
          albumSlug: e.album?.slug,
        })}
        className="flex items-center gap-3 px-2 py-2 rounded-md hover:bg-tq-ink/5 transition-colors"
      >
        <span className="w-8 text-center text-lg font-bold font-display tabular-nums text-tq-ink">
          {e.posicio}
        </span>
        <span className="w-4 flex justify-center shrink-0">
          <TrendCue posicio={e.posicio} posicio_anterior={e.posicio_anterior} />
        </span>
        {e.album?.imatge_url ? (
          <img
            src={e.album.imatge_url}
            alt=""
            loading="lazy"
            className="w-12 h-12 rounded object-cover shrink-0"
          />
        ) : (
          <div className="w-12 h-12 rounded shrink-0" style={{ background: 'var(--mm-color-gray-200)' }} />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold truncate">{e.canco?.nom}</p>
          <p className="text-xs text-tq-ink/60 truncate">{credits}</p>
          {e.album?.nom && (
            <p className="text-[11px] text-tq-ink/60 truncate">{e.album.nom}</p>
          )}
        </div>
      </Link>
    </li>
  )
}

/* ── Header: hero ink band with title + territori + week navigator. */
function TopHero({ data, territori, setParams, setmanaParam }) {
  const titoli = TERRITORI_NOM[data?.territori || territori] || territori
  const dissabte = data?.setmana_dissabte || setmanaToDissabte(data?.setmana)
  const prevDissabte = setmanaToDissabte(data?.prev_setmana)
  const nextDissabte = setmanaToDissabte(data?.next_setmana)
  const hasPrev = !!data?.prev_setmana
  const hasNext = !!data?.next_setmana

  function go(setmana) {
    if (!setmana) return
    const next = new URLSearchParams()
    next.set('t', territori.toLowerCase())
    next.set('s', setmana)
    setParams(next)
  }

  function goLatest() {
    const next = new URLSearchParams()
    next.set('t', territori.toLowerCase())
    setParams(next)
  }

  return (
    <section className="-mx-6 lg:-mx-12 px-6 lg:px-12 py-10 md:py-12 bg-tq-ink text-white">
      <div className="max-w-6xl mx-auto">
        <p className="text-[10px] uppercase tracking-widest text-tq-yellow">
          El nostre top setmanal
        </p>
        <h1 className="text-3xl md:text-5xl font-bold font-display mt-1.5 leading-tight">
          Top {titoli}
        </h1>
        {data?.fallback_from && (
          <p className="text-xs text-tq-yellow mt-2">
            {TERRITORI_NOM[data.fallback_from]} encara no té prou dades
            per a un top propi — ara mateix mostrem el d'«Altres».
          </p>
        )}

        {/* Territori selector — pills */}
        <nav className="flex flex-wrap gap-1.5 mt-5" aria-label="Territoris">
          {TERRITORIS.map(t => (
            <button
              key={t.codi}
              type="button"
              onClick={() => {
                const next = new URLSearchParams()
                next.set('t', t.codi.toLowerCase())
                if (setmanaParam) next.set('s', setmanaParam)
                setParams(next)
              }}
              className={
                'px-3 py-1 rounded-full text-xs font-semibold transition-colors ' +
                (t.codi === territori
                  ? 'bg-tq-yellow text-tq-ink'
                  : 'bg-white/10 text-white hover:bg-white/20')
              }
            >
              {t.nom}
            </button>
          ))}
        </nav>

        {/* Week navigator — only when we know the dissabte. */}
        {dissabte && (
          <div className="mt-6 flex items-center gap-3 flex-wrap">
            <button
              type="button"
              onClick={() => go(data?.prev_setmana)}
              disabled={!hasPrev}
              title={hasPrev ? `Setmana del ${fmtDataLlarga(prevDissabte)}` : 'No hi ha setmana anterior'}
              aria-label="Setmana anterior"
              className={
                'inline-flex items-center justify-center w-9 h-9 rounded-full transition-colors ' +
                (hasPrev
                  ? 'bg-white/10 text-white hover:bg-tq-yellow hover:text-tq-ink'
                  : 'bg-white/5 text-white/30 cursor-not-allowed')
              }
            >
              <MmIcon name="arrow-left" className="h-4 w-4" />
            </button>

            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-widest text-white/60">
                Setmana del
              </span>
              <span className="text-base font-semibold tabular-nums">
                {fmtDataLlarga(dissabte)}
              </span>
            </div>

            <button
              type="button"
              onClick={() => go(data?.next_setmana)}
              disabled={!hasNext}
              title={hasNext ? `Setmana del ${fmtDataLlarga(nextDissabte)}` : 'Aquesta és la més recent'}
              aria-label="Setmana següent"
              className={
                'inline-flex items-center justify-center w-9 h-9 rounded-full transition-colors ' +
                (hasNext
                  ? 'bg-white/10 text-white hover:bg-tq-yellow hover:text-tq-ink'
                  : 'bg-white/5 text-white/30 cursor-not-allowed')
              }
            >
              <MmIcon name="arrow-right" className="h-4 w-4" />
            </button>

            {/* "Tornar a l'actual" button — only when not viewing the
                latest week. The shortcut spares the user clicking
                next a few times after deep-diving into history. */}
            {hasNext && (
              <button
                type="button"
                onClick={goLatest}
                className="ml-auto text-xs font-semibold text-white/70 underline hover:text-tq-yellow transition-colors"
              >
                Tornar a l'última →
              </button>
            )}

            {data?.es_provisional && (
              <span
                className="text-[10px] font-semibold px-2 py-0.5 rounded uppercase tracking-widest"
                style={{ backgroundColor: 'rgba(250, 204, 21, 0.2)', color: 'var(--color-tq-yellow)' }}
              >
                Provisional
              </span>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

/* ── Page ──────────────────────────────────────────────────────────── */

export default function TopPage() {
  const [params, setParams] = useSearchParams()
  const territori = (params.get('t') || 'PPCC').toUpperCase()
  const setmanaParam = params.get('s') || ''

  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setError(null)
    const qs = new URLSearchParams()
    qs.set('territori', territori)
    if (setmanaParam) qs.set('setmana', setmanaParam)
    api.get(`/top/?${qs}`)
      .then(setData)
      .catch(err => setError(err.message || 'Error'))
      .finally(() => setLoading(false))
  }, [territori, setmanaParam])

  const entries = data?.entries || []
  const left  = entries.slice(0, 20)
  const right = entries.slice(20, 40)

  return (
    <div className="space-y-0">
      <SeoHead entity="top" />
      <TopHero
        data={data}
        territori={territori}
        setParams={setParams}
        setmanaParam={setmanaParam}
      />

      {/* List band — white. */}
      <section className="-mx-6 lg:-mx-12 px-6 lg:px-12 py-10 md:py-12 bg-white text-tq-ink">
        <div className="max-w-6xl mx-auto">
          {error && <Alert tone="danger">{error}</Alert>}

          {loading && (
            <div className="grid sm:grid-cols-2 gap-x-6">
              {Array.from({ length: 20 }).map((_, i) => (
                <div key={i} className="h-12 my-1 bg-tq-ink/5 rounded-md animate-pulse" />
              ))}
            </div>
          )}

          {!loading && !error && entries.length === 0 && (
            <p className="text-sm text-tq-ink/60 italic">
              Encara no hi ha top per a aquest territori i setmana.
            </p>
          )}

          {!loading && !error && entries.length > 0 && (
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1">
              <ol className="space-y-1">{left.map(e => <TopRow key={e.posicio} e={e} />)}</ol>
              <ol className="space-y-1">{right.map(e => <TopRow key={e.posicio} e={e} />)}</ol>
            </div>
          )}
        </div>
      </section>

      {/* Methodology footer band — discreet ink strip. */}
      <section className="-mx-6 lg:-mx-12 px-6 lg:px-12 py-6 bg-tq-ink text-white">
        <div className="max-w-6xl mx-auto text-center">
          <p className="text-xs text-white/60">
            Calculat a partir d'escoltes reals.{' '}
            <Link to="/com-funciona" className="underline hover:text-tq-yellow transition-colors">
              Com es decideix el top →
            </Link>
          </p>
        </div>
      </section>
    </div>
  )
}
