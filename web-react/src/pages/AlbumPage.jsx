/**
 * AlbumPage — public album profile (/album/<slug>), redisseny web.
 *
 * No bespoke mock existed for this page (decision 3) — it's EXTRAPOLATED
 * from the cançó/artista language: dark hero with the cover, Anton title,
 * artist link + year · N cançons + streaming links; a glass "CANÇONS"
 * card with the numbered track list (TOP badge + duration), each row
 * linking to the song.
 *
 * Reads /api/v1/albums/<slug>/ (shape unchanged). Cover + ExternalListen
 * Links + FeedbackContext conserved; URLs (incl. SEO-nested) untouched.
 */
import { Link, useParams } from 'react-router-dom'
import Cover from '../components/Cover'
import { cancoUrl } from '../lib/urls'
import { useFeedbackTarget } from '../context/FeedbackContext'
import ExternalListenLinks from '../components/ExternalListenLinks'
import { SeoHead } from '../lib/seoHead'
import useApi from '../hooks/useApi'
import { Band, Glow, Glass, Kicker, Crit } from '../components/rd/primitives'

function formatDuration(ms) {
  if (!ms) return null
  const totalSeconds = Math.floor(ms / 1000)
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function AlbumPage() {
  const params = useParams()
  const slug = params.albumSlug || params.slug
  const { data, error, loading, reload } = useApi(`/albums/${slug}/`, {
    mapError: (e) => (e.status === 404 ? 'Àlbum no trobat.' : null),
  })

  useFeedbackTarget(
    data ? { targetType: 'album', targetPk: data.pk, targetSlug: data.slug, targetLabel: data.nom } : null,
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

  const year = data.data_llancament?.slice(0, 4)
  const nCancons = data.cancons?.length || 0

  return (
    <>
      <SeoHead entity="album" slug={slug} />

      <Band tone="top-hero">
        <Glow variant="a" />
        <div className="rd-cc-hero">
          {data.imatge_url ? (
            <Cover
              entitat="album" deezerId={data.deezer_id} imatgeUrl={data.imatge_url}
              alt={data.nom ? `Portada de ${data.nom}` : ''} size={500} priority
              className="rd-cc-tile" style={{ objectFit: 'cover' }}
            />
          ) : (
            <div className="rd-cc-tile" style={{ background: '#1b1a22' }} />
          )}
          <div className="min-w-0 flex-1">
            <Kicker color="var(--color-tq-yellow)">àlbum</Kicker>
            <Crit as="h1" className="rd-cc-title">{data.nom}</Crit>
            {data.artista && (
              <p className="text-lg" style={{ margin: '2px 0 0' }}>
                <Link to={`/artista/${data.artista.slug}`} className="rd-cc-artist">{data.artista.nom}</Link>
              </p>
            )}
            <p className="rd-cc-album" style={{ marginTop: 7 }}>
              {year || '—'}{nCancons > 0 ? ` · ${nCancons} ${nCancons === 1 ? 'cançó' : 'cançons'}` : ''}
            </p>
            <ExternalListenLinks
              className="rd-cc-links" kind="album" title={data.nom}
              artist={data.artista?.nom} deezerId={data.deezer_id}
            />
          </div>
        </div>
      </Band>

      <Band tone="ink2">
        {nCancons > 0 ? (
          <Glass className="rd-cc-card max-w-3xl">
            <Kicker color="var(--color-tq-yellow)">el disc, cançó a cançó</Kicker>
            <Crit as="h2" className="rd-cc-h2">CANÇONS</Crit>
            <ol className="flex flex-col mt-3">
              {data.cancons.map((c, i) => {
                const dur = formatDuration(c.durada_ms)
                return (
                  <li key={c.pk}>
                    <Link
                      to={cancoUrl({ cancoSlug: c.slug, artistaSlug: data.artista?.slug, albumSlug: data.slug })}
                      className="rd-tracklist-row"
                    >
                      <span className="rd-tracklist-n">{i + 1}</span>
                      <div className="min-w-0 flex-1">
                        <p className="rd-frow-title">{c.nom}</p>
                        {c.artistes_col?.length > 0 && (
                          <p className="rd-frow-artist">amb {c.artistes_col.map(x => x.nom).join(', ')}</p>
                        )}
                      </div>
                      {c.al_top && (
                        <span className="rd-top-badge">TOP</span>
                      )}
                      {dur && <span className="rd-tracklist-dur">{dur}</span>}
                    </Link>
                  </li>
                )
              })}
            </ol>
          </Glass>
        ) : (
          <p className="rd-empty">Encara no hi ha cançons registrades d'aquest àlbum.</p>
        )}
      </Band>
    </>
  )
}
