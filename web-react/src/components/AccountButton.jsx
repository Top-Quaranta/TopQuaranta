/**
 * AccountButton — header slot for the user/login action.
 *
 * Always a single silhouette icon on the yellow bar.
 *   - Not authenticated → links to /compte/accedir.
 *   - Authenticated     → links to /compte. A small red badge appears
 *                         when the user has unread direct messages.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api } from '../lib/api'

function UserIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="8.5" r="3.2" />
      <path d="M4.5 20.5 C5 16 8.2 13.5 12 13.5 C15.8 13.5 19 16 19.5 20.5" />
    </svg>
  )
}

export default function AccountButton() {
  const { profile, loading } = useAuth()
  const [unread, setUnread] = useState(0)

  // Poll unread-messages count. 60s is a fair compromise between
  // "fresh" and "don't hammer the API" for a passive indicator.
  useEffect(() => {
    if (!profile) { setUnread(0); return }
    let cancelled = false
    async function load() {
      try {
        const inbox = await api.get('/missatges/')
        if (!cancelled) setUnread(inbox.no_llegits_total || 0)
      } catch { /* silently ignore */ }
    }
    load()
    const id = setInterval(load, 60_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [profile])

  if (loading) {
    return <span className="h-8 w-8 rounded-full bg-tq-ink/10 animate-pulse" />
  }

  // When the user has unread DMs, the icon doubles as a missatges
  // shortcut — clicking the badge should land you on the inbox, not
  // on the dashboard. Without unread we keep the dashboard target.
  const to = profile
    ? (unread > 0 ? '/comunitat/missatges' : '/compte')
    : '/compte/accedir'
  const label = profile
    ? `${profile.email}${unread > 0 ? ` (${unread} missatge${unread === 1 ? '' : 's'} no llegits)` : ''}`
    : 'Accedir'

  return (
    <Link
      to={to}
      title={label}
      aria-label={label}
      className="relative inline-flex items-center justify-center h-8 w-8 rounded-full text-tq-ink hover:bg-tq-ink hover:text-tq-yellow transition-colors"
    >
      <UserIcon />
      {unread > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-600 text-white text-[10px] font-bold flex items-center justify-center leading-none">
          {unread > 9 ? '9+' : unread}
        </span>
      )}
    </Link>
  )
}
