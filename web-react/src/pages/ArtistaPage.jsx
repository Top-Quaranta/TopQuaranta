/**
 * ArtistaPage — public artist profile.
 *
 * Reads /api/v1/artistes/<slug>/ and renders:
 *   - Header card (name, territories, location, Deezer link)
 *   - Social links row (when any)
 *   - Last 10 weeks in the ranking (grouped by week)
 *   - Verified discography (albums with cover + track count)
 *
 * Unapproved artists ship a minimal "under review" page.
 */
import { Link, useParams } from 'react-router-dom'
import { SeoHead } from '../lib/seoHead'
import Alert from '../components/ui/Alert'
import { albumUrl, cancoUrl } from '../lib/urls'
import { deezerImg } from '../lib/img'
import FeedbackButton from '../components/FeedbackButton'
import { useFeedbackTarget } from '../context/FeedbackContext'
import ExternalListenLinks from '../components/ExternalListenLinks'
import { useAuth } from '../context/AuthContext'
import useApi from '../hooks/useApi'
import { TERRITORI_NOM } from '../components/editorial'

export default function ArtistaPage() {
  const { slug } = useParams()
  const { profile } = useAuth()
  const { data, error, loading } = useApi(`/artistes/${slug}/`, {
    mapError: (e) => (e.status === 404 ? 'Artista no trobat.' : null),
  })

  // Publish the page target so the shared footer "Corregir" button
  // addresses this artist. Must run unconditionally before any early
  // returns so the hook call order stays stable across renders.
  useFeedbackTarget(
    data
      ? { targetType: 'artista', targetPk: data.pk, targetSlug: data.slug, targetLabel: data.nom }
      : null,
  )

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div className="h-28 bg-white/5 rounded-lg animate-pulse" />
        <div className="h-48 bg-white/5 rounded-lg animate-pulse" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto">
        <Alert tone="danger">{error}</Alert>
        <p className="mt-4">
          <Link to="/artistes" className="text-tq-yellow">← Torna al directori</Link>
        </p>
      </div>
    )
  }

  if (!data) return null

  const localitatText = (() => {
    const loc = data.localitats?.[0]
    if (!loc) return null
    if (loc.municipi) {
      return `${loc.municipi.nom}, ${loc.municipi.comarca} (${loc.municipi.territori})`
    }
    return loc.manual
  })()

  return (
    <article className="max-w-4xl mx-auto text-white space-y-6">
      <SeoHead entity="artista" slug={slug} />
      {/* Header card */}
      <header className="bg-white text-tq-ink rounded-lg p-6 shadow-md flex flex-col sm:flex-row gap-6">
        {data.imatge_url ? (
          <img
            src={deezerImg(data.imatge_url, 500)}
            alt=""
            className="w-full sm:w-48 h-48 object-cover rounded-md shrink-0"
          />
        ) : (
          <div className="w-full sm:w-48 h-48 bg-gray-100 rounded-md shrink-0 flex items-center justify-center font-display font-bold text-5xl text-gray-400">
            {data.nom?.[0] || '?'}
          </div>
        )}
        <div className="min-w-0 flex-1">
        <h1 className="text-3xl font-bold font-display">{data.nom}</h1>
        <div className="flex flex-wrap gap-2 mt-2 text-sm text-gray-600">
          {data.territoris?.length > 0 && (
            <span>{data.territoris.map(c => TERRITORI_NOM[c] || c).join(' · ')}</span>
          )}
          {localitatText && <span>· {localitatText}</span>}
        </div>
        {data.genere && (
          <p className="text-xs text-gray-500 mt-2 uppercase tracking-wide">{data.genere}</p>
        )}
        {!data.aprovat && (
          <p className="mt-3 inline-block px-2 py-0.5 bg-tq-yellow-soft text-tq-yellow-deep text-xs font-semibold rounded">
            Pendent de revisió
          </p>
        )}

        {/* Streaming links (replace the old single Deezer anchor). */}
        <ExternalListenLinks
          className="mt-4"
          kind="artista"
          artist={data.nom}
          deezerId={data.deezer_ids?.[0]}
        />

        {/* Social links + self-claim CTA */}
        <div className="flex flex-wrap gap-3 mt-3 text-sm">
          {Object.entries(data.social || {}).map(([key, url]) => (
            <a
              key={key}
              href={url}
              target="_blank" rel="noopener"
              className="underline text-tq-ink hover:text-tq-yellow-deep capitalize"
            >
              {key.replace(/_url$/, '').replace(/_/g, ' ')}
            </a>
          ))}
          {/* CTA: request to manage this artist. Goes to /compte/artista/gestio
              pre-filled. Private — still works for anonymous users because
              AuthRoute on the target page will redirect to login.
              When the visitor is already a verified manager of this
              artist (per /api/v1/auth/me/'s `verified_artist_pks`), we
              swap the request CTA for a direct shortcut to the editor. */}
          {profile?.verified_artist_pks?.includes(data.pk) ? (
            <Link
              to={`/compte/artista/${data.pk}/editar`}
              className="ml-auto text-xs px-2.5 py-1 rounded-md bg-tq-yellow text-tq-ink font-semibold hover:bg-tq-yellow-deep hover:text-white"
            >
              Editar perfil
            </Link>
          ) : (
            <Link
              to={`/compte/artista/gestio?artista=${data.slug}`}
              className="ml-auto text-xs px-2.5 py-1 rounded-md bg-tq-ink text-tq-yellow font-semibold hover:bg-tq-ink/90"
            >
              Sóc aquest artista
            </Link>
          )}
        </div>
        </div>
      </header>

      {/* Ranking history */}
      {data.historial?.length > 0 && (
        <section className="bg-white text-tq-ink rounded-lg p-6 shadow-md">
          <h2 className="text-xl font-bold font-display mb-3">Últimes setmanes al top</h2>
          <ul className="space-y-3">
            {data.historial.map(week => (
              <li key={week.setmana}>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Setmana del {week.setmana}
                </p>
                <ul className="mt-1 flex flex-wrap gap-1.5">
                  {week.entries.map((e, i) => (
                    <li key={`${week.setmana}-${e.territori}-${i}`}>
                      <Link
                        to={cancoUrl({
                          cancoSlug: e.canco_slug,
                          artistaSlug: data.slug,
                          albumSlug: e.canco_album_slug,
                        })}
                        className="inline-flex items-center gap-2 px-2 py-1 bg-tq-yellow-soft text-tq-ink text-xs rounded-sm hover:bg-tq-yellow"
                        title={e.canco_nom}
                      >
                        <span className="font-bold tabular-nums">#{e.posicio}</span>
                        <span className="text-[10px] text-gray-500">{e.territori}</span>
                        <span className="truncate max-w-[14rem]">{e.canco_nom}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Discography */}
      {data.discografia?.length > 0 && (
        <section className="bg-white text-tq-ink rounded-lg p-6 shadow-md">
          <h2 className="text-xl font-bold font-display mb-3">Discografia</h2>
          <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {data.discografia.map(a => (
              <li key={a.slug}>
                <Link
                  to={albumUrl({ albumSlug: a.slug, artistaSlug: data.slug })}
                  className="block"
                >
                  {a.imatge_url ? (
                    <img
                      src={deezerImg(a.imatge_url, 500)}
                      alt=""
                      className="aspect-square w-full object-cover rounded-md"
                    />
                  ) : (
                    <div className="aspect-square w-full bg-gray-100 rounded-md" />
                  )}
                  <p className="mt-1.5 text-sm font-semibold truncate">{a.nom}</p>
                  <p className="text-xs text-gray-500">
                    {a.data_llancament?.slice(0, 4)} · {a.n_cancons} cançons
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Col·laboracions — cançons d'altres artistes amb participació d'aquest. */}
      {data.colaboracions?.length > 0 && (
        <section className="bg-white text-tq-ink rounded-lg p-6 shadow-md">
          <h2 className="text-xl font-bold font-display mb-3">També col·labora a</h2>
          <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {data.colaboracions.map(c => (
              <li key={c.canco_slug}>
                <Link
                  to={cancoUrl({
                    cancoSlug: c.canco_slug,
                    artistaSlug: c.artista_principal_slug,
                    albumSlug: c.album_slug,
                  })}
                  className="block"
                >
                  {c.imatge_url ? (
                    <img
                      src={deezerImg(c.imatge_url, 500)}
                      alt=""
                      loading="lazy"
                      className="aspect-square w-full object-cover rounded-md"
                    />
                  ) : (
                    <div className="aspect-square w-full bg-gray-100 rounded-md" />
                  )}
                  <p className="mt-1.5 text-sm font-semibold truncate">{c.canco_nom}</p>
                  <p className="text-xs text-gray-500 truncate">
                    amb {c.artista_principal_nom}
                  </p>
                  {c.data_llancament && (
                    <p className="text-[11px] text-gray-600">
                      {c.data_llancament.slice(0, 4)}
                    </p>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  )
}
