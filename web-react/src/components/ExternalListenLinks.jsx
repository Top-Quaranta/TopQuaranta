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

import { trackEvent } from '../lib/analytics'

function encode(q) {
  return encodeURIComponent((q || '').trim())
}

// Map the link's display name to the analytics dim1 — short, stable
// slugs the dashboard charts on. We don't bake them into the link
// builder above so the buttons keep the human label.
const DSP_SLUG = {
  Spotify: 'spotify',
  Deezer: 'deezer',
  YouTube: 'youtube',
  'Apple Music': 'apple',
}

function buildLinks({ kind, title, artist, deezerId, isrc }) {
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

  // Spotify: for tracks with an ISRC, use its "isrc:" search filter —
  // it returns exactly the matched track, so the effective behaviour
  // is a deep link even though the URL is technically a /search/. We
  // don't have album UPCs or artist MBIDs, so album/artist searches
  // stay text-based.
  const spotifyHref =
    kind === 'canco' && isrc
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
  className = '',
}) {
  const links = buildLinks({ kind, title, artist, deezerId, isrc })

  return (
    <div className={'flex flex-wrap items-center gap-2 ' + className}>
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
  )
}
