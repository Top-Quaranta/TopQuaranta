/**
 * ExternalListenLinks — "Escolta a" row for content pages.
 *
 * Builds search URLs (or direct track/album/artist URLs when we have
 * the DSP's own ID) for Spotify, Deezer, YouTube Music and Apple
 * Music. Rendered as a horizontal row of small pill-shaped links.
 * No API calls, no auth — just URL construction.
 *
 * The `kind` prop picks the right search path per platform:
 *   - "canco"   → track search ("<artist> <title>")
 *   - "album"   → album search ("<artist> <title>")
 *   - "artista" → artist search
 *
 * Deezer gets a direct link when we hold the id (we do for almost
 * every Canco + Album). Others always search because we don't
 * populate their IDs.
 */

import { useState } from 'react'
import { trackEvent } from '../lib/analytics'

function encode(q) {
  return encodeURIComponent((q || '').trim())
}

// kind -> Spotify entity path segment for direct links + embeds.
const SPOTIFY_TYPE = { canco: 'track', album: 'album', artista: 'artist' }

// Map the link's display name to the analytics dim1 — short, stable
// slugs the dashboard charts on. We don't bake them into the link
// builder above so the buttons keep the human label.
const DSP_SLUG = {
  Spotify: 'spotify',
  Deezer: 'deezer',
  YouTube: 'youtube',
  'Apple Music': 'apple',
}

export function buildLinks({ kind, title, artist, deezerId, isrc, spotifyId }) {
  // Top-line search string — "artista titol" is the ordering DSPs
  // match best in our testing. For artist pages it's just the name.
  const q =
    kind === 'artista' ? artist : [artist, title].filter(Boolean).join(' ')
  const enc = encode(q)

  const spotifyPath = {
    canco: 'tracks',
    album: 'albums',
    artista: 'artists',
  }[kind]

  const applePath = {
    canco: 'songs',
    album: 'albums',
    artista: 'artists',
  }[kind]

  // Spotify: when we hold the exact entity id (Process B enrichment for
  // tracks, Album/Artista.spotify_id) link the REAL entity. Otherwise
  // fall back: ISRC search for tracks (deep-link-equivalent), text
  // search for album/artist (no UPC/artist-id without the exact id).
  const spotifyType = SPOTIFY_TYPE[kind]
  const spotifyHref =
    spotifyId && spotifyType
      ? `https://open.spotify.com/${spotifyType}/${spotifyId}`
      : kind === 'canco' && isrc
      ? `https://open.spotify.com/search/isrc%3A${encode(isrc)}`
      : `https://open.spotify.com/search/${enc}${
          spotifyPath ? `/${spotifyPath}` : ''
        }`

  // Deezer: direct URL when we hold the id (we do for 100% of Canço
  // and Album after the legacy purge). Otherwise search.
  const deezerHref =
    deezerId && kind === 'canco'
      ? `https://www.deezer.com/track/${deezerId}`
      : deezerId && kind === 'album'
      ? `https://www.deezer.com/album/${deezerId}`
      : deezerId && kind === 'artista'
      ? `https://www.deezer.com/artist/${deezerId}`
      : `https://www.deezer.com/search/${enc}`

  return [
    { name: 'Spotify',     href: spotifyHref },
    { name: 'Deezer',      href: deezerHref },
    // YouTube doesn't expose ISRC via public search; text-based here.
    { name: 'YouTube',     href: `https://music.youtube.com/search?q=${enc}` },
    // Apple Music's web search parses plain text only (no isrc: filter).
    {
      name: 'Apple Music',
      href: `https://music.apple.com/search?term=${enc}${
        applePath ? `&type=${applePath}` : ''
      }`,
    },
  ]
}

const PLAY_ICON = (
  <svg
    width="12"
    height="12"
    viewBox="0 0 24 24"
    fill="currentColor"
    aria-hidden="true"
  >
    <path d="M8 5v14l11-7z" />
  </svg>
)

export default function ExternalListenLinks({
  kind,
  title,
  artist,
  deezerId = null,
  isrc = null,
  spotifyId = null,
  className = '',
}) {
  const links = buildLinks({ kind, title, artist, deezerId, isrc, spotifyId })
  // Embed only when we hold the exact id. Facade (click-to-load): the
  // iframe is NOT mounted until the user clicks, so no Spotify cookies
  // load on page view (RGPD) and there's no perf hit for visitors who
  // never play. The same escolta_click event fires on activation.
  const spotifyType = SPOTIFY_TYPE[kind]
  const canEmbed = !!(spotifyId && spotifyType)
  const [embedOn, setEmbedOn] = useState(false)
  const embedHeight = kind === 'canco' ? 152 : 352

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-gray-500">
          Escolta-ho a
        </span>
        {links.map(l => (
          <a
            key={l.name}
            href={l.href}
            target="_blank"
            rel="noopener"
            // Beacon fires before the browser hands the navigation
            // off — `sendBeacon` survives the unload, so we don't
            // delay the user's click while waiting for the POST.
            // dim1 = DSP slug, dim2 = surface (canco/album/artista).
            onClick={() => trackEvent('escolta_click', DSP_SLUG[l.name] || l.name.toLowerCase(), kind || '')}
            className="inline-flex items-center gap-1 px-2.5 py-1 bg-tq-ink text-tq-yellow text-xs font-semibold rounded-full hover:bg-tq-ink/90 transition-colors"
          >
            {PLAY_ICON}
            {l.name}
          </a>
        ))}
      </div>

      {canEmbed && (
        <div className="mt-3">
          {embedOn ? (
            <iframe
              title="Reproductor de Spotify"
              src={`https://open.spotify.com/embed/${spotifyType}/${spotifyId}`}
              width="100%"
              height={embedHeight}
              style={{ borderRadius: 12, border: 0 }}
              loading="lazy"
              allow="encrypted-media"
            />
          ) : (
            <button
              type="button"
              onClick={() => {
                setEmbedOn(true)
                trackEvent('escolta_click', 'spotify_embed', kind || '')
              }}
              className="inline-flex items-center gap-2 px-3 py-2 bg-[#1DB954] text-black text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity"
            >
              {PLAY_ICON}
              Reproductor de Spotify
            </button>
          )}
        </div>
      )}
    </div>
  )
}
