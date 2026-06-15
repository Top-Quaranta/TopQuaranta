import { describe, expect, it } from 'vitest'
import { buildLinks } from './ExternalListenLinks'

function spotify(links) {
  return links.find(l => l.name === 'Spotify').href
}

describe('ExternalListenLinks buildLinks — Spotify', () => {
  it('links the exact track when we hold the spotify id', () => {
    const href = spotify(
      buildLinks({ kind: 'canco', title: 'X', artist: 'Y', spotifyId: 'abc123' }),
    )
    expect(href).toBe('https://open.spotify.com/track/abc123')
  })

  it('links the exact album / artist with their ids', () => {
    expect(
      spotify(buildLinks({ kind: 'album', title: 'X', artist: 'Y', spotifyId: 'al1' })),
    ).toBe('https://open.spotify.com/album/al1')
    expect(
      spotify(buildLinks({ kind: 'artista', artist: 'Y', spotifyId: 'ar1' })),
    ).toBe('https://open.spotify.com/artist/ar1')
  })

  it('falls back to ISRC search for a track without a spotify id', () => {
    const href = spotify(
      buildLinks({ kind: 'canco', title: 'X', artist: 'Y', isrc: 'ES1234567890' }),
    )
    expect(href).toContain('/search/isrc%3A')
    expect(href).not.toContain('/track/')
  })

  it('falls back to text search for an album without ids', () => {
    const href = spotify(buildLinks({ kind: 'album', title: 'Disc', artist: 'Y' }))
    expect(href).toContain('/search/')
    expect(href).toContain('/albums')
  })
})
