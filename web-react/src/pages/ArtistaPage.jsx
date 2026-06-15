/**
 * ArtistaPage — public artist profile (/artista/<slug>), redisseny web.
 *
 * Dark hero (territory glow) with the initials/photo tile, Anton name,
 * territory line, derived KPI badges (songs at top / best position /
 * albums), streaming links and the "Sóc aquest artista" CTA. Body bands:
 * weeks in the top, discography, collaborations — glass cards.
 *
 * Reads /api/v1/artistes/<slug>/ (shape unchanged). KPIs are DERIVED from
 * the real historial/discografia, not invented. URLs + ExternalListenLinks
 * + FeedbackContext + the gestió CTA target are conserved.
 */
import { Link, useParams } from 'react-router-dom'
import { SeoHead } from '../lib/seoHead'
import { albumUrl, cancoUrl } from '../lib/urls'
import { deezerImg } from '../lib/img'
import { useFeedbackTarget } from '../context/FeedbackContext'
import ExternalListenLinks from '../components/ExternalListenLinks'
import { useAuth } from '../context/AuthContext'
import useApi from '../hooks/useApi'
import { Band, Glow, Glass, Kicker, Crit, Numeral, TerrLogo, RdCover } from '../components/rd/primitives'
import { terr, shade } from '../components/rd/terr'

function Kpi({ n, label }) {
  return (
    <span className="rd-cc-pos rd-glass">
      <Numeral n={n} size={24} color="var(--color-tq-yellow)" />
      <em>{label}</em>
    </span>
  )
}

export default function ArtistaPage() {
  const { slug } = useParams()
  const { profile } = useAuth()
  const { data, error, loading, reload } = useApi(`/artistes/${slug}/`, {
    mapError: (e) => (e.status === 404 ? 'Artista no trobat.' : null),
  })

  useFeedbackTarget(
    data ? { targetType: 'artista', targetPk: data.pk, targetSlug: data.slug, targetLabel: data.nom } : null,
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
          <div className="flex gap-3 justify-center mt-4">
            <button type="button" onClick={reload} className="rd-btn rd-btn--ghost">Reintentar</button>
            <Link to="/artistes" className="rd-btn rd-btn--hot">← Torna al directori</Link>
          </div>
        </Glass>
      </Band>
    )
  }
  if (!data) return null

  const code = data.territoris?.[0]
  const t = code ? terr(code) : terr('ALT')
  const loc = data.localitats?.[0]
  const localitatText = loc ? (loc.municipi ? `${loc.municipi.nom}, ${loc.municipi.comarca}` : loc.manual) : null

  const hist = data.historial || []
  const allEntries = hist.flatMap(w => w.entries || [])
  const bestPos = allEntries.length ? Math.min(...allEntries.map(e => e.posicio)) : null
  const nTop = new Set(allEntries.map(e => e.canco_slug)).size
  const nAlbums = (data.discografia || []).length

  const isManager = profile?.verified_artist_pks?.includes(data.pk)

  return (
    <>
      <SeoHead entity="artista" slug={slug} />

      <Band tone="top-hero">
        <Glow variant="a" color={t.deep} />
        <div className="rd-cc-hero">
          {data.imatge_url ? (
            <img src={deezerImg(data.imatge_url, 500)} alt="" className="rd-cc-tile" style={{ objectFit: 'cover' }} />
          ) : (
            <div className="rd-cc-tile" style={{ background: `linear-gradient(155deg, ${shade(t.deep, 0.14)} 0%, ${shade(t.deep, -0.28)} 100%)` }}>
              <span className="rd-cc-ini" style={{ color: t.accent }}>{(data.nom?.[0] || '?').toUpperCase()}</span>
            </div>
          )}
          <div className="min-w-0 flex-1">
            <Kicker color="var(--color-tq-yellow)">artista</Kicker>
            <Crit as="h1" className="rd-cc-title">{data.nom}</Crit>
            <p className="rd-cc-album">
              <TerrLogo code={code || 'ALT'} className="h-4 w-4" /> {t.nom}
              {localitatText && <span style={{ color: 'rgba(255,255,255,0.6)' }}> · {localitatText}</span>}
              {data.genere && <span style={{ color: 'rgba(255,255,255,0.6)' }}> · {data.genere}</span>}
            </p>
            {!data.aprovat && (
              <p className="mt-2 inline-block px-2 py-0.5 rounded text-xs font-semibold" style={{ background: 'rgba(250,204,21,0.2)', color: 'var(--color-tq-yellow)' }}>
                Pendent de revisió
              </p>
            )}
            {data.entrat_al_top && (
              // Slice F3: shareable "newly entered the top" badge. Fed by
              // the same new-entry signal as the manager alert.
              <p className="mt-2 inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold" style={{ background: 'var(--color-tq-yellow)', color: 'var(--color-tq-ink)' }}>
                🎉 Nou al Top aquesta setmana
              </p>
            )}

            <div className="rd-cc-badges">
              <Kpi n={nTop} label="al top" />
              {bestPos != null && <Kpi n={`#${bestPos}`} label="millor posició" />}
              {nAlbums > 0 && <Kpi n={nAlbums} label={nAlbums === 1 ? 'àlbum' : 'àlbums'} />}
            </div>

            <ExternalListenLinks className="rd-cc-links" kind="artista" artist={data.nom} deezerId={data.deezer_ids?.[0]} spotifyId={data.spotify_id} />

            <div className="flex flex-wrap gap-3 mt-3 items-center">
              {Object.entries(data.social || {}).map(([key, url]) => (
                <a key={key} href={url} target="_blank" rel="noopener" className="rd-listen-pill capitalize">
                  {key.replace(/_url$/, '').replace(/_/g, ' ')}
                </a>
              ))}
              {isManager ? (
                <Link to={`/compte/artista/${data.pk}/editar`} className="rd-btn rd-btn--hot ml-auto" style={{ fontSize: 13, padding: '9px 16px' }}>Editar perfil</Link>
              ) : (
                // Claim CTA: links the request-management flow
                // (/compte/artista/gestio -> UserArtista -> staff verifies).
                // More prominent (--hot) when the artist is newly at the top.
                <Link
                  to={`/compte/artista/gestio?artista=${data.slug}`}
                  className={`rd-btn ${data.entrat_al_top ? 'rd-btn--hot' : 'rd-btn--ghost'} ml-auto`}
                  style={{ fontSize: 13, padding: '9px 16px' }}
                >
                  Ets {data.nom}? Reclama el teu perfil →
                </Link>
              )}
            </div>
          </div>
        </div>
      </Band>

      <Band tone="ink2">
        <div className="rd-cc-grid">
          <div className="min-w-0 flex flex-col gap-4">
            {hist.length > 0 && (
              <Glass className="rd-cc-card">
                <Kicker color="var(--color-tq-yellow)">les últimes setmanes</Kicker>
                <Crit as="h2" className="rd-cc-h2">AL TOP</Crit>
                <ul className="flex flex-col gap-3 mt-3">
                  {hist.map(week => (
                    <li key={week.setmana}>
                      <p className="text-[11px] uppercase tracking-widest text-white/45">Setmana del {week.setmana}</p>
                      <ul className="mt-1.5 flex flex-wrap gap-1.5">
                        {week.entries.map((e, i) => (
                          <li key={`${week.setmana}-${e.territori}-${i}`}>
                            <Link
                              to={cancoUrl({ cancoSlug: e.canco_slug, artistaSlug: data.slug, albumSlug: e.canco_album_slug })}
                              className="rd-hist-chip" title={e.canco_nom}
                            >
                              <span className="font-extrabold tabular-nums">#{e.posicio}</span>
                              <span className="text-[10px] text-white/50">{terr(e.territori).short}</span>
                              <span className="truncate max-w-[14rem]">{e.canco_nom}</span>
                            </Link>
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </Glass>
            )}

            {(data.discografia || []).length > 0 && (
              <Glass className="rd-cc-card">
                <Kicker color="var(--color-tq-yellow)">discografia</Kicker>
                <Crit as="h2" className="rd-cc-h2">ÀLBUMS</Crit>
                <ul className="rd-album-wall" style={{ marginTop: 16 }}>
                  {data.discografia.map(a => (
                    <li key={a.slug}>
                      <Link to={albumUrl({ albumSlug: a.slug, artistaSlug: data.slug })} className="block group">
                        <RdCover src={a.imatge_url ? deezerImg(a.imatge_url, 500) : null} label={a.nom} alt={a.nom} size="100%" radius={12} className="rd-album-cover" />
                        <p className="rd-album-title">{a.nom}</p>
                        <p className="rd-album-artist">{a.data_llancament?.slice(0, 4)} · {a.n_cancons} cançons</p>
                      </Link>
                    </li>
                  ))}
                </ul>
              </Glass>
            )}
          </div>

          {(data.colaboracions || []).length > 0 && (
            <aside className="min-w-0">
              <Glass className="rd-cc-card">
                <Kicker color="var(--color-tq-yellow)">també hi col·labora</Kicker>
                <Crit as="h2" className="rd-cc-h2">COL·LABORACIONS</Crit>
                <ul className="flex flex-col gap-3 mt-3">
                  {data.colaboracions.map(c => (
                    <li key={c.canco_slug}>
                      <Link to={cancoUrl({ cancoSlug: c.canco_slug, artistaSlug: c.artista_principal_slug, albumSlug: c.album_slug })} className="rd-trow">
                        <RdCover src={c.imatge_url ? deezerImg(c.imatge_url, 120) : null} label={c.canco_nom} alt={c.canco_nom} size={48} radius={8} />
                        <div className="min-w-0 flex-1">
                          <p className="rd-trow-title">{c.canco_nom}</p>
                          <p className="rd-trow-artist">amb {c.artista_principal_nom}</p>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              </Glass>
            </aside>
          )}
        </div>
      </Band>
    </>
  )
}
