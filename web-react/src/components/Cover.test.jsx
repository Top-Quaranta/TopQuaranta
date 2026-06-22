// @vitest-environment jsdom
/**
 * Tests for the Cover fallback chain.
 *
 * The contract under audit (2026-06-22): when the self-hosted -500
 * variant is missing on disk the <img> 404s and the cover renders
 * broken. The onError handler must walk a stepped chain
 * -500 → -250 → Deezer so a cover never stays broken, while the happy
 * path (the -500 loads first try) is left completely untouched.
 *
 * jsdom does not actually fetch images, so loads/errors never fire on
 * their own — we drive the chain by dispatching `error` on the <img>,
 * exactly what the browser would do on a 404.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render } from '@testing-library/react'

import Cover from './Cover'
import { portadaFallbackChain } from '../lib/img'

const DEEZER = 'https://cdn-images.dzcdn.net/images/cover/abc123/1000x1000-000000-80-0-0.jpg'

afterEach(cleanup)

function img(container) {
  return container.querySelector('img')
}

describe('Cover fallback chain', () => {
  it('starts on the self-hosted 500px JPG (happy path src)', () => {
    const { container } = render(
      <Cover entitat="album" deezerId={42} imatgeUrl={DEEZER} alt="x" />,
    )
    expect(img(container).getAttribute('src')).toBe('/portades/album/42-500.jpg')
  })

  it('advances -500 → -250 → Deezer on successive errors', () => {
    const { container } = render(
      <Cover entitat="album" deezerId={42} imatgeUrl={DEEZER} alt="x" />,
    )
    const el = img(container)
    expect(el.getAttribute('src')).toBe('/portades/album/42-500.jpg')

    // -500 404s → step down to -250 on our own origin.
    fireEvent.error(el)
    expect(img(container).getAttribute('src')).toBe('/portades/album/42-250.jpg')

    // -250 404s → leave our origin for the original Deezer cover
    // (resized to the slot via the WxH trick).
    fireEvent.error(img(container))
    expect(img(container).getAttribute('src')).toBe(
      'https://cdn-images.dzcdn.net/images/cover/abc123/500x500-000000-80-0-0.jpg',
    )
  })

  it('stops at the last step and does not loop on a final error', () => {
    const { container } = render(
      <Cover entitat="album" deezerId={42} imatgeUrl={DEEZER} alt="x" />,
    )
    // Walk to the end of the chain.
    fireEvent.error(img(container)) // -500 -> -250
    fireEvent.error(img(container)) // -250 -> deezer
    const finalSrc = img(container).getAttribute('src')

    // Another error at the terminal step is a no-op: the src is stable
    // (the handler short-circuits, so there's no setState loop).
    fireEvent.error(img(container))
    expect(img(container).getAttribute('src')).toBe(finalSrc)
  })

  it('drops the <picture> sources once it falls back past the local JPG', () => {
    const { container } = render(
      <Cover entitat="album" deezerId={42} imatgeUrl={DEEZER} alt="x" />,
    )
    // Happy path: avif + webp sources present.
    expect(container.querySelectorAll('source')).toHaveLength(2)
    fireEvent.error(img(container)) // step past the local 500
    // Sources gone so the browser can't keep preferring a 404'ing
    // avif/webp over the chosen <img> fallback.
    expect(container.querySelectorAll('source')).toHaveLength(0)
  })

  it('renders a plain Deezer <img> when no deezerId (no local requests)', () => {
    const { container } = render(<Cover imatgeUrl={DEEZER} alt="x" size={120} />)
    expect(container.querySelector('picture')).toBeNull()
    expect(img(container).getAttribute('src')).toBe(
      'https://cdn-images.dzcdn.net/images/cover/abc123/120x120-000000-80-0-0.jpg',
    )
  })
})

describe('portadaFallbackChain', () => {
  it('orders -500 → -250 → resized Deezer', () => {
    expect(portadaFallbackChain('album', 42, DEEZER, 500)).toEqual([
      '/portades/album/42-500.jpg',
      '/portades/album/42-250.jpg',
      'https://cdn-images.dzcdn.net/images/cover/abc123/500x500-000000-80-0-0.jpg',
    ])
  })

  it('drops the Deezer step when no usable image URL is given', () => {
    expect(portadaFallbackChain('canco', 7, null)).toEqual([
      '/portades/canco/7-500.jpg',
      '/portades/canco/7-250.jpg',
    ])
  })
})
