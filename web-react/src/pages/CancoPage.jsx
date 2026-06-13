/**
 * CancoPage — public track page (/canco/<slug>), redisseny web.
 *
 * Dark hero (territory glow) with the cover, Anton title, artist/album
 * links, metadata and streaming links. Body: the real ranking trajectory
 * (CancoChart, recharts) framed in a white data panel inside a glass card,
 * the algorithm-transparency panel, and the provisional callout.
 *
 * Reads /api/v1/cancons/<slug>/ (shape unchanged). The trajectory is the
 * REAL historial (not the prototype's sample curve). Cover component,
 * ExternalListenLinks, TopBreakdownPanel and FeedbackContext conserved.
 */
import { lazy, Suspense } from 'react'
import { Link, useParams } from 'react-router-dom'
import { albumUrl } from '../lib/urls'
import Cover from '../components/Cover'
import { useFeedbackTarget } from '../context/FeedbackContext'
import ExternalListenLinks from '../components/ExternalListenLinks'
import TopBreakdownPanel from '../components/TopBreakdownPanel'
import { SeoHead } from '../lib/seoHead'
import useApi from '../hooks/useApi'
import { Band, Glow, Glass, Kicker, Crit, TerrLogo } from '../components/rd/primitives'
import { terr } from '../components/rd/terr'

const CancoChart = lazy(() => import('../components/CancoChart'))

function formatDuration(ms) {
  if (!ms) return null
  const totalSeconds = Math.floor(ms / 1000)
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function CancoPage() {
  const params = useParams()
  const slug = params.cancoSlug || params.slug
  const { data, error, loading, reload } = useApi(`/cancons/${slug}/`, {
    mapError: (e) => (e.status === 404 ? 'Cançó no trobada.' : null),
  })

  useFeedbackTarget(
    data ? { targetType: 'canco', targetPk: data.pk, targetSlug: data.slug, targetLabel: data.nom } : null,
  )

  if (loading) {
    return (
      <Band tone="top-hero">
        <div className="rd-cc-hero">
          <div className="rd-cc-tile" style={{ background: 'rgba(255,255,255,0.06)' }} />
          <div className="flex-1"><div style={{ height: 48, width: '60%', background: 'rgba(255,255,255,0.06)', borderRadius: 8 }} /></div>
        </div>
      </Band>
    )
  }
  if (error) {
    return (
      <Band tone="ink2">
        <Glass className="p-6 text-center max-w-xl mx-auto">
          <p className="text-white/80">{error}</p>
          <button type="button" onClick={reload} className="rd-btn rd-btn--ghost mt-3">Reintentar</button>
        </Glass>
      </Band>
    )
  }
  if (!data) return null

  const dur = formatDuration(data.durada_ms)
  const prov = data.provisional || []

  return (
    <>
      <SeoHead entity="canco" slug={slug} />

      <Band tone="top-hero">
        <Glow variant="a" />
        <div className="rd-cc-hero">
          {data.album?.imatge_url ? (
            <Cover
              entitat="album" deezerId={data.album?.deezer_id} imatgeUrl={data.album.imatge_url}
              alt={data.album?.nom ? `Portada de ${data.album.nom}` : ''} size={500} priority
              className="rd-cc-tile" style={{ objectFit: 'cover' }}
            />
          ) : (
            <div className="rd-cc-tile" style={{ background: '#1b1a22' }} />
          )}
          <div className="min-w-0 flex-1">
            <Kicker color="var(--color-tq-yellow)">cançó</Kicker>
            <Crit as="h1" className="rd-cc-title">{data.nom}</Crit>
            {data.artista && (
              <p className="text-lg" style={{ margin: '2px 0 0' }}>
                <Link to={`/artista/${data.artista.slug}`} className="rd-cc-artist">{data.artista.nom}</Link>
                {data.artistes_col?.length > 0 && (
                  <span className="text-white/55 text-sm"> amb {data.artistes_col.map((col, j) => (
                    <span key={col.slug}>{j > 0 ? ', ' : ''}<Link to={`/artista/${col.slug}`} className="underline hover:text-white">{col.nom}</Link></span>
                  ))}</span>
                )}
              </p>
            )}
            {data.album && (
              <p className="rd-cc-album" style={{ marginTop: 7 }}>
                de l'àlbum «<Link to={albumUrl({ albumSlug: data.album.slug, artistaSlug: data.artista?.slug })} className="underline hover:text-white" style={{ color: 'inherit' }}>{data.album.nom}</Link>»
              </p>
            )}

            {prov.length > 0 && (
              <div className="rd-cc-badges">
                {prov.map(p => (
                  <span key={p.territori} className="rd-cc-pos rd-glass">
                    <span style={{ fontFamily: 'var(--font-crit)', fontSize: 22, color: 'var(--color-tq-yellow)' }}>#{p.posicio}</span>
                    <TerrLogo code={p.territori} className="h-4 w-4" />
                    <em style={{ color: terr(p.territori).accent }}>{terr(p.territori).short}</em>
                  </span>
                ))}
              </div>
            )}

            <p className="text-xs text-white/50 mt-3 flex flex-wrap gap-x-3">
              {dur && <span>{dur}</span>}
              {data.isrc && <span>ISRC: {data.isrc}</span>}
              {data.data_llancament && <span>Publicada: {data.data_llancament}</span>}
            </p>

            <ExternalListenLinks
              className="rd-cc-links" kind="canco" title={data.nom}
              artist={data.artista?.nom} deezerId={data.deezer_id} isrc={data.isrc}
            />
          </div>
        </div>
      </Band>

      <Band tone="ink2">
        <div className="flex flex-col gap-4 max-w-4xl">
          <TopBreakdownPanel slug={data.slug} />

          {data.historial?.length > 0 ? (
            <Glass className="rd-cc-card">
              <Kicker color="var(--color-tq-yellow)">posició per setmana</Kicker>
              <Crit as="h2" className="rd-cc-h2">TRAJECTÒRIA AL TOP</Crit>
              <p className="text-xs text-white/50 mt-1 mb-3">Més baix és millor (1 = el cim).</p>
              <div className="rd-chart-panel">
                <div className="w-full h-72">
                  <Suspense fallback={<div className="w-full h-full bg-black/5 rounded animate-pulse" />}>
                    <CancoChart historial={data.historial} territoris={data.territoris_historial} />
                  </Suspense>
                </div>
              </div>
            </Glass>
          ) : prov.length === 0 ? (
            <p className="rd-empty">Aquesta cançó encara no ha aparegut a cap top.</p>
          ) : null}
        </div>
      </Band>
    </>
  )
}
