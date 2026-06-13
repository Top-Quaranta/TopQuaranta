/**
 * TopPage — /top (redisseny web).
 *
 * Dark hero with the big Anton title + territory pills + week navigator,
 * then the 1–40 list in two columns of glass rows. House vocabulary
 * ("el top", "la llista" — never the R-word).
 *
 * URL contract UNCHANGED: ?t=<territori-code>, ?s=<YYYY-MM-DD setmana>.
 * Backend gives prev_setmana / next_setmana (navigator boundaries),
 * fallback_from (small-territory banner), es_provisional, and the
 * single-source setmana_numero (week badge). Per-row territori comes
 * from the additive artista.territori field.
 */
import { useSearchParams, Link } from 'react-router-dom'
import useApi from '../hooks/useApi'
import { Band, Glow, Glass, Kicker, Crit, Numeral, Move, TerrLogo, RdCover } from '../components/rd/primitives'
import { terr } from '../components/rd/terr'
import { cancoUrl } from '../lib/urls'
import { deezerImg } from '../lib/img'
import { fmtDataLlarga } from '../lib/format'
import { SeoHead } from '../lib/seoHead'

/* Pill order — Global first, then by user-facing name, Altres last. */
const TERRITORIS = ['PPCC', 'AND', 'CAT', 'CNO', 'FRA', 'BAL', 'ALG', 'VAL', 'ALT']

function setmanaToDissabte(iso) {
  if (!iso) return null
  const d = new Date(iso + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() + 5)
  return d.toISOString().slice(0, 10)
}

/* ── One row of the 1–40 list. ── */
function FullRow({ e }) {
  const first = e.posicio === 1
  const code = e.artista?.territori
  const credits = [e.artista?.nom, ...(e.artistes_col || []).map(c => c.nom)].filter(Boolean).join(', ')
  return (
    <li>
      <Link
        to={cancoUrl({ cancoSlug: e.canco?.slug, artistaSlug: e.artista?.slug, albumSlug: e.album?.slug })}
        className={`rd-frow rd-glass${first ? ' rd-frow-one' : ''}`}
      >
        <span className="rd-frow-num">
          <Numeral n={e.posicio} size={first ? 38 : 30} color={first ? 'var(--color-tq-yellow)' : 'rgba(255,255,255,0.92)'} />
        </span>
        <span className="rd-frow-mv"><Move posicio={e.posicio} posicio_anterior={e.posicio_anterior} size={20} /></span>
        <RdCover
          src={e.album?.imatge_url ? deezerImg(e.album.imatge_url, 120) : null}
          label={e.canco?.nom || e.artista?.nom || '?'}
          alt={e.album?.nom ? `Portada de ${e.album.nom}` : ''}
          size={52} radius={9}
        />
        <div className="rd-frow-meta">
          <p className="rd-frow-title" style={first ? { color: 'var(--color-tq-yellow)' } : undefined}>{e.canco?.nom}</p>
          <p className="rd-frow-artist">{credits}</p>
          {e.album?.nom && <p className="rd-frow-album">{e.album.nom}</p>}
        </div>
        {code && (
          <span className="rd-frow-terr">
            <TerrLogo code={code} className="h-4 w-4" />
            <span className="rd-frow-terrname" style={{ color: terr(code).accent }}>{terr(code).short}</span>
          </span>
        )}
      </Link>
    </li>
  )
}

/* ── Hero: title + territory pills + week navigator. ── */
function TopHero({ data, territori, setParams, setmanaParam }) {
  const t = terr(data?.territori || territori)
  const isPpcc = (data?.territori || territori) === 'PPCC'
  const dissabte = data?.setmana_dissabte || setmanaToDissabte(data?.setmana)
  const hasPrev = !!data?.prev_setmana
  const hasNext = !!data?.next_setmana

  function go(setmana) {
    if (!setmana) return
    const next = new URLSearchParams()
    next.set('t', territori.toLowerCase())
    next.set('s', setmana)
    setParams(next)
  }
  function selectTerr(codi) {
    const next = new URLSearchParams()
    next.set('t', codi.toLowerCase())
    if (setmanaParam) next.set('s', setmanaParam)
    setParams(next)
  }
  function goLatest() {
    const next = new URLSearchParams()
    next.set('t', territori.toLowerCase())
    setParams(next)
  }

  return (
    <Band tone="top-hero">
      <Glow variant="a" color={t.deep} />
      <Kicker className="block mb-2">el nostre top setmanal</Kicker>
      <Crit as="h1" className="rd-top-h1">
        TOP <span style={{ color: 'var(--color-tq-yellow)' }}>{isPpcc ? '40' : t.short.toUpperCase()}</span>
      </Crit>

      {data?.fallback_from && (
        <p className="text-sm mt-2" style={{ color: 'var(--color-tq-yellow)' }}>
          {terr(data.fallback_from).nom} encara no té prou dades per a un top
          propi — ara mateix mostrem el d'«Altres».
        </p>
      )}

      <nav className="rd-terr-pills" aria-label="Territoris">
        {TERRITORIS.map(codi => {
          const on = codi === territori
          return (
            <button
              key={codi}
              type="button"
              onClick={() => selectTerr(codi)}
              className={`rd-pill${on ? ' rd-pill-on' : ''}`}
              style={on ? { background: 'var(--color-tq-yellow)', color: '#0a0a0a' } : undefined}
            >
              {terr(codi).nom}
            </button>
          )
        })}
      </nav>

      {dissabte && (
        <div className="rd-wk-nav">
          <button
            type="button" onClick={() => go(data?.prev_setmana)} disabled={!hasPrev}
            aria-label="Setmana anterior"
            className={`rd-wk-arrow${hasPrev ? '' : ' rd-wk-off'}`}
          >‹</button>
          <div className="rd-wk-label">
            <Kicker>setmana del</Kicker>
            <span className="rd-wk-date">{fmtDataLlarga(dissabte)}</span>
          </div>
          <button
            type="button" onClick={() => go(data?.next_setmana)} disabled={!hasNext}
            aria-label="Setmana següent"
            className={`rd-wk-arrow${hasNext ? '' : ' rd-wk-off'}`}
          >›</button>
          {hasNext && (
            <button type="button" onClick={goLatest} className="rd-wk-latest">Tornar a l'última →</button>
          )}
          {data?.setmana_numero != null && (
            <span className="rd-wk-badge" style={{ borderColor: 'var(--color-tq-yellow)', color: 'var(--color-tq-yellow)' }}>
              SETMANA {data.setmana_numero}
            </span>
          )}
          {data?.es_provisional && (
            <span className="rd-wk-badge" style={{ borderColor: 'var(--color-tq-yellow)', color: 'var(--color-tq-yellow)' }}>
              PROVISIONAL
            </span>
          )}
        </div>
      )}
    </Band>
  )
}

/* ── Page ──────────────────────────────────────────────────────────── */
export default function TopPage() {
  const [params, setParams] = useSearchParams()
  const territori = (params.get('t') || 'PPCC').toUpperCase()
  const setmanaParam = params.get('s') || ''

  const _qs = new URLSearchParams()
  _qs.set('territori', territori)
  if (setmanaParam) _qs.set('setmana', setmanaParam)
  const { data, error, loading, reload } = useApi(`/top/?${_qs}`)

  const entries = data?.entries || []
  const mid = Math.ceil(entries.length / 2)
  const left = entries.slice(0, mid)
  const right = entries.slice(mid)

  return (
    <>
      <SeoHead entity="top" />
      <TopHero data={data} territori={territori} setParams={setParams} setmanaParam={setmanaParam} />

      <Band tone="ink2">
        {error ? (
          <Glass className="p-6 text-center">
            <p className="text-white/70 text-sm">No s'ha pogut carregar el top ara mateix.</p>
            <button type="button" onClick={reload} className="rd-btn rd-btn--ghost mt-3">Reintentar</button>
          </Glass>
        ) : loading ? (
          <div className="rd-full-grid">
            <ol className="rd-full-col">{Array.from({ length: 20 }).map((_, i) => <li key={i}><div className="rd-frow rd-glass" style={{ height: 68 }} /></li>)}</ol>
            <ol className="rd-full-col">{Array.from({ length: 20 }).map((_, i) => <li key={i}><div className="rd-frow rd-glass" style={{ height: 68 }} /></li>)}</ol>
          </div>
        ) : entries.length === 0 ? (
          <p className="rd-empty">Encara no hi ha prou dades per a un top d'aquest territori i setmana.</p>
        ) : (
          <div className="rd-full-grid">
            <ol className="rd-full-col">{left.map(e => <FullRow key={e.posicio} e={e} />)}</ol>
            <ol className="rd-full-col">{right.map(e => <FullRow key={e.posicio} e={e} />)}</ol>
          </div>
        )}

        <p className="rd-method">
          Calculat a partir d'escoltes reals de Last.fm.{' '}
          <Link to="/com-funciona" className="rd-method-link" style={{ color: 'var(--color-tq-yellow)' }}>
            Com es decideix el top →
          </Link>
        </p>
      </Band>
    </>
  )
}
