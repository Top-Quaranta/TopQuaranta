/**
 * CancoPage — public song profile with the full ranking history.
 *
 * Reads /api/v1/cancons/<pk>/ and renders:
 *   - Header: cover + title + artist + album link
 *   - Chart: per-territory ranking evolution (recharts LineChart,
 *     Y axis inverted since position 1 is the top)
 *   - Optional provisional-ranking callout
 *
 * The chart lines colour-match territory colors defined in HomePage
 * to keep the brand language consistent.
 */
import { lazy, Suspense } from 'react'
import { Link, useParams } from 'react-router-dom'
import Alert from '../components/ui/Alert'
import { albumUrl } from '../lib/urls'
import { deezerImg } from '../lib/img'
import { useFeedbackTarget } from '../context/FeedbackContext'
import ExternalListenLinks from '../components/ExternalListenLinks'
import TopBreakdownPanel from '../components/TopBreakdownPanel'
import { SeoHead } from '../lib/seoHead'
import useApi from '../hooks/useApi'
import { TERRITORI_NOM } from '../components/editorial'

// Lazy so recharts (~115 KB gz) stays out of the public entry bundle;
// it only loads when a song actually has a ranking history to chart.
const CancoChart = lazy(() => import('../components/CancoChart'))

function formatDuration(ms) {
  if (!ms) return '—'
  const totalSeconds = Math.floor(ms / 1000)
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function CancoPage() {
  // React Router hands us whichever params the matched route had:
  //   /canco/:slug                                      → slug
  //   /artista/:artistaSlug/:albumSlug/:cancoSlug       → cancoSlug
  // The leaf slug is the authoritative lookup in either case.
  const params = useParams()
  const slug = params.cancoSlug || params.slug
  const { data, error, loading } = useApi(`/cancons/${slug}/`, {
    mapError: (e) => (e.status === 404 ? 'Cançó no trobada.' : null),
  })

  useFeedbackTarget(
    data
      ? { targetType: 'canco', targetPk: data.pk, targetSlug: data.slug, targetLabel: data.nom }
      : null,
  )

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div className="h-60 bg-white/5 rounded-lg animate-pulse" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto">
        <Alert tone="danger">{error}</Alert>
      </div>
    )
  }

  if (!data) return null

  return (
    <article className="max-w-4xl mx-auto text-white space-y-6">
      <SeoHead entity="canco" slug={slug} />
      {/* Header */}
      <header className="bg-white text-tq-ink rounded-lg p-6 shadow-md flex flex-col sm:flex-row gap-6">
        {data.album?.imatge_url ? (
          <img
            src={deezerImg(data.album.imatge_url, 500)}
            alt=""
            className="w-full sm:w-48 h-48 object-cover rounded-md shrink-0"
          />
        ) : (
          <div className="w-full sm:w-48 h-48 bg-gray-100 rounded-md shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-wider text-gray-500">Cançó</p>
          <h1 className="text-3xl font-bold font-display mt-1">{data.nom}</h1>
          {data.artista && (
            <p className="mt-2 text-lg">
              <Link
                to={`/artista/${data.artista.slug}`}
                className="hover:text-tq-yellow-deep"
              >
                {data.artista.nom}
              </Link>
              {data.artistes_col?.length > 0 && (
                <span className="text-gray-500 text-sm">
                  {' '}amb{' '}
                  {data.artistes_col.map((col, j) => (
                    <span key={col.slug}>
                      {j > 0 ? ', ' : ''}
                      <Link to={`/artista/${col.slug}`} className="underline">
                        {col.nom}
                      </Link>
                    </span>
                  ))}
                </span>
              )}
            </p>
          )}
          {data.album && (
            <p className="text-sm text-gray-500 mt-1">
              Àlbum: <Link to={albumUrl({ albumSlug: data.album.slug, artistaSlug: data.artista?.slug })} className="underline">{data.album.nom}</Link>
            </p>
          )}
          <p className="text-xs text-gray-500 mt-2 space-x-3">
            <span>{formatDuration(data.durada_ms)}</span>
            {data.isrc && <span>ISRC: {data.isrc}</span>}
            {data.data_llancament && <span>Publicada: {data.data_llancament}</span>}
          </p>
          <ExternalListenLinks
            className="mt-4"
            kind="canco"
            title={data.nom}
            artist={data.artista?.nom}
            deezerId={data.deezer_id}
            isrc={data.isrc}
          />
        </div>
      </header>

      {/* Algorithm transparency panel — discreet, collapsed by default.
          Returns null when there's nothing to show (anon viewer of a
          song that isn't in the current top). */}
      <TopBreakdownPanel slug={data.slug} />

      {/* Ranking chart */}
      {data.historial?.length > 0 && (
        <section className="bg-white text-tq-ink rounded-lg p-6 shadow-md">
          <h2 className="text-xl font-bold font-display mb-1">Evolució al top</h2>
          <p className="text-xs text-gray-500 mb-4">
            Posició setmanal — més baix és millor (1 = top)
          </p>
          {/* Height reserved on the wrapper so the lazy chart streaming
              in causes no layout shift (CLS). */}
          <div className="w-full h-72">
            <Suspense
              fallback={<div className="w-full h-full bg-gray-100 rounded animate-pulse" />}
            >
              <CancoChart
                historial={data.historial}
                territoris={data.territoris_historial}
              />
            </Suspense>
          </div>
        </section>
      )}

      {/* Provisional callout */}
      {data.provisional?.length > 0 && (
        <section className="bg-tq-yellow-soft text-tq-ink rounded-lg p-4 text-sm">
          <p className="font-semibold mb-1">Actualment al provisional:</p>
          <ul className="flex flex-wrap gap-2">
            {data.provisional.map(p => (
              <li key={p.territori} className="px-2 py-0.5 bg-white rounded-sm">
                #{p.posicio} a {TERRITORI_NOM[p.territori] || p.territori}
              </li>
            ))}
          </ul>
        </section>
      )}

      {!data.historial?.length && !data.provisional?.length && (
        <p className="text-tq-ink-muted text-sm">
          Aquesta cançó encara no ha aparegut a cap top.
        </p>
      )}
    </article>
  )
}
