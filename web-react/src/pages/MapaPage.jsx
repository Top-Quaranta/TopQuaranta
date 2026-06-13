/**
 * MapaPage — /mapa (redisseny web).
 *
 * SVG map of the Països Catalans, three drill-down levels (territori →
 * comarca → municipi). The geometry/drill-down logic is unchanged; the
 * chrome is the network-kit dark-glass language and the choropleth now
 * fills each region with its territori `deep`, lightened by artist
 * density (so the colour still carries the count). Strokes are white-α;
 * the selection gets a yellow stroke. L'Alguer keeps its top-right inset.
 *
 * Data: static GeoJSON in /public/geodata/ + /mapa/stats/ +
 * /mapa/artistes-top/ (contracts unchanged). `municipis-CAT.json` may be
 * absent → handled as an explicit empty state, never an error.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Band, Glow, Glass, Kicker, Crit, TerrLogo } from '../components/rd/primitives'
import { terr, shade } from '../components/rd/terr'
import { SeoHead } from '../lib/seoHead'
import { deezerImg } from '../lib/img'
import useApi from '../hooks/useApi'

const TERRITORI_NOM = {
  CAT: 'Catalunya', VAL: 'País Valencià', BAL: 'Illes Balears', AND: 'Andorra',
  CNO: 'Catalunya del Nord', FRA: 'Franja de Ponent', ALG: "L'Alguer", CAR: 'El Carxe',
}

function useGeoJSON(path) {
  const [data, setData] = useState(null)
  useEffect(() => {
    let cancelled = false
    // Clear stale geometry before the new fetch (intended).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setData(null)
    fetch(path).then(r => r.json()).then(j => { if (!cancelled) setData(j) }).catch(() => {})
    return () => { cancelled = true }
  }, [path])
  return data
}

function boundsFromGeoJSON(gj) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  function walk(coords) {
    if (typeof coords[0] === 'number') {
      const [x, y] = coords
      if (x < minX) minX = x; if (x > maxX) maxX = x
      if (y < minY) minY = y; if (y > maxY) maxY = y
    } else { for (const c of coords) walk(c) }
  }
  for (const ft of gj?.features || []) walk(ft.geometry.coordinates)
  if (!isFinite(minX)) return null
  return { minX, minY, maxX, maxY }
}

// Polygon / MultiPolygon → SVG "d". Y is negated so north renders on top.
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

// Fill = the region's territori `deep`, lightened toward white by artist
// density (sqrt so small counts still surface). Keeps the territory
// colour identity while still reading as a choropleth.
function fillFor(codi, n, maxN) {
  const deep = terr(codi).deep
  if (!maxN || !n) return shade(deep, 0.02)
  const frac = Math.min(1, Math.sqrt(n / maxN))
  return shade(deep, 0.04 + 0.44 * frac)
}

const STROKE = 'rgba(255,255,255,0.28)'
const STROKE_SEL = '#facc15'

// L'Alguer (Sardinia) renders in a top-right inset at the overview level.
function AlgerInset({ feature, n, maxN, selected, hovered, onHover, onClick }) {
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
  return (
    <div className="rd-map-inset rd-glass">
      <svg viewBox={vb} xmlns="http://www.w3.org/2000/svg" className="w-full h-auto">
        <path
          d={geometryToPath(feature.geometry)}
          fill={fillFor('ALG', n, maxN)}
          stroke={selected ? STROKE_SEL : STROKE}
          strokeWidth={selected ? 1.4 : 0.6}
          opacity={hovered ? 0.85 : 1}
          onMouseEnter={() => onHover('ALG')}
          onMouseLeave={() => onHover(null)}
          onClick={onClick}
          style={{ cursor: 'pointer', vectorEffect: 'non-scaling-stroke' }}
        />
      </svg>
      <span className="rd-map-inset-label">L'Alguer</span>
    </div>
  )
}

function Kpi({ label, value }) {
  return (
    <div className="rd-kpi">
      <span className="rd-kpi-n">{value.toLocaleString('ca')}</span>
      <span className="rd-kpi-l">{label}</span>
    </div>
  )
}

function totals(stats) {
  return stats.reduce(
    (acc, r) => ({
      n_artistes: acc.n_artistes + (r.n_artistes || 0),
      n_albums: acc.n_albums + (r.n_albums || 0),
      n_cancons: acc.n_cancons + (r.n_cancons || 0),
      n_ranking: acc.n_ranking + (r.n_ranking || 0),
    }),
    { n_artistes: 0, n_albums: 0, n_cancons: 0, n_ranking: 0 },
  )
}

export default function MapaPage() {
  const [selTerritori, setSelTerritori] = useState(null)
  const [selComarca, setSelComarca] = useState(null)
  const [selMunicipi, setSelMunicipi] = useState(null)
  const [hovered, setHovered] = useState(null)

  const level = selComarca ? 'municipi' : selTerritori ? 'comarca' : 'territori'
  const geoPath =
    selComarca ? `/geodata/municipis-${selTerritori}.json` :
    selTerritori ? `/geodata/comarques-${selTerritori}.json` :
    '/geodata/paisos.json'
  const gj = useGeoJSON(geoPath)

  const _statsP = new URLSearchParams({ level })
  if (selTerritori && level !== 'territori') _statsP.set('parent', selTerritori)
  if (selComarca) { _statsP.set('parent', selComarca); _statsP.set('territori', selTerritori) }
  const { data: statsRaw } = useApi(`/mapa/stats/?${_statsP}`)
  const stats = useMemo(() => statsRaw || [], [statsRaw])

  function keyForFeature(ft) {
    const p = ft.properties || {}
    if (level === 'territori') return p.codi
    if (level === 'comarca') return p.comarca
    return `${p.codi}::${p.comarca}::${p.municipi}`
  }

  const statsByKey = useMemo(() => {
    const m = {}
    for (const r of stats) {
      if (level === 'territori') m[r.territori] = r
      else if (level === 'comarca') m[r.comarca] = r
      else m[`${r.territori}::${r.comarca}::${r.municipi}`] = r
    }
    return m
  }, [stats, level])

  const maxN = useMemo(() => {
    let m = 0
    for (const r of stats) if (r.n_artistes > m) m = r.n_artistes
    return m
  }, [stats])

  const features = useMemo(() => {
    let fs = gj?.features || []
    if (level === 'territori') fs = fs.filter(f => (f.properties?.codi) !== 'ALG')
    return fs
  }, [gj, level])

  const algFeature = useMemo(
    () => (level === 'territori' ? (gj?.features || []).find(f => f.properties?.codi === 'ALG') : null),
    [gj, level],
  )

  const featureBounds = useMemo(
    () => (features.length ? boundsFromGeoJSON({ features }) : null),
    [features],
  )

  function onFeatureClick(ft) {
    const props = ft.properties || {}
    if (level === 'territori') setSelTerritori(props.codi)
    else if (level === 'comarca') setSelComarca(props.comarca)
    else setSelMunicipi({ codi: props.codi, comarca: props.comarca, municipi: props.municipi })
  }
  function goUp() {
    if (selMunicipi) setSelMunicipi(null)
    else if (selComarca) setSelComarca(null)
    else if (selTerritori) setSelTerritori(null)
  }

  const titol =
    selMunicipi ? selMunicipi.municipi :
    selComarca ? selComarca :
    selTerritori ? TERRITORI_NOM[selTerritori] : 'Països Catalans'
  const subtitle =
    selMunicipi ? `${selMunicipi.comarca} · ${TERRITORI_NOM[selMunicipi.codi]}` :
    selComarca ? TERRITORI_NOM[selTerritori] :
    selTerritori ? 'Territori' : 'Mapa complet'
  const panelCode = selMunicipi?.codi || selTerritori || 'PPCC'

  const _artP = new URLSearchParams({ limit: '60' })
  if (selMunicipi) { _artP.set('territori', selMunicipi.codi); _artP.set('comarca', selMunicipi.comarca); _artP.set('municipi', selMunicipi.municipi) }
  else if (selComarca && selTerritori) { _artP.set('territori', selTerritori); _artP.set('comarca', selComarca) }
  else if (selTerritori) { _artP.set('territori', selTerritori) }
  const { data: artistes } = useApi(`/mapa/artistes-top/?${_artP}`)

  let kpi
  if (selMunicipi) {
    const k = `${selMunicipi.codi}::${selMunicipi.comarca}::${selMunicipi.municipi}`
    kpi = statsByKey[k] || { n_artistes: 0, n_albums: 0, n_cancons: 0, n_ranking: 0 }
  } else {
    kpi = totals(stats)
  }

  const viewBox = featureBounds
    ? (() => {
        const pad = Math.max((featureBounds.maxX - featureBounds.minX) * 0.02, (featureBounds.maxY - featureBounds.minY) * 0.02, 0.01)
        return `${featureBounds.minX - pad} ${-featureBounds.maxY - pad} ${featureBounds.maxX - featureBounds.minX + 2 * pad} ${featureBounds.maxY - featureBounds.minY + 2 * pad}`
      })()
    : '0 0 10 10'

  // `municipis-CAT.json` isn't in the repo → empty features at municipi
  // level. Surface it as an explicit note, never an error.
  const missingGeo = gj && features.length === 0 && level === 'municipi'

  return (
    <>
      <SeoHead entity="mapa" />

      <Band tone="top-hero">
        <Glow variant="a" />
        <Kicker className="block mb-2">deu territoris, una llengua</Kicker>
        <Crit as="h1" className="rd-top-h1">EL <span style={{ color: 'var(--color-tq-yellow)' }}>MAPA</span></Crit>
        <p className="rd-hero-sub">
          Fes clic a un territori per fer zoom a les comarques i, després, als
          municipis. Al panell hi surten els artistes de la zona.
        </p>
      </Band>

      <Band tone="ink2">
        <div className="rd-mapa-grid">
          <div className="rd-map-box rd-glass">
            {!gj && <p className="rd-empty" style={{ padding: 40, textAlign: 'center' }}>Carregant el mapa…</p>}
            {missingGeo && (
              <p className="rd-empty" style={{ padding: 40, textAlign: 'center' }}>
                Encara no tenim la geometria dels municipis d'aquest territori.
                Torna enrere per veure les comarques.
              </p>
            )}
            {gj && features.length > 0 && (
              <svg viewBox={viewBox} xmlns="http://www.w3.org/2000/svg" className="rd-map-svg">
                {features.map((ft, i) => {
                  const k = keyForFeature(ft)
                  const s = statsByKey[k]
                  const baseCode = level === 'territori' ? ft.properties.codi : selTerritori
                  const isSel =
                    (level === 'territori' && selTerritori === ft.properties.codi) ||
                    (level === 'comarca' && selComarca === ft.properties.comarca) ||
                    (level === 'municipi' && selMunicipi && selMunicipi.municipi === ft.properties.municipi && selMunicipi.comarca === ft.properties.comarca)
                  return (
                    <path
                      key={k + '-' + i}
                      d={geometryToPath(ft.geometry)}
                      fill={fillFor(baseCode, s?.n_artistes || 0, maxN)}
                      stroke={isSel ? STROKE_SEL : STROKE}
                      strokeWidth={isSel ? 1.4 : 0.6}
                      opacity={hovered === k ? 0.82 : 1}
                      onMouseEnter={() => setHovered(k)}
                      onMouseLeave={() => setHovered(null)}
                      onClick={() => onFeatureClick(ft)}
                      style={{ cursor: 'pointer', vectorEffect: 'non-scaling-stroke' }}
                    />
                  )
                })}
              </svg>
            )}

            {hovered && (() => {
              const s = statsByKey[hovered]
              const parts = hovered.split('::')
              const name = parts.length === 1 ? (TERRITORI_NOM[parts[0]] || parts[0]) : parts.length === 2 ? parts[1] : parts[2]
              return (
                <div className="rd-map-tip rd-glass">
                  <span className="rd-map-tip-name">{name}</span>
                  {s && <span className="rd-map-tip-sub">{s.n_artistes.toLocaleString('ca')} artistes</span>}
                </div>
              )
            })()}

            {level === 'territori' && algFeature && (
              <AlgerInset
                feature={algFeature} n={statsByKey['ALG']?.n_artistes || 0} maxN={maxN}
                selected={selTerritori === 'ALG'} hovered={hovered === 'ALG'}
                onHover={setHovered} onClick={() => onFeatureClick(algFeature)}
              />
            )}
          </div>

          <Glass as="aside" className="rd-mapa-detail">
            {!!selTerritori && (
              <button type="button" onClick={goUp} className="rd-map-back">← Tornar</button>
            )}
            <div className="rd-mapa-dhead">
              <TerrLogo code={panelCode} className="h-9 w-9" />
              <div className="min-w-0">
                <Kicker>{subtitle}</Kicker>
                <Crit as="h2" className="rd-mapa-dname">{titol}</Crit>
              </div>
            </div>

            <div className="rd-mapa-kpis">
              <Kpi label="Artistes" value={kpi.n_artistes} />
              <Kpi label="Àlbums" value={kpi.n_albums} />
              <Kpi label="Cançons" value={kpi.n_cancons} />
              <Kpi label="Al top" value={kpi.n_ranking} />
            </div>

            <Kicker className="block mb-2">artistes més escoltats</Kicker>
            {artistes === null && <p className="rd-empty">Carregant…</p>}
            {artistes && artistes.length === 0 && <p className="rd-empty">Sense artistes en aquesta zona.</p>}
            {artistes && artistes.length > 0 && (
              <ul className="rd-mapa-artistes">
                {artistes.map(a => (
                  <li key={a.pk}>
                    <Link to={`/artista/${a.slug}`} className="block group">
                      <div className="rd-mapa-artthumb">
                        {a.imatge_url ? (
                          <img src={deezerImg(a.imatge_url, 250)} alt="" loading="lazy" className="w-full h-full object-cover" />
                        ) : (
                          <span className="rd-mapa-artini">{(a.nom || '?').slice(0, 2).toUpperCase()}</span>
                        )}
                      </div>
                      <p className="rd-mapa-artname">{a.nom}</p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Glass>
        </div>
      </Band>
    </>
  )
}
