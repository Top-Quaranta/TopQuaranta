/**
 * Aggregate analytics beacon — fire-and-forget POSTs to the Django
 * ingest endpoints. No PII, no IPs, no fingerprints.
 *
 * Two helpers:
 *   trackPageview(path, utm?)  → /api/v1/analytics/pageview/
 *   trackEvent(clau, dim1, dim2)→ /api/v1/analytics/event/  (allowlist)
 *
 * We use `navigator.sendBeacon` when the browser supports it (every
 * modern one does) — it's specifically designed for this case:
 *   - Survives page-unload (won't be cancelled on click-then-navigate).
 *   - Doesn't block the navigation or a UX action waiting for fetch.
 *   - No CORS preflight (simple POST with text/plain content-type).
 *
 * Failures are silent. Analytics MUST NOT break the SPA — a blocked
 * beacon (ad-blocker, network blip, locked-down browser) just means
 * we lose that event, not that the page misbehaves.
 *
 * Allowlist of `clau` values (must match `_PUBLIC_EVENT_KEYS` in
 * `web/api/analytics_ingest.py`):
 *
 *   spa_route_view     dim1 = pathname
 *   search_query       dim1 = scope (artistes/albums/cançons)
 *   share_click        dim1 = surface, dim2 = network
 *   escolta_click      dim1 = dsp (spotify/deezer/yt/apple)
 *   play_preview       dim1 = surface (canco/album/artista)
 *   newsletter_signup  (no dims — fired separately from registre)
 *   directori_filter   dim1 = filter type
 *   mapa_zoom          dim1 = level (territori/comarca/municipi)
 */

const PAGEVIEW_URL = '/api/v1/analytics/pageview/'
const EVENT_URL    = '/api/v1/analytics/event/'

function send(url, payload) {
  try {
    const body = JSON.stringify(payload)
    if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
      // sendBeacon's 2nd arg can be a Blob; use application/json so
      // DRF's JSONParser picks it up instead of guessing form-encoded.
      const blob = new Blob([body], { type: 'application/json' })
      navigator.sendBeacon(url, blob)
      return
    }
    // Legacy fallback. `keepalive: true` so the request survives a
    // navigation just like sendBeacon would.
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      credentials: 'omit',     // no cookies — pure aggregate signal
      keepalive: true,
      mode: 'cors',
    }).catch(() => {})
  } catch {
    // Storage-disabled mode, sandboxed iframe, etc. Swallow.
  }
}

/** Read `?utm_source=…&utm_campaign=…` off the current location. */
function readUtm() {
  try {
    const p = new URLSearchParams(window.location.search)
    const src = (p.get('utm_source') || '').trim().toLowerCase()
    if (!src) return null
    const cmp = (p.get('utm_campaign') || '').trim().toLowerCase()
    return { utm_source: src, utm_campaign: cmp }
  } catch {
    return null
  }
}

/**
 * Record a SPA route change. Pass the React Router pathname (no
 * search string — we don't want query params bloating the dim1
 * cardinality, and UTM is captured separately as a utm_landing
 * event by the same endpoint).
 */
export function trackPageview(path) {
  const utm = readUtm()
  send(PAGEVIEW_URL, { path, ...(utm || {}) })
}

/**
 * Record a curated SPA event. `clau` MUST be in the backend
 * allowlist (`_PUBLIC_EVENT_KEYS`) — the server returns 400 for
 * unknown values, which we silently swallow. Dim1/dim2 are
 * lower-cased + truncated server-side so callers don't need to
 * normalise.
 */
export function trackEvent(clau, dim1 = '', dim2 = '') {
  send(EVENT_URL, { clau, dim1, dim2 })
}
