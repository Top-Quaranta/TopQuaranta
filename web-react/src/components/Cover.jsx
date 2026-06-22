/**
 * Cover — self-hosted album/cover image with a stepped fallback chain.
 *
 * When `deezerId` is given, renders a <picture> pointing at the
 * self-hosted variants at /portades/<entitat>/<deezerId>-<mida>.<fmt>
 * in AVIF → WebP → local JPG order (modern browsers pick AVIF/WebP;
 * iOS ≤15 falls to WebP/JPG). AVIF/WebP are ~30-40% smaller than the
 * Deezer JPEG and served with an immutable 1-year cache from our own
 * origin (LCP win, Fase 3).
 *
 * Fallback chain, driven entirely by the <img>'s onError. The happy
 * path — the 500px variant loads on the first try — is untouched: no
 * onError fires, `step` stays 0, nothing changes.
 *
 *   step 0  local JPG -500  →  500px self-hosted cover (the normal src)
 *   step 1  local JPG -250  →  some albums never got the -500 variant
 *                              on disk but do have -250 (audit
 *                              2026-06-22: /portades/album/<id>-500.jpg
 *                              404s while -250.jpg is present). Step
 *                              down before leaving our own origin.
 *   step 2  Deezer CDN      →  original stored Deezer cover, resized
 *                              via the WxH trick — exists whenever the
 *                              entity has any cover at all.
 *   step 3  stop            →  nothing more to try; the <img> keeps its
 *                              last src and the browser shows its native
 *                              broken-image affordance. We do NOT loop.
 *
 * `step` indexes into a per-render `chain` array. onError advances it
 * once per failure and is a no-op past the end, so a permanently-broken
 * final URL can never re-trigger a setState loop.
 *
 * Without `deezerId`, it renders a plain Deezer <img> directly (no
 * failed local requests).
 *
 * `priority` marks the LCP hero (eager + fetchpriority=high); omit it
 * for grid/list thumbnails (lazy).
 *
 * Spec: docs/architecture/portades.md
 */
import { useState } from 'react'

import {
  deezerImg,
  portadaFallbackChain,
  portadaSrcset,
} from '../lib/img'

const SIZES = '(max-width: 600px) 250px, 500px'

export default function Cover({
  entitat,
  deezerId,
  imatgeUrl,
  alt = '',
  size = 500,
  className = '',
  priority = false,
}) {
  // Index into the <img> fallback chain. 0 = the normal 500px local
  // cover (the happy path — never touched unless an onError fires).
  const [step, setStep] = useState(0)
  const loading = priority ? 'eager' : 'lazy'
  const fetchPriority = priority ? 'high' : 'auto'

  const deezerSrc = deezerImg(imatgeUrl, size)

  // No self-hosted cover possible (no deezer_id / entitat) → plain
  // Deezer image, resized via the WxH trick. No local requests.
  if (!entitat || !deezerId) {
    return (
      <img
        src={deezerSrc}
        alt={alt}
        className={className}
        loading={loading}
        fetchPriority={fetchPriority}
      />
    )
  }

  // Ordered <img> fallback chain: -500 local → -250 local → Deezer.
  const chain = portadaFallbackChain(entitat, deezerId, imatgeUrl, size)

  // Clamp defensively; once the chain is exhausted, keep the last src.
  const idx = Math.min(step, chain.length - 1)
  const imgSrc = chain[idx]
  // True until the final step — once there, onError must be a no-op so a
  // permanently-broken final URL can never re-trigger a setState loop.
  const canAdvance = step < chain.length - 1

  // The <picture> <source>s are self-hosted (avif/webp) too. Keep them
  // only while we're on step 0 (the local 500/250 srcset). Once we've
  // stepped past the local JPG, drop them — otherwise the browser would
  // keep preferring a 404'ing avif/webp variant over our chosen <img>
  // fallback (notably the Deezer URL at the last step).
  const showLocalSources = step === 0

  return (
    <picture>
      {showLocalSources && (
        <>
          <source
            type="image/avif"
            srcSet={portadaSrcset(entitat, deezerId, 'avif')}
            sizes={SIZES}
          />
          <source
            type="image/webp"
            srcSet={portadaSrcset(entitat, deezerId, 'webp')}
            sizes={SIZES}
          />
        </>
      )}
      <img
        src={imgSrc}
        alt={alt}
        className={className}
        loading={loading}
        fetchPriority={fetchPriority}
        onError={() => {
          if (canAdvance) setStep((s) => s + 1)
        }}
      />
    </picture>
  )
}
