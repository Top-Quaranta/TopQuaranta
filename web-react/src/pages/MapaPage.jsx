/**
 * MapaPage — /mapa
 *
 * SVG map of the Països Catalans. Three drill-down levels:
 *   1. Territoris  (paisos.json)                → click → comarca
 *   2. Comarques   (comarques-<CODI>.json)      → click → municipi
 *   3. Municipis   (municipis-<CODI>.json)      → click → list of artistes
 *
 * Left: the map itself (SVG, equirectangular projection, no tiles).
 * Right: a sticky panel with the current level's KPIs, or — at municipi
 * level when one is selected — the list of artistes living there.
 *
 * Colouring: coropleta groc-clar → tq-yellow segons n_artistes.
 * Non-PPCC artistes (localitat_manual without municipi) are skipped by
 * the backend, so they never affect the map.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Section } from '../components/editorial'
import { SeoHead } from '../lib/seoHead'
import { deezerImg } from '../lib/img'
import useApi from '../hooks/useApi'

const TERRITORI_NOM = {
  CAT: 'Catalunya',
  VAL: 'País Valencià',
  BAL: 'Illes Balears',
  AND: 'Andorra',
  CNO: 'Catalunya del Nord',
  FRA: 'Franja de Ponent',
  ALG: "L'Alguer",
  CAR: 'El Carxe',
}

// Fetch a static GeoJSON from /public/geodata/.
function useGeoJSON(path) {
  const [data, setData] = useState(null)
  useEffect(() => {
    let cancelled = false
    setData(null)
    fetch(path).then(r => r.json()).then(j => { if (!cancelled) setData(j) }).catch(() => {})
    return () => { cancelled = true }
  }, [path])
  return data
}

// Compute bounds from a FeatureCollection. Returns null if empty.
function boundsFromGeoJSON(gj) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  function walk(coords) {
    if (typeof coords[0] === 'number') {
      const [x, y] = coords
      if (x < minX) minX = x; if (x > maxX) maxX = x
      if (y < minY) minY = y; if (y > maxY) maxY = y
    } else {
      for (const c of coords) walk(c)
    }
  }
  for (const ft of gj?.features || []) walk(ft.geometry.coordinates)
  if (!isFinite(minX)) return null
  return { minX, minY, maxX, maxY }
}

// Approximate centroid of a geometry: bbox centre of the largest ring.
// Good enough for text labels; no need for proper polygon centroid.
function centroidOf(geom) {
  const rings = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates
  let best = null, bestArea = -1
  for (const poly of rings) {
    const outer = poly[0] || []
    if (!outer.length) continue
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const [x, y] of outer) {
      if (x < minX) minX = x; if (x > maxX) maxX = x
      if (y < minY) minY = y; if (y > maxY) maxY = y
    }
    const area = (maxX - minX) * (maxY - minY)
    if (area > bestArea) { bestArea = area; best = { x: (minX + maxX) / 2, y: (minY + maxY) / 2 } }
  }
  return best
}

// Polygon / MultiPolygon → SVG "d". Y is negated so northern latitudes
// render on top.
function geometryToPath(geom) {
  const rings = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates
  const parts = []
  for (const poly of rings) {
    for (const ring of poly) {
      if (!ring.length) continue
      const [x0, y0] = ring[0]
      let d = `M${x0.toFixed(4)},${(-y0).toFixed(4)}`
      for (let i = 1; i < ring.length; i++) {
        const [x, y] = ring[i]
        d += `L${x.toFixed(4)},${(-y).toFixed(4)}`
      }
      d += 'Z'
      parts.push(d)
    }
  }
  return parts.join(' ')
}

// Linear mix between two hex colours, t in [0, 1].
function mix(a, b, t) {
  const ah = parseInt(a.slice(1), 16), bh = parseInt(b.slice(1), 16)
  const ar = (ah >> 16) & 0xff, ag = (ah >> 8) & 0xff, ab = ah & 0xff
  const br = (bh >> 16) & 0xff, bg = (bh >> 8) & 0xff, bb = bh & 0xff
  const r = Math.round(ar + (br - ar) * t)
  const g = Math.round(ag + (bg - ag) * t)
  const b2 = Math.round(ab + (bb - ab) * t)
  return `#${((r << 16) | (g << 8) | b2).toString(16).padStart(6, '0')}`
}

// Three-stop colour scale: cream → tq-yellow → orange → dark orange.
// sqrt mapping so small values surface instead of disappearing.
function colourFor(n, maxN) {
  if (!n || !maxN) return '#f5f1e4' // warm cream for empty regions
  const t = Math.min(1, Math.sqrt(n / maxN))
  if (t < 0.5) {
    return mix('#fde68a', '#facc15', t / 0.5)       // pale yellow → yellow
  }
  return mix('#f97316', '#9a3412', (t - 0.5) / 0.5) // orange → dark brick
}

// L'Alguer sits in Sardinia, ~8°E, too far to include with the rest
// of PPCC without ~60% empty sea. At the overview level we render it
// separately in a top-right inset (mimicking how Canaries are drawn
// on maps of Spain). Drilled-in levels show it at its real position.

// L'Alguer inset: dedicated mini-SVG pinned to the top-right corner of
// the map container, with a short "separator" hint so it's visually
// understood as an out-of-frame addition (Canaries-style).
function AlgerInset({ feature, stats, maxN, selected, hovered, onHover, onClick }) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  function walk(c) {
    if (typeof c[0] === 'number') {
      if (c[0] < minX) minX = c[0]; if (c[0] > maxX) maxX = c[0]
      if (c[1] < minY) minY = c[1]; if (c[1] > maxY) maxY = c[1]
    } else { for (const x of c) walk(x) }
  }
  walk(feature.geometry.coordinates)
  const pad = 0.02
  const vb = `${minX - pad} ${-maxY - pad} ${maxX - minX + 2 * pad} ${maxY - minY + 2 * pad}`
  const n = stats?.n_artistes || 0
  const fill = colourFor(n, maxN)
  return (
    <div
      className="absolute top-3 right-3 w-28 bg-white/80 backdrop-blur rounded border border-tq-ink/20 shadow-sm"
      style={{ zIndex: 5 }}
    >
      <svg viewBox={vb} xmlns="http://www.w3.org/2000/svg" className="w-full h-auto">
        <path
          d={geometryToPath(feature.geometry)}
          fill={fill}
          stroke={selected ? '#0a0a0a' : '#9ca3af'}
          strokeWidth={selected ? 1.5 : 0.5}
          opacity={hovered ? 0.85 : 1}
          onMouseEnter={() => onHover('ALG')}
          onMouseLeave={() => onHover(null)}
          onClick={onClick}
          style={{ cursor: 'pointer', vectorEffect: 'non-scaling-stroke' }}
        />
      </svg>
      <div className="border-t border-tq-ink/10 px-2 py-1 text-[10px] font-semibold text-tq-ink/80 text-center">
        L'Alguer
      </div>
    </div>
  )
}

function KPI({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-tq-ink/60">{label}</div>
      <div className="text-xl font-bold font-display">{value.toLocaleString('ca')}</div>
    </div>
  )
}

function totals(stats) {
  return stats.reduce(
    (acc, r) => ({
      n_artistes: acc.n_artistes + (r.n_artistes || 0),
      n_albums:   acc.n_albums + (r.n_albums || 0),
      n_cancons:  acc.n_cancons + (r.n_cancons || 0),
      n_ranking:  acc.n_ranking + (r.n_ranking || 0),
    }),
    { n_artistes: 0, n_albums: 0, n_cancons: 0, n_ranking: 0 },
  )
}

export default function MapaPage() {
  const [selTerritori, setSelTerritori] = useState(null) // codi
  const [selComarca,   setSelComarca]   = useState(null) // name
  const [selMunicipi,  setSelMunicipi]  = useState(null) // { codi, comarca, municipi }

  const level =
    selComarca  ? 'municipi' :
    selTerritori ? 'comarca' :
    'territori'

  const geoPath =
    selComarca  ? `/geodata/municipis-${selTerritori}.json` :
    selTerritori ? `/geodata/comarques-${selTerritori}.json` :
    '/geodata/paisos.json'

  const gj = useGeoJSON(geoPath)

  // useApi-keyed path: stats refetch automatically when level /
  // selTerritori / selComarca change, with cancellation on unmount
  // and on path change.
  const _statsP = new URLSearchParams({ level })
  if (selTerritori && level !== 'territori') _statsP.set('parent', selTerritori)
  if (selComarca && level === 'municipi') {
    _statsP.set('parent', selComarca)
    _statsP.set('territori', selTerritori)
  }
  const { data: statsRaw } = useApi(`/mapa/stats/?${_statsP}`)
  const stats = statsRaw || []

  useEffect(() => {
    // K1 analytics: count drill-downs per level so we can see if the
    // audience uses the comarca / municipi tiers or stays at the
    // territori overview. dim1 is the resulting level after the
    // selection change.
    import('../lib/analytics').then(({ trackEvent }) =>
      trackEvent('mapa_zoom', level)
    )
  }, [level, selTerritori, selComarca])

  function keyForFeature(ft) {
    const props = ft.properties || {}
    if (level === 'territori') return props.codi
    if (level === 'comarca')   return `${props.codi}::${props.comarca}`
    return `${props.codi}::${props.comarca}::${props.municipi}`
  }

  const statsByKey = useMemo(() => {
    const m = {}
    for (const r of stats) {
      let k
      if (level === 'territori')     k = r.codi
      else if (level === 'comarca')  k = `${r.codi}::${r.comarca}`
      else                           k = `${r.codi}::${r.comarca}::${r.municipi}`
      m[k] = r
    }
    return m
  }, [stats, level])

  const maxN = useMemo(() => {
    let m = 0
    for (const r of stats) if (r.n_artistes > m) m = r.n_artistes
    return m
  }, [stats])

  // Filter features shown to the parent selection (municipis within a
  // single comarca; comarques within one territori).
  const features = useMemo(() => {
    if (!gj) return []
    let feats = gj.features
    if (level === 'comarca' && selTerritori) {
      feats = feats.filter(ft => ft.properties.codi === selTerritori)
    } else if (level === 'municipi' && selComarca) {
      feats = feats.filter(ft => ft.properties.comarca === selComarca)
    }
    // At the PPCC overview, peel L'Alguer out of the main map — it
    // renders in a dedicated inset at the top-right corner instead.
    if (level === 'territori') {
      feats = feats.filter(ft => ft.properties.codi !== 'ALG')
    }
    return feats
  }, [gj, level, selTerritori, selComarca])

  // L'Alguer feature for the inset (only at territori level).
  const algFeature = useMemo(() => {
    if (level !== 'territori' || !gj) return null
    return gj.features.find(ft => ft.properties.codi === 'ALG') || null
  }, [gj, level])

  const featureBounds = useMemo(
    () => (features.length ? boundsFromGeoJSON({ features }) : null),
    [features],
  )

  const [hovered, setHovered] = useState(null)

  function onFeatureClick(ft) {
    const props = ft.properties || {}
    if (level === 'territori') {
      setSelTerritori(props.codi)
    } else if (level === 'comarca') {
      setSelComarca(props.comarca)
    } else {
      setSelMunicipi({
        codi: props.codi,
        comarca: props.comarca,
        municipi: props.municipi,
      })
    }
  }

  function goUp() {
    if (selMunicipi) setSelMunicipi(null)
    else if (selComarca) setSelComarca(null)
    else if (selTerritori) setSelTerritori(null)
  }

  const title =
    selMunicipi ? selMunicipi.municipi :
    selComarca  ? selComarca :
    selTerritori ? TERRITORI_NOM[selTerritori] :
    'Països Catalans'

  const subtitle =
    selMunicipi ? `${selMunicipi.comarca} · ${TERRITORI_NOM[selMunicipi.codi]}` :
    selComarca  ? TERRITORI_NOM[selTerritori] :
    selTerritori ? 'Territori' :
    'Mapa complet'

  // Top artistes for whatever region scope is active. Shown at every
  // level (PPCC by default, drilled-down when the user clicks into a
  // territori / comarca / municipi). Sorted by cumulative Last.fm
  // plays on the backend.
  // Artistes-top scoped to current selection. useApi handles
  // refetch + cancellation on every selection change.
  const _artP = new URLSearchParams({ limit: '60' })
  if (selMunicipi) {
    _artP.set('territori', selMunicipi.codi)
    _artP.set('comarca', selMunicipi.comarca)
    _artP.set('municipi', selMunicipi.municipi)
  } else if (selComarca && selTerritori) {
    _artP.set('territori', selTerritori)
    _artP.set('comarca', selComarca)
  } else if (selTerritori) {
    _artP.set('territori', selTerritori)
  }
  const { data: artistes } = useApi(`/mapa/artistes-top/?${_artP}`)

  // Which KPIs does the panel show?
  let kpi
  if (selMunicipi) {
    const k = `${selMunicipi.codi}::${selMunicipi.comarca}::${selMunicipi.municipi}`
    kpi = statsByKey[k] || { n_artistes: 0, n_albums: 0, n_cancons: 0, n_ranking: 0 }
  } else if (selComarca) {
    // We're at municipi level; stats already filtered to this comarca.
    kpi = totals(stats)
  } else if (selTerritori) {
    // We're at comarca level; stats filtered to territori.
    kpi = totals(stats)
  } else {
    kpi = totals(stats)
  }

  const showBackButton = !!selTerritori

  const viewBox = featureBounds
    ? (() => {
        const pad = Math.max(
          (featureBounds.maxX - featureBounds.minX) * 0.02,
          (featureBounds.maxY - featureBounds.minY) * 0.02,
          0.01,
        )
        const x = featureBounds.minX - pad
        const y = -featureBounds.maxY - pad
        const w = featureBounds.maxX - featureBounds.minX + 2 * pad
        const h = featureBounds.maxY - featureBounds.minY + 2 * pad
        return `${x} ${y} ${w} ${h}`
      })()
    : '0 0 10 10'

  return (
    <div className="space-y-0">
      <SeoHead entity="mapa" />
      {/* ── Hero band ───────────────────────────────────────────── */}
      <Section tone="ink">
        <p className="text-[10px] uppercase tracking-widest text-tq-yellow">
          Mapa
        </p>
        <h1 className="text-3xl md:text-5xl font-bold font-display mt-1.5 leading-tight">
          La música al territori
        </h1>
        <p className="text-sm md:text-base text-white/80 mt-3 max-w-2xl leading-relaxed">
          Fes clic a un territori per fer zoom a les seves comarques i,
          després, als municipis. Al panell lateral hi apareixen els
          artistes de la zona.
        </p>
      </Section>

      {/* ── Map + side panel band ───────────────────────────────── */}
      <Section tone="white">
        <div className="grid lg:grid-cols-[1fr_320px] gap-4">
        {/* ── Map ── */}
        <div
          className="relative rounded-lg border border-black/5 p-3 min-h-[500px]"
          style={{ background: 'linear-gradient(180deg, #eef2f7 0%, #f5f7fa 100%)' }}
        >
          {!gj && <p className="text-sm text-tq-ink/60 p-6 text-center">Carregant mapa…</p>}
          {gj && (
            <svg
              viewBox={viewBox}
              xmlns="http://www.w3.org/2000/svg"
              className="w-full h-auto max-h-[70vh]"
            >
              {features.map((ft, i) => {
                const k = keyForFeature(ft)
                const s = statsByKey[k]
                const n = s?.n_artistes || 0
                const fill = colourFor(n, maxN)
                const isHov = hovered === k
                const isSel =
                  (level === 'territori' && selTerritori === ft.properties.codi) ||
                  (level === 'comarca' && selComarca === ft.properties.comarca) ||
                  (level === 'municipi' && selMunicipi &&
                    selMunicipi.municipi === ft.properties.municipi &&
                    selMunicipi.comarca === ft.properties.comarca)
                return (
                  <path
                    key={k + '-' + i}
                    d={geometryToPath(ft.geometry)}
                    fill={fill}
                    stroke={isSel ? '#0a0a0a' : '#9ca3af'}
                    strokeWidth={isSel ? 1.5 : 0.5}
                    opacity={isHov ? 0.85 : 1}
                    onMouseEnter={() => setHovered(k)}
                    onMouseLeave={() => setHovered(null)}
                    onClick={() => onFeatureClick(ft)}
                    style={{ cursor: 'pointer', vectorEffect: 'non-scaling-stroke' }}
                  />
                )
              })}
              {/* No inline labels — the hover tooltip carries the name. */}
            </svg>
          )}

          {/* Hover tooltip — floats over the map at the top-left.
              Shown for all levels; at territori level labels are
              already painted but the tooltip adds the count. */}
          {hovered && (() => {
            const s = statsByKey[hovered]
            const parts = hovered.split('::')
            let name
            if (parts.length === 1) name = TERRITORI_NOM[parts[0]] || parts[0]
            else if (parts.length === 2) name = parts[1]
            else name = parts[2]
            return (
              <div
                className="absolute top-4 left-4 bg-tq-ink text-white rounded px-3 py-1.5 text-xs shadow-lg pointer-events-none"
                style={{ zIndex: 10 }}
              >
                <div className="font-semibold">{name}</div>
                {s && (
                  <div className="text-tq-yellow">
                    {s.n_artistes.toLocaleString('ca')} artistes
                  </div>
                )}
              </div>
            )
          })()}

          {/* L'Alguer inset — only at the PPCC overview. */}
          {level === 'territori' && algFeature && (
            <AlgerInset
              feature={algFeature}
              stats={statsByKey['ALG']}
              maxN={maxN}
              selected={selTerritori === 'ALG'}
              hovered={hovered === 'ALG'}
              onHover={setHovered}
              onClick={() => onFeatureClick(algFeature)}
            />
          )}
        </div>

        {/* ── Side panel ── */}
        <aside className="bg-white rounded-lg border border-black/5 p-4 text-tq-ink lg:sticky lg:top-4 h-fit">
          {showBackButton && (
            <button
              type="button"
              onClick={goUp}
              className="text-xs font-semibold text-tq-ink/70 hover:text-tq-ink mb-3"
            >
              ← Tornar
            </button>
          )}
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/60">{subtitle}</p>
          <h1 className="text-2xl font-bold font-display leading-tight mt-0.5 mb-4">
            {title}
          </h1>

          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="col-span-2">
              <div className="text-[10px] uppercase tracking-widest text-tq-ink/60">
                Artistes
              </div>
              <div className="text-4xl font-bold font-display text-tq-ink tabular-nums leading-none">
                {kpi.n_artistes.toLocaleString('ca')}
              </div>
            </div>
            <KPI label="Àlbums" value={kpi.n_albums} />
            <KPI label="Cançons" value={kpi.n_cancons} />
            <KPI label="Al ranking" value={kpi.n_ranking} />
          </div>

          {/* Top artistes grid — square thumbnails + name, sorted by
              cumulative Last.fm plays. Shown at every scope. */}
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-tq-ink/70 mb-2 mt-4">
              Artistes més escoltats
            </h2>
            {artistes === null && <p className="text-sm text-tq-ink/60">Carregant…</p>}
            {artistes && artistes.length === 0 && (
              <p className="text-sm text-tq-ink/60 italic">Sense artistes aquí.</p>
            )}
            {artistes && artistes.length > 0 && (
              <ul className="grid grid-cols-3 gap-2 max-h-[55vh] overflow-y-auto pr-1">
                {artistes.map(a => (
                  <li key={a.pk}>
                    <Link
                      to={`/artista/${a.slug}`}
                      className="block group"
                    >
                      <div className="aspect-square rounded overflow-hidden bg-tq-ink/5 relative">
                        {a.imatge_url ? (
                          <img
                            src={deezerImg(a.imatge_url, 250)}
                            alt=""
                            loading="lazy"
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-lg font-bold text-tq-ink/40">
                            {(a.nom || '?').slice(0, 2).toUpperCase()}
                          </div>
                        )}
                      </div>
                      <div className="mt-1 text-[11px] font-semibold leading-tight line-clamp-2 group-hover:text-tq-yellow-deep">
                        {a.nom}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {!selTerritori && (
            <p className="text-[11px] text-tq-ink/60 mt-4">
              Clica un territori al mapa per veure'n les comarques.
            </p>
          )}
          {selTerritori && !selComarca && (
            <p className="text-[11px] text-tq-ink/60 mt-4">
              Clica una comarca per veure'n els municipis.
            </p>
          )}
          {selComarca && !selMunicipi && (
            <p className="text-[11px] text-tq-ink/60 mt-4">
              Clica un municipi per veure'n els artistes.
            </p>
          )}
        </aside>
        </div>
      </Section>
    </div>
  )
}
