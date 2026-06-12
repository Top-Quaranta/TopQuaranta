/**
 * rd/CookieBanner — redisseny-styled cookie notice (glass bar, centred at
 * the bottom). Same honest copy + same localStorage key/logic as the legacy
 * CookieBanner, so dismissing either hides both. The legacy one stays for
 * the staff shell (untouched).
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'

const STORAGE_KEY = 'cookie-banner-dismissed'

function initialOpen() {
  try { return !localStorage.getItem(STORAGE_KEY) } catch { return true }
}

export default function RdCookieBanner() {
  // Client-only SPA — reading localStorage in the lazy initializer is
  // safe (no SSR/hydration) and avoids a setState-in-effect.
  const [open, setOpen] = useState(initialOpen)

  function dismiss() {
    setOpen(false)
    try { localStorage.setItem(STORAGE_KEY, '1') } catch { /* ignore */ }
  }

  if (!open) return null

  return (
    <div className="rd-cookie rd-glass" role="region" aria-label="Avís de cookies">
      <p style={{ fontSize: 13.5, lineHeight: 1.5, color: 'rgba(255,255,255,0.8)', margin: 0, flex: 1 }}>
        Només fem servir cookies estrictament necessàries per a la sessió i la
        seguretat. Zero tracking de tercers, zero analytics. Detall a la{' '}
        <Link to="/legal/cookies" style={{ color: '#fff', textDecoration: 'underline' }}>
          política de cookies
        </Link>.
      </p>
      <button
        type="button"
        onClick={dismiss}
        className="rd-btn rd-btn--hot"
        style={{ whiteSpace: 'nowrap', padding: '9px 18px', fontSize: 13 }}
      >
        Entès
      </button>
    </div>
  )
}
