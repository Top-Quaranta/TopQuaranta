/**
 * FeedbackButton — "Corregir" action shown on content pages.
 *
 * Behaviour depends on who's looking:
 *   - staff           → direct link to the /staff/... edit page for
 *                       the current target
 *   - authenticated   → opens an inline modal with a textarea that
 *                       POSTs to /api/v1/feedback/ with the current
 *                       URL + target context
 *   - anonymous       → redirects to /compte/accedir?next=<here> so
 *                       they can either register or log in and then
 *                       come back to file the report
 *
 * The staff edit path is derived from `targetType`:
 *   artista → /staff/artistes/<pk>
 *   album   → /staff/albums/<pk>
 *   canco   → /staff/cancons/<pk>
 */
import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'

function staffEditPath(targetType, pk) {
  if (!pk) return null
  switch (targetType) {
    case 'artista': return `/staff/artistes/${pk}`
    case 'album':   return `/staff/albums/${pk}`
    case 'canco':   return `/staff/cancons/${pk}`
    default:        return null
  }
}

export default function FeedbackButton({
  targetType,
  targetPk,
  targetSlug,
  targetLabel,
  className = '',
}) {
  const { profile } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [open, setOpen] = useState(false)
  const [missatge, setMissatge] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  // Staff edits directly.
  if (profile?.is_staff) {
    const href = staffEditPath(targetType, targetPk)
    if (!href) return null
    return (
      <Link
        to={href}
        className={
          'text-xs font-semibold px-2.5 py-1 rounded bg-tq-yellow text-tq-ink hover:bg-tq-yellow-deep hover:text-white transition-colors ' +
          className
        }
      >
        Editar
      </Link>
    )
  }

  const buttonClass =
    'text-xs font-semibold px-2.5 py-1 rounded border border-white/20 text-white hover:bg-white/10 transition-colors ' +
    className

  // Anonymous → send to login with a `next` so they come back here.
  if (!profile) {
    const next = encodeURIComponent(location.pathname + location.search)
    return (
      <button
        type="button"
        onClick={() => navigate(`/compte/accedir?next=${decodeURIComponent(next)}`)}
        className={buttonClass}
      >
        Corregir
      </button>
    )
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.post('/feedback/', {
        url: location.pathname + location.search,
        target_type: targetType || 'altres',
        target_pk: targetPk || null,
        target_slug: targetSlug || '',
        target_label: targetLabel || '',
        missatge,
      })
      setDone(true)
      setMissatge('')
    } catch (err) {
      setError(err.payload?.errors?.missatge || err.message)
    } finally {
      setBusy(false)
    }
  }

  function close() {
    setOpen(false)
    setDone(false)
    setError('')
  }

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={buttonClass}>
        Corregir
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm p-0 sm:p-4"
          role="dialog"
          aria-modal="true"
          onClick={close}
        >
          <div
            className="bg-tq-ink-soft border border-white/10 rounded-t-xl sm:rounded-xl w-full max-w-lg text-white"
            onClick={e => e.stopPropagation()}
          >
            <header className="flex items-start justify-between p-4 border-b border-white/10">
              <div>
                <p className="text-[10px] uppercase tracking-widest text-white/60">Correcció</p>
                <h3 className="text-base font-bold mt-0.5">
                  {targetLabel ? `Reporta sobre: ${targetLabel}` : 'Reporta un error'}
                </h3>
              </div>
              <button
                type="button"
                onClick={close}
                aria-label="Tancar"
                className="text-white/60 hover:text-white p-1"
              >
                ✕
              </button>
            </header>

            {done ? (
              <div className="p-5">
                <p className="text-sm text-emerald-300">
                  Gràcies! Hem rebut la teva correcció.
                  L'equip la revisarà ben aviat.
                </p>
                <button
                  type="button"
                  onClick={close}
                  className="mt-4 text-xs font-semibold px-3 py-1.5 rounded bg-tq-yellow text-tq-ink hover:bg-tq-yellow-deep hover:text-white"
                >
                  Tancar
                </button>
              </div>
            ) : (
              <form onSubmit={submit} className="p-5 flex flex-col gap-3">
                <p className="text-xs text-white/70">
                  Explica'ns què veus malament: un nom incorrecte, una
                  localitat equivocada, una cançó que no hi hauria de
                  ser, un àlbum que falta, una imatge, etc. Qualsevol
                  detall ajuda.
                </p>
                <textarea
                  required
                  autoFocus
                  rows={5}
                  maxLength={5000}
                  value={missatge}
                  onChange={e => setMissatge(e.target.value)}
                  className="w-full px-3 py-2 rounded-md bg-white/[0.07] text-white text-sm border border-white/15 placeholder-white/40 focus:outline-none focus:border-tq-yellow resize-y"
                  placeholder="Què cal corregir?"
                />
                {error && <p className="text-xs text-red-300">{error}</p>}
                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={close}
                    className="text-xs font-semibold px-3 py-1.5 rounded border border-white/20 text-white hover:bg-white/10"
                  >
                    Cancel·lar
                  </button>
                  <button
                    type="submit"
                    disabled={busy || !missatge.trim()}
                    className="text-xs font-semibold px-3 py-1.5 rounded bg-tq-yellow text-tq-ink hover:bg-tq-yellow-deep hover:text-white disabled:opacity-50"
                  >
                    {busy ? 'Enviant…' : 'Enviar'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  )
}
