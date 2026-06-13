/**
 * HomePage — redisseny web (network-kit language).
 *
 * Bands (handoff + Miquel's amendments):
 *   1. Hero            — dark band + glows, Anton headline, ONE live
 *                        countdown glass card (SETMANA pill, week from API).
 *   2. EL TOP 10       — #1 glass card + rows 2–10, with territory chips.
 *   3. LA PUJADA       — biggest climber of the week (cançó destacada).
 *   4. EXPLORA PER TERRITORI — territory glass grid.
 *   5. NOUS ÀLBUMS     — cover-forward wall.
 *   6. PER DESCOBRIR   — recently approved artists, never in the top.
 *   7. CTA band (yellow) — simple call to the top, NO second clock.
 *
 * Vocabulary: "el top" / "el top complet" / "la llista" — the house words
 * (the R-word is product-vetoed across the SPA).
 * Week number + per-row territori come from the API (single source); the
 * client only paints. Real data/URLs/countdown logic conserved.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import useApi from '../hooks/useApi'
import { Band, Glow, Glass, Kicker, Crit, Numeral, Move, TerrLogo, RdCover } from '../components/rd/primitives'
import { terr } from '../components/rd/terr'
import { cancoUrl, albumUrl, artistaUrl } from '../lib/urls'
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

/* ── Shared section header (kicker + Anton crit title) ──────────────── */
function SecHead({ kicker, children }) {
  return (
    <header style={{ marginBottom: 'clamp(22px,3vw,34px)' }}>
      <Kicker color="var(--color-tq-yellow)">{kicker}</Kicker>
      <Crit as="h2" className="rd-sec-title">{children}</Crit>
    </header>
  )
}

/* Cover props for a top-style entry (real Deezer cover, sized to slot). */
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

/* ── 1 · Hero ───────────────────────────────────────────────────────── */
function Hero({ now, week }) {
  const c = useCountdown(now)
  return (
    <Band tone="hero">
      <Glow variant="a" />
      <Glow variant="b" />
      <div className="rd-hero-grid">
        <div>
          <Kicker className="block mb-3.5">el top setmanal de música en català</Kicker>
          <h1 className="rd-hero-h1">
            LA NOSTRA MÚSICA<br />NO PARA DE <span style={{ color: 'var(--color-tq-yellow)' }}>CRÉIXER</span>
          </h1>
          <p className="rd-hero-sub">
            Cada dissabte mesurem què sona als Països Catalans a partir
            d'escoltes reals. Deu territoris, un top de 40, dades obertes.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link to="/top" className="rd-btn rd-btn--hot">Veure el top complet</Link>
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
function NumberOneCard({ e }) {
  const code = e.artista?.territori
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
          {code && (
            <div className="rd-one-terr">
              <TerrLogo code={code} className="h-[18px] w-[18px]" />
              <Kicker>{terr(code).nom}</Kicker>
            </div>
          )}
        </div>
      </div>
    </Link>
  )
}

function TopRow({ e }) {
  const code = e.artista?.territori
  return (
    <li>
      <Link to={rowUrl(e)} className="rd-trow">
        <Numeral n={e.posicio} size={26} color="rgba(255,255,255,0.92)" />
        <RdCover {...coverProps(e, 42, 8)} />
        <div className="min-w-0 flex-1">
          <p className="rd-trow-title">{e.canco?.nom}</p>
          <p className="rd-trow-artist">{e.artista?.nom}</p>
        </div>
        {code && <TerrLogo code={code} className="h-4 w-4 shrink-0" />}
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
        Veure el top complet (40) →
      </Link>
    </Band>
  )
}

/* ── 3 · LA PUJADA (cançó destacada — biggest climber) ──────────────── */
function PujadaSection() {
  const { data } = useApi('/top/canco-destacada/')
  const e = data?.entry
  if (!e) return null
  const code = e.territori
  return (
    <Band tone="ink">
      <SecHead kicker="el gran salt de la setmana">LA PUJADA</SecHead>
      <Link to={rowUrl(e)} className="rd-pujada rd-glass">
        <RdCover {...coverProps(e, 150, 14)} />
        <div className="min-w-0">
          <span className="rd-pujada-badge" style={{ background: 'var(--color-tq-yellow)', color: '#0a0a0a' }}>
            #{e.posicio} · puja {e.delta}
          </span>
          <h3 className="rd-one-title" style={{ marginTop: 12 }}>{e.canco?.nom}</h3>
          <p className="rd-one-artist">{e.artista?.nom}</p>
          {code && code !== 'PPCC' && (
            <div className="rd-one-terr"><TerrLogo code={code} className="h-[18px] w-[18px]" /><Kicker>{terr(code).nom}</Kicker></div>
          )}
        </div>
      </Link>
    </Band>
  )
}

/* ── 4 · EXPLORA PER TERRITORI ──────────────────────────────────────── */
const TERR_GRID = ['CAT', 'VAL', 'BAL', 'AND', 'CNO', 'FRA', 'ALG', 'ALT']

function TerritoriSection() {
  return (
    <Band tone="ink2">
      <SecHead kicker="deu territoris, una llengua">EXPLORA PER TERRITORI</SecHead>
      <div className="rd-terr-grid">
        {TERR_GRID.map(code => {
          const t = terr(code)
          return (
            <Link key={code} to={`/top?t=${code.toLowerCase()}`} className="rd-terr-card rd-glass">
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

/* ── 5 · NOUS ÀLBUMS ────────────────────────────────────────────────── */
function AlbumsSection() {
  const { data, loading } = useApi('/albums/?ordering=-data_llancament&amb_verificades=true&limit=10')
  const items = data?.results || []
  if (!loading && items.length === 0) return null
  return (
    <Band tone="ink">
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

/* ── 6 · PER DESCOBRIR (recently approved, never in the top) ────────── */
function DescobertaSection() {
  const { data } = useApi('/artistes/descoberta/?limit=4')
  const items = data?.results || []
  if (items.length === 0) return null
  return (
    <Band tone="ink2">
      <SecHead kicker="encara no han estat al top">PER DESCOBRIR</SecHead>
      <ul className="rd-desc-grid">
        {items.map(a => {
          const code = a.territoris?.[0]
          const t = code ? terr(code) : null
          return (
            <li key={a.slug}>
              <Link to={artistaUrl(a.slug)} className="block group">
                <RdCover
                  src={a.imatge_url ? deezerImg(a.imatge_url, 500) : null}
                  label={a.nom} alt={a.nom ? `${a.nom}` : ''}
                  tint={t ? t.deep : '#33373d'}
                  size="100%" radius={12}
                  className="rd-album-cover"
                />
                <p className="rd-album-title">{a.nom}</p>
                {t && (
                  <span className="rd-desc-terr" style={{ color: t.accent }}>
                    <TerrLogo code={code} className="h-3.5 w-3.5" /> {t.nom}
                  </span>
                )}
              </Link>
            </li>
          )
        })}
      </ul>
    </Band>
  )
}

/* ── 7 · CTA band (yellow) — single clock rule: NO numbers here ─────── */
function CtaBand() {
  return (
    <Band tone="yellow" className="text-center">
      <Kicker color="rgba(10,10,10,0.66)">cada dissabte a les 9 h</Kicker>
      <p className="rd-cd-published">EL TOP, CADA SETMANA</p>
      <p className="rd-cd-note" style={{ marginBottom: 22 }}>música en català, viva i mesurable</p>
      <Link to="/top" className="rd-btn" style={{ background: '#0a0a0a', color: 'var(--color-tq-yellow)' }}>
        Veure el top complet →
      </Link>
    </Band>
  )
}

/* ── Page ───────────────────────────────────────────────────────────── */
export default function HomePage() {
  useEffect(() => { document.body.removeAttribute('data-theme') }, [])
  const now = useNow()
  // Week number comes from the API (single backend source — no client anchor).
  const { data: top } = useApi('/top/?territori=PPCC&oficial=true&limit=1')
  const week = top?.setmana_numero ?? null

  return (
    <>
      <SeoHead entity="homepage" />
      <Hero now={now} week={week} />
      <TopTenSection />
      <PujadaSection />
      <TerritoriSection />
      <AlbumsSection />
      <DescobertaSection />
      <CtaBand />
    </>
  )
}
