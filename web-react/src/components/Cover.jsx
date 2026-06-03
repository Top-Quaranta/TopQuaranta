/**
 * Cover — self-hosted album/cover image with a Deezer fallback.
 *
 * When `deezerId` is given, renders a <picture> pointing at the
 * self-hosted variants at /portades/<entitat>/<deezerId>-<mida>.<fmt>
 * in AVIF → WebP → local JPG order (modern browsers pick AVIF/WebP;
 * iOS ≤15 falls to WebP/JPG). AVIF/WebP are ~30-40% smaller than the
 * Deezer JPEG and served with an immutable 1-year cache from our own
 * origin (LCP win, Fase 3).
 *
 * If all three local formats 404 — the entity has no generated cover
 * yet (e.g. `canco`/`artista` before the nightly cron drains them) —
 * the <img>'s onError swaps to the original Deezer URL, so the cover
 * still shows. Without `deezerId`, it renders a plain Deezer <img>
 * directly (no failed local requests).
 *
 * `priority` marks the LCP hero (eager + fetchpriority=high); omit it
 * for grid/list thumbnails (lazy).
 *
 * Spec: docs/architecture/portades.md
 */
import { useState } from 'react'

import { deezerImg, portadaSrcset, portadaUrl } from '../lib/img'

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
  const [localFailed, setLocalFailed] = useState(false)
  const loading = priority ? 'eager' : 'lazy'
  const fetchPriority = priority ? 'high' : 'auto'

  // No self-hosted cover available (no deezer_id, or the local variants
  // 404'd) → plain Deezer image, resized via the WxH trick.
  if (!entitat || !deezerId || localFailed) {
    return (
      <img
        src={deezerImg(imatgeUrl, size)}
        alt={alt}
        className={className}
        loading={loading}
        fetchPriority={fetchPriority}
      />
    )
  }

  return (
    <picture>
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
      <img
        src={portadaUrl(entitat, deezerId, 500, 'jpg')}
        alt={alt}
        className={className}
        loading={loading}
        fetchPriority={fetchPriority}
        onError={() => setLocalFailed(true)}
      />
    </picture>
  )
}
