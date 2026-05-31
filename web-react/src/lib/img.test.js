/**
 * Tests for the Deezer image URL rewriter.
 *
 * Locked-in contract: any `WxH` segment in a Deezer CDN URL is
 * swapped for the requested size; non-Deezer URLs and falsy values
 * pass through unchanged. Empirical Deezer support (2026-05-18):
 * sizes 56–1400 return 200; 2000+ returns 403. We don't gate on
 * size here — staying within sensible bounds is the caller's job.
 */
import { describe, it, expect } from 'vitest'
import { deezerImg, portadaSrcset, portadaUrl } from './img'

const SAMPLE = 'https://cdn-images.dzcdn.net/images/cover/abc123/1000x1000-000000-80-0-0.jpg'

describe('deezerImg', () => {
  it('rewrites a 1000x1000 Deezer URL to the requested size', () => {
    expect(deezerImg(SAMPLE, 120)).toBe(
      'https://cdn-images.dzcdn.net/images/cover/abc123/120x120-000000-80-0-0.jpg',
    )
  })

  it('rewrites an already-small Deezer URL to a different size', () => {
    const small = 'https://cdn-images.dzcdn.net/images/cover/abc/56x56-000000-80-0-0.jpg'
    expect(deezerImg(small, 500)).toBe(
      'https://cdn-images.dzcdn.net/images/cover/abc/500x500-000000-80-0-0.jpg',
    )
  })

  it('passes a non-Deezer URL through unchanged', () => {
    const external = 'https://www.last.fm/img/foo.jpg'
    expect(deezerImg(external, 250)).toBe(external)
  })

  it('returns empty string for null / undefined / non-string input', () => {
    expect(deezerImg(null, 250)).toBe('')
    expect(deezerImg(undefined, 250)).toBe('')
    expect(deezerImg('', 250)).toBe('')
  })

  it('defaults to 500 when size is omitted', () => {
    expect(deezerImg(SAMPLE)).toBe(
      'https://cdn-images.dzcdn.net/images/cover/abc123/500x500-000000-80-0-0.jpg',
    )
  })
})

describe('portadaUrl', () => {
  it('builds the deterministic self-hosted path', () => {
    expect(portadaUrl('album', 12345, 500, 'webp')).toBe('/portades/album/12345-500.webp')
    expect(portadaUrl('album', 9, 250, 'avif')).toBe('/portades/album/9-250.avif')
  })
})

describe('portadaSrcset', () => {
  it('emits the 250w + 500w variants for a format', () => {
    expect(portadaSrcset('album', 42, 'avif')).toBe(
      '/portades/album/42-250.avif 250w, /portades/album/42-500.avif 500w',
    )
  })
})
