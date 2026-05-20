/**
 * Tabs — accessible tabbed navigation with optional URL-hash sync.
 *
 * Sprint Portal Artista Ampliat (2026-05-20): one shared primitive
 * for `/compte/artista/<slug>/` and reusable elsewhere. The active
 * tab can be driven externally (`activeKey` + `onChange`) or it can
 * mirror the URL hash (`syncHash`); the hash variant gives free
 * back-button + permalink support without an external state store.
 *
 * Props:
 *   tabs       array of `{key, label, count?}`
 *   activeKey  controlled active key. If syncHash is true and
 *              activeKey is not provided, falls back to URL hash.
 *   onChange   callback(key) — fired on tab click. When syncHash
 *              is true the hook also updates window.location.hash.
 *   syncHash   bool, default false. When true the component reads
 *              and writes `window.location.hash`.
 *
 * Design: mm-design tokens. Bottom-underline on active tab uses
 * `tq-yellow`; inactive tabs sit in `text-white/60` over the dark
 * `/compte` shell. Counts appear as a thin pill.
 */
import { useCallback, useEffect, useState } from 'react'

function readHashKey() {
  if (typeof window === 'undefined') return ''
  return (window.location.hash || '').replace(/^#/, '')
}

export default function Tabs({
  tabs,
  activeKey,
  onChange,
  syncHash = false,
  className = '',
}) {
  const [hashKey, setHashKey] = useState(syncHash ? readHashKey() : '')

  useEffect(() => {
    if (!syncHash) return undefined
    const handle = () => setHashKey(readHashKey())
    window.addEventListener('hashchange', handle)
    return () => window.removeEventListener('hashchange', handle)
  }, [syncHash])

  // Resolve the active key. Priority: explicit prop > hash > first tab.
  const resolvedKey =
    activeKey ||
    (syncHash && tabs.some(t => t.key === hashKey) ? hashKey : '') ||
    (tabs[0]?.key ?? '')

  const handleClick = useCallback(
    key => {
      if (syncHash) {
        // `history.replaceState` keeps the back button useful (a hash
        // change wouldn't add a separate entry anyway, but being
        // explicit avoids surprising scroll resets).
        window.history.replaceState(null, '', `#${key}`)
        setHashKey(key)
      }
      onChange?.(key)
    },
    [syncHash, onChange]
  )

  return (
    <div className={`border-b border-white/10 ${className}`} role="tablist">
      <div className="flex gap-1 overflow-x-auto">
        {tabs.map(t => {
          const isActive = t.key === resolvedKey
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => handleClick(t.key)}
              className={[
                'inline-flex items-center gap-2 px-4 py-3 text-sm font-semibold transition-colors',
                'border-b-2 -mb-px focus:outline-none focus-visible:ring-2 focus-visible:ring-tq-yellow rounded-t',
                isActive
                  ? 'text-tq-yellow border-tq-yellow'
                  : 'text-white/60 border-transparent hover:text-white',
              ].join(' ')}
            >
              <span>{t.label}</span>
              {typeof t.count === 'number' && (
                <span
                  className={
                    'inline-flex items-center justify-center min-w-[1.25rem] px-1.5 py-0.5 rounded-full text-[10px] font-semibold ' +
                    (isActive
                      ? 'bg-tq-yellow text-tq-ink'
                      : 'bg-white/10 text-white/70')
                  }
                >
                  {t.count}
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
