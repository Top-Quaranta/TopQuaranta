/**
 * AlbumPage — public album profile.
 *
 * Reads /api/v1/albums/<slug>/ and renders a cover + metadata block
 * plus a track listing. Tracks that have ever appeared in a ranking
 * show a small "top" badge.
 */
import { Link, useParams } from 'react-router-dom'
import Alert from '../components/ui/Alert'
import { cancoUrl } from '../lib/urls'
import { deezerImg } from '../lib/img'
import { useFeedbackTarget } from '../context/FeedbackContext'
import ExternalListenLinks from '../components/ExternalListenLinks'
import { SeoHead } from '../lib/seoHead'
import useApi from '../hooks/useApi'

function formatDuration(ms) {
  if (!ms) return '—'
  const totalSeconds = Math.floor(ms / 1000)
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function AlbumPage() {
  // Matched route can be `/album/:slug` or `/artista/:artistaSlug/:albumSlug`.
  const params = useParams()
  const slug = params.albumSlug || params.slug
  const { data, error, loading } = useApi(`/albums/${slug}/`, {
    mapError: (e) => (e.status === 404 ? 'Àlbum no trobat.' : null),
  })

  useFeedbackTarget(
    data
      ? { targetType: 'album', targetPk: data.pk, targetSlug: data.slug, targetLabel: data.nom }
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
      <SeoHead entity="album" slug={slug} />
      {/* Header */}
      <header className="bg-white text-tq-ink rounded-lg p-6 shadow-md flex flex-col sm:flex-row gap-6">
        {data.imatge_url ? (
          <img
            src={deezerImg(data.imatge_url, 500)}
            alt=""
            className="w-full sm:w-48 h-48 object-cover rounded-md shrink-0"
          />
        ) : (
          <div className="w-full sm:w-48 h-48 bg-gray-100 rounded-md shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-wider text-gray-500">Àlbum</p>
          <h1 className="text-3xl font-bold font-display mt-1">{data.nom}</h1>
          {data.artista && (
            <p className="mt-2 text-lg">
              <Link
                to={`/artista/${data.artista.slug}`}
                className="hover:text-tq-yellow-deep"
              >
                {data.artista.nom}
              </Link>
            </p>
          )}
          <p className="text-sm text-gray-500 mt-2">
            {data.data_llancament?.slice(0, 4) || '—'}
            {data.cancons?.length > 0 && <> · {data.cancons.length} cançons</>}
          </p>
          <ExternalListenLinks
            className="mt-4"
            kind="album"
            title={data.nom}
            artist={data.artista?.nom}
            deezerId={data.deezer_id}
          />
        </div>
      </header>

      {/* Tracks */}
      {data.cancons?.length > 0 && (
        <section className="bg-white text-tq-ink rounded-lg p-6 shadow-md">
          <h2 className="text-xl font-bold font-display mb-4">Cançons</h2>
          <ol className="space-y-1">
            {data.cancons.map((c, i) => (
              <li key={c.pk}>
                <Link
                  to={cancoUrl({
                    cancoSlug: c.slug,
                    artistaSlug: data.artista?.slug,
                    albumSlug: data.slug,
                  })}
                  className="flex items-center gap-3 py-2 border-b border-gray-100 last:border-b-0 hover:bg-tq-yellow-soft -mx-2 px-2 rounded"
                >
                  <span className="w-8 text-right text-sm font-semibold text-gray-400 tabular-nums shrink-0">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold truncate">{c.nom}</p>
                    {c.artistes_col?.length > 0 && (
                      <p className="text-xs text-gray-500 truncate">
                        amb {c.artistes_col.map(x => x.nom).join(', ')}
                      </p>
                    )}
                  </div>
                  {c.al_top && (
                    <span className="px-1.5 py-0.5 bg-tq-yellow text-tq-ink text-[10px] font-semibold rounded">
                      TOP
                    </span>
                  )}
                  <span className="text-xs text-gray-400 tabular-nums shrink-0 w-12 text-right">
                    {formatDuration(c.durada_ms)}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </section>
      )}
    </article>
  )
}
