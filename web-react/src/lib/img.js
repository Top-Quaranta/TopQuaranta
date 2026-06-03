/**
 * Image URL utilities.
 *
 * The backend stores Deezer cover URLs as full strings in the
 * canonical 1000x1000 variant (`Album.imatge_url` is `cover_xl`).
 * Serving 1000x1000 to a 40x40 slot was the main LCP driver per
 * PSI 2026-05-16 (≈4.2 MiB of unnecessary payload per page).
 *
 * Deezer's CDN supports arbitrary `WxH` segments up to ~1400 (2000+
 * returns 403; verified empirically). We rewrite the segment in the
 * existing URL at consumption time — no model changes, no migration,
 * no rebuild of stored URLs.
 *
 * Slot → size table (2x retina baked in; pick the next size up):
 *   ≤48 px slot   → 120
 *   ≤128 px slot  → 250
 *   ≤320 px slot  → 500
 *   Renderer 1080 → 1000 (keep)
 */

const DEEZER_HOST = 'dzcdn.net'
const SIZE_PATTERN = /\/\d+x\d+-/

/**
 * Rewrite a Deezer cover URL to a given square size.
 * Pass-through for null, empty, or non-Deezer URLs.
 *
 * @param {string|null|undefined} url - original URL (any size)
 * @param {number} size - target square side in CSS pixels
 * @returns {string} resized URL or the input unchanged
 */
export function deezerImg(url, size = 500) {
  if (!url || typeof url !== 'string') return url || ''
  if (!url.includes(DEEZER_HOST)) return url
  return url.replace(SIZE_PATTERN, `/${size}x${size}-`)
}

// ── Self-hosted covers (Fase 3) ──────────────────────────────────────
// Caddy serves /portades/<entitat>/<deezer_id>-<mida>.<format> from our
// own origin (webp/avif/jpg, immutable cache). See
// docs/architecture/portades.md.

const PORTADA_BASE = '/portades'

/** Path to one self-hosted cover variant. */
export function portadaUrl(entitat, deezerId, mida, fmt) {
  return `${PORTADA_BASE}/${entitat}/${deezerId}-${mida}.${fmt}`
}

/** `<source srcset>` value for a format: the 250w + 500w variants. */
export function portadaSrcset(entitat, deezerId, fmt) {
  return (
    `${portadaUrl(entitat, deezerId, 250, fmt)} 250w, ` +
    `${portadaUrl(entitat, deezerId, 500, fmt)} 500w`
  )
}
