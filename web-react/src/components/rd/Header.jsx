/**
 * rd/Header — dark liquid-glass site header (the only production variant;
 * the prototype's yellow header is a Tweak, not shipped — decision 1).
 *
 * Real routing (react-router NavLink) + real auth (useAuth). Active link
 * fills with the brand yellow + ink text. Mobile (<900px): nav collapses
 * to a hamburger menu. The skip-link stays in Layout.
 */
import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import TopQuarantaLogo from '../TopQuarantaLogo'
import { useAuth } from '../../context/AuthContext'

const NAV = [
  { to: '/', label: 'Inici', end: true },
  { to: '/top', label: 'Top' },
  { to: '/artistes', label: 'Artistes' },
  { to: '/mapa', label: 'Mapa' },
  { to: '/comunitat', label: 'Comunitat' },
]

function linkClass({ isActive }) {
  return `rd-hdr-link${isActive ? ' on' : ''}`
}
const activeStyle = ({ isActive }) =>
  isActive ? { background: 'var(--color-tq-yellow)', color: '#0a0a0a' } : undefined

export default function Header() {
  const { profile } = useAuth()
  const [open, setOpen] = useState(false)
  const authed = !!profile?.is_authenticated
  // Anonymous visitors get the public community landing (the authed
  // /comunitat zone bounces them to login); registered users go straight in.
  const base = NAV.map(n =>
    n.to === '/comunitat'
      ? { ...n, to: authed ? '/comunitat' : '/comunitat-musics' }
      : n,
  )
  const nav = profile?.is_staff
    ? [...base, { to: '/staff', label: 'Staff' }]
    : base

  return (
    <header className="rd-hdr">
      <div className="rd-hdr-inner">
        <Link to="/" className="shrink-0 flex items-center" aria-label="TopQuaranta — Inici">
          <TopQuarantaLogo className="h-[26px] w-auto" />
        </Link>

        <nav className="rd-hdr-nav" aria-label="Navegació principal">
          {nav.map(n => (
            <NavLink key={n.to} to={n.to} end={n.end} className={linkClass} style={activeStyle}>
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div className="rd-hdr-right">
          {profile?.is_authenticated ? (
            <Link
              to="/compte"
              className="rd-hdr-user"
              style={{ background: 'var(--color-tq-yellow)' }}
              aria-label="El meu compte"
            >
              {(profile.email || '?').trim().charAt(0).toUpperCase()}
            </Link>
          ) : (
            <Link to="/compte/accedir" className="rd-hdr-acc" aria-label="Accedir">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
              </svg>
            </Link>
          )}
          <button
            type="button"
            className="rd-hdr-burger"
            onClick={() => setOpen(o => !o)}
            aria-label={open ? 'Tancar menú' : 'Obrir menú'}
            aria-expanded={open}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
              {open ? <g><path d="M18 6 6 18" /><path d="m6 6 12 12" /></g>
                : <g><path d="M3 6h18" /><path d="M3 12h18" /><path d="M3 18h18" /></g>}
            </svg>
          </button>
        </div>
      </div>

      {open && (
        <nav className="rd-hdr-mobile" aria-label="Navegació mòbil">
          {nav.map(n => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={linkClass}
              style={activeStyle}
              onClick={() => setOpen(false)}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  )
}
