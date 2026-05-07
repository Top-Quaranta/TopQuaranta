/**
 * HomePage — Sprint I editorial redesign.
 *
 * Ten vertical sections, no sidebar, alternating ink/white surfaces
 * for visual rhythm:
 *
 *   1. Hero          — pitch + 3 blocks + 2 CTAs
 *   2. Stats         — three big counters in a row
 *   3. Top PPCC      — first 10 entries of the latest official top
 *   4. Cançó nova    — best new entry of the week
 *   5. Artista destacat — biggest jumper among verified-managed artists
 *   6. Últims llançaments — 6 albums, freshest with verified tracks
 *   7. Artistes en descoberta — recently approved, never in the top
 *   8. Territori en focus — one territory rotated weekly
 *   9. Notícies      — top 3 community posts (auth only)
 *  10. Compte enrere — small note about the next official top
 *
 * Inspirations: FACT (editorial dark), Bandcamp (clean cards), RA
 * (single accent on dark). All colours via mm-design tokens or the
 * brand `tq-*` aliases — zero hex hardcoded outside the territory
 * palette mapping below (kept from the old design for continuity).
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import useApi from '../hooks/useApi'
import MmIcon from '../components/MmIcon'
import {
  Section, SectionHeader, TerritoriBadge, TrendCue,
  TERR_COLORS, TERRITORI_NOM, FOCUS_TERRITORIS,
} from '../components/editorial'
import { albumUrl, artistaUrl, cancoUrl } from '../lib/urls'
import { SeoHead } from '../lib/seoHead'

/* ── Section 1 · Hero ──────────────────────────────────────────────── */

/* Each hero block is itself a navigation primitive — hovering hints
 * destination, clicking takes you there. The two redundant CTAs that
 * lived below were removed: the blocks already cover the same intents
 * (top, mapa, comunitat) and adding buttons made the section noisy.
 * `to` for the comunitat block flips for anonymous visitors so a
 * non-logged-in click still lands somewhere useful (registre). */
function makeHeroBlocks(profile) {
  return [
    {
      icon: 'icon-ranking', color: TERR_COLORS.BAL,
      to: '/top',
      title: 'El top setmanal',
      body: 'Escoltes reals de Last.fm. Deu territoris, top 40 cada dissabte.',
    },
    {
      icon: 'icon-mapa', color: TERR_COLORS.VAL,
      to: '/mapa',
      title: 'El mapa',
      body: 'Descobreix música per territori, comarca i municipi.',
    },
    {
      icon: 'user', color: TERR_COLORS.CAT,
      to: profile ? '/comunitat' : '/compte/accedir?mode=registre',
      title: 'La comunitat',
      body: "Troba algú amb qui fer música i compartir projectes.",
    },
  ]
}

function HeroBlock({ icon, color, title, body, to }) {
  return (
    <Link
      to={to}
      className="group bg-white text-tq-ink rounded-lg p-4 shadow-md flex flex-col gap-1.5 hover:shadow-lg hover:-translate-y-0.5 transition-all"
    >
      <span
        className="inline-flex items-center justify-center w-9 h-9 rounded-md text-white"
        style={{ backgroundColor: color }}
      >
        <MmIcon name={icon} className="h-5 w-5" />
      </span>
      <h3 className="text-sm font-bold font-display mt-0.5 group-hover:underline">{title}</h3>
      <p className="text-xs text-tq-ink/70 leading-snug">{body}</p>
    </Link>
  )
}

function HeroSection() {
  const { profile } = useAuth()
  const blocks = makeHeroBlocks(profile)

  return (
    <Section tone="ink">
      <p className="text-[10px] uppercase tracking-widest text-tq-yellow">
        TopQuaranta
      </p>
      <h1 className="text-3xl md:text-4xl font-bold font-display mt-1.5 max-w-3xl leading-tight">
        El punt de trobada de la música en català
      </h1>
      <p className="text-sm md:text-base text-white/80 mt-3 max-w-2xl leading-relaxed">
        Descobreix, comparteix i connecta amb la música i els músics
        en català. Una comunitat oberta amb dades públiques.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-6">
        {blocks.map(b => <HeroBlock key={b.title} {...b} />)}
      </div>

      <p className="text-xs text-white/60 mt-3">
        <Link to="/com-funciona" className="underline hover:text-tq-yellow transition-colors">
          Com funciona TopQuaranta →
        </Link>
      </p>
    </Section>
  )
}

/* ── Section 2 · Stats ─────────────────────────────────────────────── */

function StatsSection() {
  const { data } = useApi('/stats/')
  // Labels avoid the internal jargon ("verificades", "aprovats") —
  // a visitor doesn't need to know the staff state machine.
  const items = [
    { n: data?.cancons_verificades, l: 'Cançons' },
    { n: data?.artistes_aprovats,   l: 'Artistes' },
    { n: data?.territoris_actius,   l: 'Territoris' },
  ]
  return (
    <Section tone="white" className="!py-6 md:!py-8">
      <div className="grid grid-cols-3 gap-3 items-baseline">
        {items.map(it => (
          <div key={it.l} className="text-center sm:text-left">
            <p className="text-2xl md:text-4xl font-bold font-display tabular-nums leading-none">
              {it.n != null ? it.n.toLocaleString('ca-ES') : '—'}
            </p>
            <p className="text-[10px] uppercase tracking-widest text-tq-ink/60 mt-1">
              {it.l}
            </p>
          </div>
        ))}
      </div>
    </Section>
  )
}

/* ── Section 3 · Top PPCC (10) + asides ────────────────────────────── */

/* One row of the top list — used by both columns of the 5+5 grid. */
function TopRow({ e }) {
  return (
    <li>
      <Link
        to={cancoUrl({
          cancoSlug: e.canco?.slug,
          artistaSlug: e.artista?.slug,
          albumSlug: e.album?.slug,
        })}
        className="flex items-center gap-2.5 px-1.5 py-1 rounded hover:bg-tq-ink/5 transition-colors"
      >
        <span className="w-6 text-center text-base font-bold font-display tabular-nums">
          {e.posicio}
        </span>
        <span className="w-4 flex justify-center">
          <TrendCue posicio={e.posicio} posicio_anterior={e.posicio_anterior} />
        </span>
        {e.album?.imatge_url ? (
          <img
            src={e.album.imatge_url}
            alt=""
            loading="lazy"
            className="w-10 h-10 rounded object-cover shrink-0"
          />
        ) : (
          <div className="w-10 h-10 rounded shrink-0" style={{ background: 'var(--mm-color-gray-200)' }} />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold truncate">{e.canco?.nom}</p>
          <p className="text-xs text-tq-ink/60 truncate">{e.artista?.nom}</p>
        </div>
      </Link>
    </li>
  )
}

/* Top in two stacked-side columns of 5 each — keeps the section
 * vertically short while preserving the same 10 entries. */
function TopList5x5() {
  const { data } = useApi('/top/?territori=PPCC&oficial=true&limit=10')
  const entries = data?.entries || []
  const left = entries.slice(0, 5)
  const right = entries.slice(5, 10)
  return (
    <div>
      {entries.length === 0 && (
        <p className="text-sm text-tq-ink/60 italic">Encara no hi ha top publicat.</p>
      )}
      <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1">
        <ol className="space-y-1">{left.map(e => <TopRow key={e.posicio} e={e} />)}</ol>
        <ol className="space-y-1">{right.map(e => <TopRow key={e.posicio} e={e} />)}</ol>
      </div>
      <p className="mt-3">
        <Link to="/top?t=ppcc" className="text-sm font-semibold text-tq-ink underline hover:text-tq-yellow-deep transition-colors">
          Veure el top complet →
        </Link>
      </p>
    </div>
  )
}

/* Right-column card: the song with the biggest climb this week
 * (rotates week-to-week so the same song doesn't lead two weeks
 * in a row). Replaces the previous "nova entrada" + "artista
 * destacat" stack. */
function CancoDestacadaCard() {
  const { data } = useApi('/top/canco-destacada/')
  const e = data?.entry
  if (!e) return null
  return (
    <Link
      to={cancoUrl({
        cancoSlug: e.canco?.slug,
        artistaSlug: e.artista?.slug,
        albumSlug: e.album?.slug,
      })}
      className="block bg-tq-ink text-white rounded-lg p-3 shadow-md hover:shadow-lg transition-shadow"
    >
      <p className="text-[10px] uppercase tracking-widest text-tq-yellow mb-2">
        Cançó destacada de la setmana
      </p>
      {e.album?.imatge_url ? (
        <img
          src={e.album.imatge_url}
          alt=""
          className="w-full aspect-square object-cover rounded-md"
        />
      ) : (
        <div className="w-full aspect-square rounded-md" style={{ background: 'var(--mm-color-gray-700)' }} />
      )}
      <span
        className="inline-block mt-2.5 text-[10px] uppercase tracking-widest font-semibold px-2 py-0.5 rounded"
        style={{ backgroundColor: 'var(--color-tq-yellow)', color: 'var(--color-tq-ink)' }}
      >
        #{e.posicio} · puja {e.delta}
      </span>
      <h3 className="text-base font-bold font-display mt-1.5 leading-tight">
        {e.canco?.nom}
      </h3>
      <p className="text-xs text-white/70 mt-0.5">{e.artista?.nom}</p>
    </Link>
  )
}

/* Combined section: 2/3 top (5+5) + 1/3 destacada card. */
function TopAndAsidesSection() {
  return (
    <Section tone="white">
      <SectionHeader kicker="Aquesta setmana" title="Top global">
        Les 10 primeres posicions del top global publicat el passat
        dissabte.
      </SectionHeader>
      <div className="grid lg:grid-cols-3 gap-4 lg:gap-6">
        <div className="lg:col-span-2 min-w-0">
          <TopList5x5 />
        </div>
        <aside className="min-w-0">
          <CancoDestacadaCard />
        </aside>
      </div>
    </Section>
  )
}

/* ── Section 6 · Últims llançaments ────────────────────────────────── */

function fmtMes(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('ca-ES', { month: 'long', year: 'numeric' })
}

function LlancamentsGrid() {
  const { data } = useApi(
    '/albums/?ordering=-data_llancament&amb_verificades=true&limit=10',
  )
  const items = data?.results || []
  if (items.length === 0) return null
  return (
    <ul className="grid grid-cols-2 sm:grid-cols-5 gap-3">
      {items.map(a => (
        <li key={a.pk}>
          <Link
            to={albumUrl({ albumSlug: a.slug, artistaSlug: a.artista?.slug })}
            className="block group"
          >
            {a.imatge_url ? (
              <img
                src={a.imatge_url}
                alt=""
                loading="lazy"
                className="aspect-square w-full object-cover rounded-md group-hover:scale-[1.02] transition-transform"
              />
            ) : (
              <div className="aspect-square w-full rounded-md" style={{ background: 'var(--mm-color-gray-700)' }} />
            )}
            <p className="mt-1.5 text-xs font-semibold truncate">{a.nom}</p>
            <p className="text-[11px] text-white/60 truncate">{a.artista?.nom}</p>
            <p className="text-[10px] text-white/60 mt-0.5">{fmtMes(a.data_llancament)}</p>
          </Link>
        </li>
      ))}
    </ul>
  )
}

/* ── Section 4 · Artistes en descoberta (aside) ────────────────────── */

/* Right-column companion to LlancamentsGrid. Image-led tiles, same
 * square cover size as the album tiles so the two halves feel
 * visually balanced. 3 entries on top of each other. */
function DescobertaColumn() {
  // 4 entries → 2×2 on desktop, matching the album cover size.
  const { data } = useApi('/artistes/descoberta/?limit=4')
  const items = data?.results || []
  if (items.length === 0) return null
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-tq-yellow mb-2">
        Artistes a descobrir
      </p>
      <ul className="grid grid-cols-4 lg:grid-cols-2 gap-3">
        {items.map(a => (
          <li key={a.pk}>
            <Link
              to={artistaUrl(a.slug)}
              className="block group"
            >
              <img
                src={a.imatge_url}
                alt=""
                loading="lazy"
                className="aspect-square w-full object-cover rounded-md group-hover:scale-[1.02] transition-transform"
              />
              <p className="mt-1.5 text-xs font-semibold truncate group-hover:underline">{a.nom}</p>
              <div className="flex flex-wrap gap-1 mt-0.5 text-[10px] text-white/75">
                {/* On the ink band the brand TERR_COLORS go too dark
                    to pass WCAG (e.g. CAT amber on tq-ink ≈ 3:1).
                    We drop to white/75 (~12:1) for the text and
                    keep the territory shape (icon) visible. */}
                {a.territoris.slice(0, 2).map(t => (
                  <span key={t} className="inline-flex items-center gap-0.5">
                    <TerritoriBadge codi={t} className="h-3 w-3" />
                    {TERRITORI_NOM[t] || t}
                  </span>
                ))}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* Combined section: 2/3 album grid (5+5) + 1/3 discovery (2×2).
 * Both columns get a same-level kicker header inside the grid so the
 * two labels ("Acabats de publicar" / "Artistes a descobrir") share
 * a single baseline — used to drift apart vertically because the
 * left label was at section-header level and the right one at column
 * level. */
function LlancamentsAndDescobertaSection() {
  return (
    <Section tone="ink">
      <div className="grid lg:grid-cols-[2fr_1fr] gap-4 lg:gap-6">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-widest text-tq-yellow mb-2">
            Acabats de publicar
          </p>
          <LlancamentsGrid />
        </div>
        <aside className="min-w-0">
          <DescobertaColumn />
        </aside>
      </div>
    </Section>
  )
}

/* ── Section 8 · Territori en focus ────────────────────────────────── */

// ISO week number (1..53) for a given date — pure JS, no deps.
function isoWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  const dayNum = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7)
}

function TerritoriFocusSection() {
  const focusCodi = useMemo(
    () => FOCUS_TERRITORIS[isoWeek(new Date()) % FOCUS_TERRITORIS.length],
    [],
  )
  // Two parallel hook calls keyed off focusCodi — both refetch on
  // territory change, both reset to null while loading (handled by
  // useApi's path-keyed reset).
  const { data: topData } = useApi(
    `/top/?territori=${focusCodi}&oficial=true&limit=3`,
  )
  const { data: artistesPage } = useApi(
    `/artistes/?territori=${focusCodi}&per_page=1`,
  )
  const count = artistesPage?.total ?? null

  const color = TERR_COLORS[focusCodi]
  const entries = topData?.entries || []

  return (
    <Section tone="ink">
      <SectionHeader kicker="Aquesta setmana mirem cap a" title={`Focus · ${TERRITORI_NOM[focusCodi]}`}>
        Cada setmana ressaltem un territori. Aquí, el seu top i la
        seva activitat.
      </SectionHeader>
      <div className="grid grid-cols-1 md:grid-cols-[160px_1fr] gap-4 items-start">
        <div
          className="rounded-lg p-4 flex flex-col items-center justify-center text-center text-white"
          style={{ backgroundColor: color }}
        >
          <TerritoriBadge codi={focusCodi} className="h-14 w-14" />
          <p className="mt-2 font-bold font-display text-base">{TERRITORI_NOM[focusCodi]}</p>
          {count != null && (
            // Full opacity on the colored tile — `opacity-80` over the
            // brand colours pushed white below 4.5:1 on red/orange/etc.
            <p className="text-[11px] mt-0.5 text-white">
              {count.toLocaleString('ca-ES')} {count === 1 ? 'artista' : 'artistes'}
            </p>
          )}
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-white/60 mb-2">
            Top d'aquesta setmana
          </p>
          {entries.length === 0 && (
            <p className="text-sm text-white/60 italic">Encara no hi ha top per a aquest territori.</p>
          )}
          <ol className="space-y-1">
            {entries.map(e => (
              <li key={e.posicio}>
                <Link
                  to={cancoUrl({
                    cancoSlug: e.canco?.slug,
                    artistaSlug: e.artista?.slug,
                    albumSlug: e.album?.slug,
                  })}
                  className="flex items-center gap-2.5 hover:opacity-80 transition-opacity"
                >
                  <span
                    className="w-6 text-center text-lg font-bold font-display tabular-nums"
                    style={{ color }}
                  >
                    {e.posicio}
                  </span>
                  <span className="text-sm font-semibold truncate">{e.canco?.nom}</span>
                  <span className="text-xs text-white/60 truncate">— {e.artista?.nom}</span>
                </Link>
              </li>
            ))}
          </ol>
          <p className="mt-3">
            {/* Brand TERR_COLORS were tuned for white surfaces; on
                tq-ink several drop below the 4.5:1 normal-text
                threshold (e.g. VAL red ≈ 3.3:1). Use the brand
                yellow (~9:1 on ink) which is the correct accent
                for ink bands anyway. */}
            <Link
              to={`/artistes?territori=${focusCodi}`}
              className="text-xs font-semibold underline text-tq-yellow hover:text-white transition-colors"
            >
              Explora els artistes de {TERRITORI_NOM[focusCodi]} →
            </Link>
          </p>
        </div>
      </div>
    </Section>
  )
}

/* ── Section 9 · Notícies i comunitat (auth only) ──────────────────── */

/* Pull the first markdown image from a post body. Returns null when
 * none. We render whatever the author embedded, scaled to fit the
 * post tile — no separate "cover" field on Publicacio. */
function firstImageInMarkdown(md) {
  if (!md) return null
  const m = md.match(/!\[[^\]]*\]\(([^\s)]+)/)
  return m ? m[1] : null
}

function NoticiaTile({ p }) {
  const cover = firstImageInMarkdown(p.cos)
  const cosNet = (p.cos || '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')      // strip image syntax
    .replace(/[#*_>`-]/g, '')
    .trim()
  return (
    <Link
      to={`/comunitat/${p.pk}`}
      className="block p-3 border border-tq-ink/10 rounded-md hover:border-tq-ink/30 transition-colors h-full"
    >
      {cover && (
        <img
          src={cover}
          alt=""
          loading="lazy"
          className="w-full aspect-[16/9] object-cover rounded mb-2"
        />
      )}
      <h3 className="font-bold font-display text-base">{p.titol}</h3>
      <p className="text-xs text-tq-ink/60 mt-0.5">
        per {p.autor?.nom_public}
        {p.publicat_at && ` · ${p.publicat_at.slice(0, 10)}`}
      </p>
      {cosNet && (
        <p className="text-sm text-tq-ink/75 mt-1.5 line-clamp-2">
          {cosNet.slice(0, 100)}{cosNet.length > 100 ? '…' : ''}
        </p>
      )}
    </Link>
  )
}

function NoticiesColumn({ kicker, items }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-tq-ink/60 mb-2">
        {kicker}
      </p>
      {items === null ? (
        <p className="text-sm text-tq-ink/40 italic">Carregant…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-tq-ink/60 italic">Sense publicacions ara mateix.</p>
      ) : (
        <ul className="space-y-2">
          {items.map(p => <li key={p.pk}><NoticiaTile p={p} /></li>)}
        </ul>
      )}
    </div>
  )
}

/* Anonymous-visitor card that takes the place of the "Internes"
 * column. Doubles as a registration funnel — the internal feed is
 * registered-only by definition so this is the natural CTA spot. */
function RegistreCTACard() {
  return (
    <Link
      to="/compte/accedir?mode=registre"
      className="block bg-tq-ink text-white rounded-md p-5 hover:bg-tq-ink/90 transition-colors h-full"
    >
      <p className="text-[10px] uppercase tracking-widest text-tq-yellow mb-2">
        Comunitat
      </p>
      <p className="font-bold font-display text-lg leading-tight">
        Toques algun instrument i busques grup?
      </p>
      <p className="font-bold font-display text-lg leading-tight mt-1">
        Sou un grup i us falta algú?
      </p>
      <p className="text-sm text-white/80 mt-3 leading-relaxed">
        Registra't i troba la teua gent al directori i a les
        publicacions internes.
      </p>
      <span className="inline-block mt-4 text-xs font-semibold px-3 py-1.5 rounded bg-tq-yellow text-tq-ink">
        Registra't →
      </span>
    </Link>
  )
}

function NoticiesSection() {
  const { profile } = useAuth()
  // Authenticated path uses the unified internal endpoint (returns
  // drafts/pending too, filtered out below). Anonymous path can only
  // read publicacions-publiques (already filtered to published).
  const pubPath = profile
    ? '/comunitat/publicacions/?filtre=publiques&page=1'
    : '/comunitat/publicacions-publiques/?page=1'
  const internPath = profile
    ? '/comunitat/publicacions/?filtre=internes&page=1'
    : null
  const { data: pubData } = useApi(pubPath)
  const { data: internData } = useApi(internPath)
  const _filterPub = (rows) =>
    profile
      ? rows.filter((p) => p.estat === 'publicat').slice(0, 3)
      : rows.slice(0, 3)
  const pub = pubData ? _filterPub(pubData.results || []) : null
  const intern = profile
    ? internData
      ? (internData.results || [])
          .filter((p) => p.estat === 'publicat')
          .slice(0, 3)
      : null
    : []
  // For authenticated users we hide the section if both columns
  // end up empty. Anon visitors always see the section because the
  // CTA is a useful slot regardless.
  if (profile && pub !== null && intern !== null && pub.length === 0 && intern.length === 0) {
    return null
  }
  return (
    <Section tone="white">
      <SectionHeader kicker="Què es cou" title="De la comunitat">
        Les publicacions més recents de la nostra gent.
      </SectionHeader>
      <div className="grid md:grid-cols-2 gap-4">
        <NoticiesColumn kicker="Públiques" items={pub} />
        {profile ? (
          <NoticiesColumn kicker="Internes" items={intern} />
        ) : (
          <RegistreCTACard />
        )}
      </div>
      <p className="mt-3">
        <Link to="/comunitat" className="text-sm font-semibold underline hover:text-tq-yellow-deep transition-colors">
          Veure totes les notícies →
        </Link>
      </p>
    </Section>
  )
}

/* ── Section 10 · Compte enrere ────────────────────────────────────── */

/* Compute the next "Saturday at 09:00 local time" from `from`. If
 * we're already past Saturday 09:00 today, returns next Saturday. */
function nextSaturday9(from = new Date()) {
  const next = new Date(from)
  const dow = next.getDay() // 0=Sun..6=Sat
  let daysAhead = (6 - dow + 7) % 7
  next.setHours(9, 0, 0, 0)
  if (daysAhead === 0 && from.getTime() >= next.getTime()) {
    daysAhead = 7
  }
  next.setDate(next.getDate() + daysAhead)
  return next
}

/* Was the top of *this* week already published? True iff today is
 * Saturday and we've crossed 09:00. (Sunday onwards we're already
 * counting down to next Saturday, so it returns False.) */
function topPublishedToday(now = new Date()) {
  return now.getDay() === 6 && now.getHours() >= 9
}

function CompteEnrereSection() {
  // Tick every second so the seconds digit moves. Cheap re-render —
  // only this leaf component subscribes.
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  // One-shot: pull the "X cançons noves" indicator from the same
  // /stats/ payload the strip on top uses (cached 60 s on the server,
  // so the StatsSection above hits the same cache key on this page).
  const { data: stats } = useApi('/stats/')
  const novetatsCount = stats?.cancons_noves_setmana ?? null

  const published = topPublishedToday(now)
  const target = useMemo(() => nextSaturday9(now), [now])
  const ms = Math.max(0, target.getTime() - now.getTime())
  const totalSeconds = Math.floor(ms / 1000)
  const days    = Math.floor(totalSeconds / 86400)
  const hours   = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  return (
    <Section tone="ink" className="!py-0 !-my-0">
      <div className="-mx-6 lg:-mx-12 px-6 lg:px-12 py-8 md:py-10 bg-tq-yellow text-tq-ink">
        <div className="max-w-6xl mx-auto text-center">
          {published ? (
            <>
              <p className="text-[10px] uppercase tracking-widest text-tq-ink/70 mb-2">
                Avui mateix
              </p>
              <p className="text-3xl md:text-5xl font-bold font-display">
                Top publicat avui
              </p>
              <p className="text-sm text-tq-ink/70 mt-3">
                Torna el proper dissabte a les 9 h.
              </p>
            </>
          ) : (
            <>
              <p className="text-[10px] uppercase tracking-widest text-tq-ink/70 mb-1.5">
                Proper top: dissabte a les 9 h
              </p>
              {/* Five equal-sized cells: dies / hores / minuts /
                  segons + a non-time indicator (novetats this week).
                  Same font size and label treatment so the row reads
                  as a single block. */}
              <div
                className="grid grid-cols-2 sm:grid-cols-5 gap-3 max-w-4xl mx-auto"
                aria-live="off"
              >
                <CountdownCell n={days} label={days === 1 ? 'dia' : 'dies'} />
                <CountdownCell n={hours} label={hours === 1 ? 'hora' : 'hores'} />
                <CountdownCell n={minutes} label={minutes === 1 ? 'minut' : 'minuts'} />
                <CountdownCell n={seconds} label={seconds === 1 ? 'segon' : 'segons'} />
                {/* Non-time indicator picked out in mm-color-blue
                    (~9:1 on yellow) so the eye treats it as a
                    distinct piece of info, not part of the clock. */}
                <CountdownCell
                  n={novetatsCount ?? 0}
                  label={novetatsCount === 1 ? 'cançó nova' : 'cançons noves'}
                  color="var(--mm-color-blue)"
                />
              </div>
            </>
          )}
        </div>
      </div>
    </Section>
  )
}

function CountdownCell({ n, label, color }) {
  // `color` overrides both the number AND the label so the cell
  // reads as a unit. Default colour is the page's ink-on-yellow.
  const style = color ? { color } : undefined
  return (
    <div>
      <p
        className="text-3xl md:text-5xl font-bold font-display tabular-nums leading-none"
        style={style}
      >
        {String(n).padStart(2, '0')}
      </p>
      <p
        className={
          'text-[10px] md:text-xs uppercase tracking-widest mt-1.5 ' +
          (color ? '' : 'text-tq-ink/70')
        }
        style={style}
      >
        {label}
      </p>
    </div>
  )
}

/* ── Page ──────────────────────────────────────────────────────────── */

export default function HomePage() {
  // Old yellow body theme is gone — the page now drives its own
  // alternating ink/white bands from within.
  useEffect(() => {
    document.body.removeAttribute('data-theme')
  }, [])

  return (
    <div className="space-y-0">
      <SeoHead entity="homepage" />
      <HeroSection />
      <StatsSection />
      <TopAndAsidesSection />
      <LlancamentsAndDescobertaSection />
      <TerritoriFocusSection />
      <NoticiesSection />
      <CompteEnrereSection />
    </div>
  )
}
