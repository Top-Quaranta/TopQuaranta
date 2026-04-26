/**
 * FilterPanel — collapsible filter drawer for staff list pages.
 *
 * Pattern: the parent owns the *applied* filter state (which drives
 * the API request). The panel owns a *pending* copy that staff edits
 * via the children (typically <Select>s and toggles); changes only
 * propagate to the parent on Apply.
 *
 * Usage (render-prop):
 *
 *   <FilterPanel
 *     applied={applied}
 *     defaults={DEFAULTS}
 *     onApply={next => { setApplied(next); setPage(1) }}
 *   >
 *     {(pending, setPending) => (
 *       <>
 *         <Select value={pending.mb} onChange={e => setPending({ mb: e.target.value })}>
 *           …
 *         </Select>
 *       </>
 *     )}
 *   </FilterPanel>
 *
 * The toggle button shows a count badge with the number of non-default
 * filters currently applied. Click outside the panel closes it
 * without applying — Apply requires an explicit button press so
 * staff doesn't accidentally re-fetch on every keystroke.
 */
import { useEffect, useRef, useState } from 'react'
import { Btn } from './StaffTable'
import MmIcon from '../MmIcon'

function activeCount(applied, defaults) {
  let n = 0
  for (const k of Object.keys(applied)) {
    if ((applied[k] ?? '') !== (defaults[k] ?? '')) n += 1
  }
  return n
}

export default function FilterPanel({
  applied,
  defaults,
  onApply,
  onReset,
  children,
}) {
  const [open, setOpen] = useState(false)
  const [pending, setPendingState] = useState({ ...applied })
  const panelRef = useRef(null)
  const buttonRef = useRef(null)

  // Re-sync pending when the parent's applied changes externally
  // (e.g. URL deep-link). Done via useEffect rather than state init
  // because the parent might mutate `applied` after mount.
  useEffect(() => { setPendingState({ ...applied }) }, [applied])

  // Close on outside click. We compare against both the panel and the
  // toggle button so clicking the button doesn't re-open immediately.
  useEffect(() => {
    if (!open) return
    function handleClick(e) {
      if (
        panelRef.current?.contains(e.target) ||
        buttonRef.current?.contains(e.target)
      ) return
      setOpen(false)
      setPendingState({ ...applied })  // discard unconfirmed edits
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open, applied])

  // Close with Escape key.
  useEffect(() => {
    if (!open) return
    function handleKey(e) {
      if (e.key === 'Escape') {
        setOpen(false)
        setPendingState({ ...applied })
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, applied])

  const setPending = patch => setPendingState(prev => ({ ...prev, ...patch }))
  const count = activeCount(applied, defaults)

  function apply() {
    onApply(pending)
    setOpen(false)
  }

  function reset() {
    const cleared = { ...defaults }
    setPendingState(cleared)
    onApply(cleared)
    if (onReset) onReset()
    setOpen(false)
  }

  return (
    <div className="relative inline-block">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-semibold border border-white/20 text-white hover:bg-white/10 transition-colors"
      >
        <MmIcon name="hamburger" className="h-4 w-4" label="Filtres" />
        Filtres
        {count > 0 && (
          <span
            className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 rounded-full text-[10px] font-bold"
            style={{
              background: 'var(--color-tq-yellow)',
              color: 'var(--mm-color-ink, #0a0a0a)',
            }}
          >
            {count}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={panelRef}
          className="absolute right-0 mt-2 w-[min(28rem,calc(100vw-2rem))] z-30 bg-white text-tq-ink rounded-lg shadow-xl border border-black/10 p-4"
          role="dialog"
          aria-label="Filtres"
        >
          <div className="flex flex-col gap-3">
            {children(pending, setPending)}
          </div>
          <div className="flex items-center justify-between gap-2 mt-4 pt-3 border-t border-black/10">
            <button
              type="button"
              onClick={reset}
              className="text-xs underline opacity-70 hover:opacity-100"
            >
              Restablir
            </button>
            <div className="flex gap-2">
              <Btn
                tone="secondary"
                onClick={() => {
                  setOpen(false)
                  setPendingState({ ...applied })
                }}
              >
                Cancel·lar
              </Btn>
              <Btn tone="primary" onClick={apply}>
                Aplicar
              </Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
