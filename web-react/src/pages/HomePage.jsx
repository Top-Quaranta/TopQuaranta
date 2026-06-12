/**
 * HomePage — redisseny web (network-kit language).
 *
 * Five editorial bands, following the design handoff:
 *   1. Hero          — dark band + glows, Anton headline, live countdown
 *                      glass card (4 cells + SETMANA pill).
 *   2. EL TOP 10     — #1 glass card + rows 2–10 (real /top/ PPCC).
 *   3. EXPLORA PER TERRITORI — territory glass grid → /top?territori=…
 *   4. NOUS ÀLBUMS   — cover-forward wall (real /albums/).
 *   5. Banda groga   — big countdown (same logic as before, decision 9).
 *
 * Real data + real URLs are preserved (cancoUrl/albumUrl, deezerImg,
 * useApi, SeoHead). The global top carries no per-row territori in its
 * payload, so the per-row territory chip from the prototype (sample data)
 * is honestly omitted; the territory language lives in section 3.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import useApi from '../hooks/useApi'
import { Band, Glow, Glass, Kicker, Crit, Numeral, Move, TerrLogo, RdCover } from '../components/rd/primitives'
import { terr } from '../components/rd/terr'
import { cancoUrl, albumUrl } from '../lib/urls'
import { deezerImg } from '../lib/img'
import { SeoHead } from '../lib/seoHead'

/* ── Countdown (same logic as the legacy HomePage — decision 9) ──────── */
function nextSaturday9(from = new Date()) {
  const next = new Date(from)
  const dow = next.getDay()
  let daysAhead = (6 - dow + 7) % 7
  next.setHours(9, 0, 0, 0)
  if (daysAhead === 0 && from.getTime() >= next.getTime()) daysAhead = 7
  next.setDate(next.getDate() + daysAhead)
  return next
}
function topPublishedToday(now = new Date()) {
  return now.getDay() === 6 && now.getHours() >= 9
}
function useNow() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}
function useCountdown(now) {
  const target = useMemo(() => nextSaturday9(now), [now])
  const ms = Math.max(0, target.getTime() - now.getTime())
  const tot = Math.floor(ms / 1000)
  return {
    dies: Math.floor(tot / 86400),
    hores: Math.floor((tot % 86400) / 3600),
    minuts: Math.floor((tot % 3600) / 60),
    segons: tot % 60,
  }
}

/* Project week number from the Saturday ISO date (anchor: Sat 2026-04-25
   = week 34, mirroring music.dates.project_week_number). */
const WEEK_ANCHOR = Date.UTC(2026, 3, 25)
function projectWeek(dissabteIso) {
  if (!dissabteIso) return null
  const d = new Date(dissabteIso)
  if (Number.isNaN(d.getTime())) return null
  const days = Math.round((Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - WEEK_ANCHOR) / 86400000)
  return 34 + Math.round(days / 7)
}

/* ── Shared section header (kicker + Anton crit title) ──────────────── */
function SecHead({ kicker, children }) {
  return (
    <header style={{ marginBottom: 'clamp(22px,3vw,34px)' }}>
      <Kicker color="var(--color-tq-yellow)">{kicker}</Kicker>
      <Crit as="h2" className="rd-sec-title">{children}</Crit>
    </header>
  )
}

/* ── 1 · Hero ───────────────────────────────────────────────────────── */
function Hero({ now, week }) {
  const c = useCountdown(now)
  return (
    <Band tone="hero">
      <Glow variant="a" />
      <Glow variant="b" />
      <div className="rd-hero-grid">
        <div>
          <Kicker className="block mb-3.5">el rànquing setmanal de música en català</Kicker>
          <h1 className="rd-hero-h1">
            LA NOSTRA MÚSICA<br />NO PARA DE <span style={{ color: 'var(--color-tq-yellow)' }}>CRÉIXER</span>
          </h1>
          <p className="rd-hero-sub">
            Cada dissabte mesurem què sona als Països Catalans a partir
            d'escoltes reals. Deu territoris, un Top 40, dades obertes.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link to="/top" className="rd-btn rd-btn--hot">Veure el TOP 40</Link>
            <Link to="/com-funciona" className="rd-btn rd-btn--ghost">Com funciona</Link>
          </div>
        </div>

        <Glass as="aside" className="rd-count-card">
          <Kicker>proper top · dissabte a les 9 h</Kicker>
          <div className="rd-count-row">
            {[['dies', c.dies], ['h', c.hores], ['min', c.minuts], ['s', c.segons]].map(([l, n]) => (
              <div key={l} className="text-center">
                <span className="rd-count-n" style={{ color: 'var(--color-tq-yellow)' }}>{String(n).padStart(2, '0')}</span>
                <span className="rd-count-l">{l}</span>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-3">
            {week != null && (
              <span className="rd-pill-week" style={{ background: 'var(--color-tq-yellow)' }}>SETMANA {week}</span>
            )}
            <Kicker>en directe</Kicker>
          </div>
        </Glass>
      </div>
    </Band>
  )
}

/* ── 2 · EL TOP 10 ──────────────────────────────────────────────────── */
function coverProps(e, size, radius) {
  return {
    src: e.album?.imatge_url ? deezerImg(e.album.imatge_url, size <= 48 ? 120 : size <= 160 ? 250 : 500) : null,
    label: e.canco?.nom || e.artista?.nom || '?',
    alt: e.album?.nom ? `Portada de ${e.album.nom}` : '',
    size, radius,
  }
}
function rowUrl(e) {
  return cancoUrl({ cancoSlug: e.canco?.slug, artistaSlug: e.artista?.slug, albumSlug: e.album?.slug })
}

function NumberOneCard({ e }) {
  return (
    <Link to={rowUrl(e)} className="rd-one-card rd-glass">
      <div className="rd-one-body">
        <RdCover {...coverProps(e, 132, 16)} />
        <div className="min-w-0">
          <div className="flex items-center gap-3.5 flex-wrap">
            <Numeral n="1" size={72} color="var(--color-tq-yellow)" />
            <span className="rd-one-tag" style={{ borderColor: 'var(--color-tq-yellow)', color: 'var(--color-tq-yellow)' }}>
              <Move posicio={e.posicio} posicio_anterior={e.posicio_anterior} size={20} /> número u
            </span>
          </div>
          <h3 className="rd-one-title">{e.canco?.nom}</h3>
          <p className="rd-one-artist">{e.artista?.nom}</p>
        </div>
      </div>
    </Link>
  )
}

function TopRow({ e }) {
  return (
    <li>
      <Link to={rowUrl(e)} className="rd-trow">
        <Numeral n={e.posicio} size={26} color="rgba(255,255,255,0.92)" />
        <RdCover {...coverProps(e, 42, 8)} />
        <div className="min-w-0 flex-1">
          <p className="rd-trow-title">{e.canco?.nom}</p>
          <p className="rd-trow-artist">{e.artista?.nom}</p>
        </div>
        <span className="rd-trow-mv"><Move posicio={e.posicio} posicio_anterior={e.posicio_anterior} size={20} /></span>
      </Link>
    </li>
  )
}

function TopRowSkeleton() {
  return (
    <li className="rd-trow" aria-hidden="true">
      <span style={{ width: 26 }} />
      <span style={{ width: 42, height: 42, borderRadius: 8, background: 'rgba(255,255,255,0.06)' }} />
      <span style={{ flex: 1, height: 14, borderRadius: 4, background: 'rgba(255,255,255,0.06)' }} />
    </li>
  )
}

function TopTenSection() {
  const { data, loading, error, reload } = useApi('/top/?territori=PPCC&oficial=true&limit=10')
  const entries = data?.entries || []
  const one = entries[0]
  const rest = entries.slice(1, 10)

  return (
    <Band tone="ink2">
      <SecHead kicker="aquesta setmana · global">EL TOP 10</SecHead>

      {error ? (
        <Glass className="p-6 text-center">
          <p className="text-white/70 text-sm">No s'ha pogut carregar el top ara mateix.</p>
          <button type="button" onClick={reload} className="rd-btn rd-btn--ghost mt-3">Reintentar</button>
        </Glass>
      ) : loading ? (
        <div className="rd-ten-grid">
          <Glass className="rd-one-card" style={{ minHeight: 180 }} />
          <ol className="rd-ten-list rd-glass">{Array.from({ length: 9 }).map((_, i) => <TopRowSkeleton key={i} />)}</ol>
        </div>
      ) : entries.length === 0 ? (
        <p className="rd-empty">Encara no hi ha cap top publicat. Torna dissabte a les 9 h.</p>
      ) : (
        <>
          {data?.es_provisional && (
            <p className="rd-empty" style={{ marginBottom: 16 }}>Top provisional — encara s'està calculant la setmana.</p>
          )}
          <div className="rd-ten-grid">
            {one && <NumberOneCard e={one} />}
            <ol className="rd-ten-list rd-glass">{rest.map(e => <TopRow key={e.posicio} e={e} />)}</ol>
          </div>
        </>
      )}

      <Link to="/top" className="rd-link-more" style={{ color: 'var(--color-tq-yellow)' }}>
        Veure el rànquing complet (40) →
      </Link>
    </Band>
  )
}

/* ── 3 · EXPLORA PER TERRITORI ──────────────────────────────────────── */
const TERR_GRID = ['CAT', 'VAL', 'BAL', 'AND', 'CNO', 'FRA', 'ALG', 'ALT']

function TerritoriSection() {
  return (
    <Band tone="ink">
      <SecHead kicker="deu territoris, una llengua">EXPLORA PER TERRITORI</SecHead>
      <div className="rd-terr-grid">
        {TERR_GRID.map(code => {
          const t = terr(code)
          return (
            <Link key={code} to={`/top?territori=${code}`} className="rd-terr-card rd-glass">
              <div className="rd-terr-glow" style={{ background: `radial-gradient(110% 80% at 50% 0%, ${t.deep}, transparent 72%)` }} />
              <TerrLogo code={code} className="h-10 w-10" />
              <span className="rd-terr-name" style={{ color: t.accent }}>{t.nom}</span>
            </Link>
          )
        })}
      </div>
    </Band>
  )
}

/* ── 4 · NOUS ÀLBUMS ────────────────────────────────────────────────── */
function AlbumsSection() {
  const { data, loading } = useApi('/albums/?ordering=-data_llancament&amb_verificades=true&limit=10')
  const items = data?.results || []
  if (!loading && items.length === 0) return null
  return (
    <Band tone="ink2">
      <SecHead kicker="acabats de publicar">NOUS <span style={{ color: 'var(--color-tq-yellow)' }}>ÀLBUMS</span></SecHead>
      {loading ? (
        <ul className="rd-album-wall">
          {Array.from({ length: 10 }).map((_, i) => (
            <li key={i}><div style={{ aspectRatio: '1', borderRadius: 12, background: 'rgba(255,255,255,0.06)' }} /></li>
          ))}
        </ul>
      ) : (
        <ul className="rd-album-wall">
          {items.map(a => (
            <li key={a.pk}>
              <Link to={albumUrl({ albumSlug: a.slug, artistaSlug: a.artista?.slug })} className="block group">
                <RdCover
                  src={a.imatge_url ? deezerImg(a.imatge_url, 500) : null}
                  label={a.nom} alt={a.nom ? `Portada de ${a.nom}` : ''}
                  size="100%" radius={12}
                  className="rd-album-cover"
                />
                <p className="rd-album-title">{a.nom}</p>
                <p className="rd-album-artist">{a.artista?.nom}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Band>
  )
}

/* ── 5 · Banda groga (countdown) ────────────────────────────────────── */
function CountdownBand({ now }) {
  const c = useCountdown(now)
  const published = topPublishedToday(now)
  return (
    <Band tone="yellow" className="text-center">
      {published ? (
        <>
          <Kicker color="rgba(10,10,10,0.66)">avui mateix</Kicker>
          <p className="rd-cd-published">Top publicat avui</p>
          <p className="rd-cd-note">torna el proper dissabte a les 9 h · música en català</p>
        </>
      ) : (
        <>
          <Kicker color="rgba(10,10,10,0.66)">proper top oficial</Kicker>
          <div className="rd-cd-row">
            {[['dies', c.dies], ['hores', c.hores], ['minuts', c.minuts], ['segons', c.segons]].map(([l, n]) => (
              <div key={l} className="text-center">
                <span className="rd-cd-n">{String(n).padStart(2, '0')}</span>
                <span className="rd-cd-l">{l}</span>
              </div>
            ))}
          </div>
          <p className="rd-cd-note">cada dissabte a les 9 h · música en català</p>
        </>
      )}
    </Band>
  )
}

/* ── Page ───────────────────────────────────────────────────────────── */
export default function HomePage() {
  // Retire the legacy yellow-body theme if a previous render set it.
  useEffect(() => { document.body.removeAttribute('data-theme') }, [])
  const now = useNow()
  const { data: top } = useApi('/top/?territori=PPCC&oficial=true&limit=1')
  const week = projectWeek(top?.setmana_dissabte || top?.setmana)

  return (
    <>
      <SeoHead entity="homepage" />
      <Hero now={now} week={week} />
      <TopTenSection />
      <TerritoriSection />
      <AlbumsSection />
      <CountdownBand now={now} />
    </>
  )
}
