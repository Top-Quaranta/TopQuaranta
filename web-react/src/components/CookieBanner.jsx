/**
 * CookieBanner — discreet first-visit notice (Sprint J).
 *
 * Strict-necessary cookies don't legally need consent (Directiva
 * e-Privacy art. 5.3 ex. 2), but visitors deserve to know what's
 * being set. Banner is informative, non-blocking, dismissible
 * with a single click. State persists in localStorage so it
 * doesn't reappear on every visit.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

const STORAGE_KEY = 'cookie-banner-dismissed'

export default function CookieBanner() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) setOpen(true)
    } catch {
      // localStorage blocked (private mode, strict settings) — show
      // the banner this session, don't try to persist dismissal.
      setOpen(true)
    }
  }, [])

  function dismiss() {
    setOpen(false)
    try { localStorage.setItem(STORAGE_KEY, '1') } catch { /* ignore */ }
  }

  if (!open) return null

  return (
    <div
      role="region"
      aria-label="Avís de cookies"
      className="fixed bottom-3 left-3 right-3 sm:left-auto sm:max-w-md z-50
                 bg-tq-ink text-white rounded-lg shadow-2xl p-4 text-sm
                 border border-white/10"
    >
      <p className="font-bold font-display text-base mb-1">Cookies</p>
      <p className="text-white/80 leading-relaxed text-xs">
        Només fem servir cookies estrictament necessàries per a la
        sessió i la seguretat. Zero tracking de tercers, zero
        analytics. Detall a la{' '}
        <Link to="/legal/cookies" className="underline hover:text-tq-yellow transition-colors">
          política de cookies
        </Link>.
      </p>
      <div className="flex justify-end mt-3">
        <button
          type="button"
          onClick={dismiss}
          className="px-3 py-1.5 bg-tq-yellow text-tq-ink text-xs font-semibold rounded hover:bg-tq-yellow-deep hover:text-white transition-colors"
        >
          Entès
        </button>
      </div>
    </div>
  )
}
