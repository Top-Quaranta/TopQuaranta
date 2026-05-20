/**
 * ConfirmDialog — accessible modal for destructive / consequential
 * actions. Sprint Portal Artista Ampliat (2026-05-20).
 *
 * Props:
 *   open             bool — render only when true
 *   title            string
 *   body             ReactNode — short explanation of what'll happen
 *   confirmLabel     string, default "Confirmar"
 *   cancelLabel      string, default "Cancel·lar"
 *   requireCheckbox  bool, default false — when true the confirm
 *                    button stays disabled until the user ticks
 *                    `checkboxLabel`. Used for hard-to-undo actions.
 *   checkboxLabel    string — visible only if requireCheckbox
 *   severity         "danger" | "warning" — colours the confirm
 *                    button + the icon strip. Default "warning".
 *   onConfirm        callback — fired on confirm click. May return
 *                    a Promise; the dialog stays open until it
 *                    resolves so callers can show a busy state.
 *   onCancel         callback — fired on ESC, backdrop click, or
 *                    cancel button.
 *
 * Behaviour:
 *   * ESC closes (calls onCancel).
 *   * Enter confirms — but only if the checkbox-guard (when present)
 *     is satisfied.
 *   * Backdrop click closes.
 *   * Focus is moved to the confirm button on open; a basic focus
 *     trap keeps Tab/Shift+Tab within the dialog so screen readers
 *     don't escape to the page behind.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

const SEVERITY = {
  danger: {
    button: 'bg-red-600 hover:bg-red-700 text-white',
    accent: 'border-l-red-600',
  },
  warning: {
    button: 'bg-tq-yellow hover:bg-tq-yellow-deep text-tq-ink hover:text-white',
    accent: 'border-l-tq-yellow',
  },
}

export default function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancel·lar',
  requireCheckbox = false,
  checkboxLabel = '',
  severity = 'warning',
  onConfirm,
  onCancel,
}) {
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const confirmBtnRef = useRef(null)
  const dialogRef = useRef(null)

  // Reset checkbox + focus the confirm button when the dialog opens.
  useEffect(() => {
    if (!open) {
      setChecked(false)
      setBusy(false)
      return
    }
    const t = setTimeout(() => confirmBtnRef.current?.focus(), 0)
    return () => clearTimeout(t)
  }, [open])

  const canConfirm = !busy && (!requireCheckbox || checked)

  const handleConfirm = useCallback(async () => {
    if (!canConfirm) return
    setBusy(true)
    try {
      await onConfirm?.()
    } finally {
      // The caller is expected to close the dialog by flipping
      // `open` to false in response to onConfirm. We only reset
      // local busy state for the safety of re-mount scenarios.
      setBusy(false)
    }
  }, [canConfirm, onConfirm])

  useEffect(() => {
    if (!open) return undefined
    const handleKey = e => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onCancel?.()
      } else if (e.key === 'Enter' && canConfirm) {
        e.preventDefault()
        handleConfirm()
      } else if (e.key === 'Tab') {
        // Basic focus trap.
        const root = dialogRef.current
        if (!root) return
        const focusables = root.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
        if (focusables.length === 0) return
        const first = focusables[0]
        const last = focusables[focusables.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, canConfirm, handleConfirm, onCancel])

  if (!open) return null

  const sev = SEVERITY[severity] || SEVERITY.warning

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Tancar"
        onClick={onCancel}
        className="absolute inset-0 bg-black/70"
      />
      <div
        ref={dialogRef}
        className={`relative bg-white text-tq-ink rounded-lg shadow-xl max-w-md w-full border-l-4 ${sev.accent}`}
      >
        <div className="p-5 space-y-3">
          <h2 id="confirm-title" className="text-base font-semibold">
            {title}
          </h2>
          <div className="text-sm text-tq-ink/80">{body}</div>
          {requireCheckbox && (
            <label className="flex items-start gap-2 text-sm cursor-pointer mt-2">
              <input
                type="checkbox"
                checked={checked}
                onChange={e => setChecked(e.target.checked)}
                className="mt-0.5"
              />
              <span>{checkboxLabel || 'Entenc el risc'}</span>
            </label>
          )}
        </div>
        <div className="px-5 py-3 bg-gray-50 flex items-center justify-end gap-2 rounded-b-lg">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm font-semibold text-tq-ink/70 hover:text-tq-ink"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmBtnRef}
            type="button"
            onClick={handleConfirm}
            disabled={!canConfirm}
            className={`px-4 py-2 rounded-md text-sm font-semibold transition-colors disabled:opacity-50 ${sev.button}`}
          >
            {busy ? '…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
