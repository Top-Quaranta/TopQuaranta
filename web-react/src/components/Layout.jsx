/**
 * Layout — persistent shell wrapping every route.
 *
 * Two shells, picked by route (this is the permanent scope boundary of
 * the redisseny, not a temporary hack):
 *   - PUBLIC routes → the redisseny dark liquid-glass shell (rd/Header,
 *     rd/Footer, rd/CookieBanner, `.rd-root`). Full-bleed <main> so pages
 *     compose with full-width bands.
 *   - /staff/* → the legacy yellow shell, UNCHANGED ("staff no es toca").
 *
 * The redisseny is public-web only; staff keeps its current chrome.
 */
import { useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import TopQuarantaLogo from './TopQuarantaLogo'
import AccountButton from './AccountButton'
import FeedbackButton from './FeedbackButton'
import CookieBanner from './CookieBanner'
import RdHeader from './rd/Header'
import RdFooter from './rd/Footer'
import RdCookieBanner from './rd/CookieBanner'
import { useAuth } from '../context/AuthContext'
import { FeedbackProvider, useFeedbackContext } from '../context/FeedbackContext'

function Hamburger({ open }) {
  return open ? (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <path d="M18 6 6 18" /><path d="m6 6 12 12" />
    </svg>
  ) : (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  )
}

/* Skip link — shared by both shells. WCAG 2.4.1 (Bypass Blocks). */
function SkipLink() {
  return (
    <a
      href="#main-content"
      className="
        sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60]
        focus:px-3 focus:py-2 focus:rounded-md focus:bg-tq-ink focus:text-tq-yellow
        focus:font-semibold focus:shadow-lg focus:outline-none focus:ring-2
        focus:ring-tq-yellow
      "
    >
      Salta al contingut principal
    </a>
  )
}

export default function Layout({ children }) {
  return (
    <FeedbackProvider>
      <LayoutInner>{children}</LayoutInner>
    </FeedbackProvider>
  )
}

function LayoutInner({ children }) {
  const location = useLocation()
  const isStaff = location.pathname.startsWith('/staff')
  return isStaff
    ? <StaffShell>{children}</StaffShell>
    : <PublicShell>{children}</PublicShell>
}

/* ── Public redisseny shell ── */
function PublicShell({ children }) {
  return (
    <div className="rd-root">
      <SkipLink />
      <RdHeader />
      <main id="main-content" tabIndex="-1">
        {children}
      </main>
      <RdFooter />
      <RdCookieBanner />
    </div>
  )
}

/* ── Legacy yellow footer line (staff shell only) ── */
function StaffFooterLine() {
  const { target } = useFeedbackContext()
  return (
    <footer className="px-6 lg:px-12 py-6 text-xs opacity-60 flex flex-wrap items-center gap-x-2 gap-y-1">
      <Link to="/com-funciona" className="underline hover:opacity-100">Com funciona</Link>
      <span>·</span>
      <Link to="/legal" className="underline hover:opacity-100">Legal</Link>
      <span>·</span>
      <a href="https://github.com/Top-Quaranta/TopQuaranta" target="_blank" rel="noopener" className="underline hover:opacity-100">GitHub</a>
      {target && (
        <>
          <span>·</span>
          <FeedbackButton
            targetType={target.targetType}
            targetPk={target.targetPk}
            targetSlug={target.targetSlug}
            targetLabel={target.targetLabel}
          />
        </>
      )}
    </footer>
  )
}

/* ── Legacy yellow shell — UNCHANGED, only used for /staff/* ── */
function StaffShell({ children }) {
  const { profile } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)

  const navLinks = [
    { to: '/top',       label: 'Top'       },
    { to: '/artistes',  label: 'Artistes'  },
    { to: '/mapa',      label: 'Mapa'      },
    { to: '/comunitat', label: 'Comunitat' },
    ...(profile?.is_staff ? [{ to: '/staff', label: 'Staff' }] : []),
  ]

  const linkClass = ({ isActive }) =>
    'shrink-0 text-xs font-semibold px-3 py-1.5 rounded transition-colors whitespace-nowrap ' +
    (isActive
      ? 'bg-tq-ink text-tq-yellow'
      : 'text-tq-ink/80 hover:text-tq-ink hover:bg-tq-ink/10')

  return (
    <>
      <SkipLink />
      <header className="bg-tq-yellow text-tq-ink sticky top-0 z-40">
        <div className="h-12 flex items-center gap-6 px-6 lg:px-12">
          <Link to="/" className="shrink-0 text-tq-ink" aria-label="TopQuaranta — Inici">
            <TopQuarantaLogo className="h-7 w-auto" />
          </Link>
          <nav className="hidden md:flex flex-1 items-center gap-1 min-w-0" aria-label="Navegació principal">
            {navLinks.map(({ to, label }) => (
              <NavLink key={to} to={to} className={linkClass}>{label}</NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2 shrink-0 ml-auto md:ml-0">
            <AccountButton />
            <button
              type="button"
              onClick={() => setMenuOpen(o => !o)}
              aria-label={menuOpen ? 'Tancar menú' : 'Obrir menú'}
              aria-expanded={menuOpen}
              className="md:hidden p-1 text-tq-ink"
            >
              <Hamburger open={menuOpen} />
            </button>
          </div>
        </div>
        {menuOpen && (
          <div className="md:hidden border-t border-tq-ink/10">
            <nav className="flex flex-col px-4 py-2 gap-0.5" aria-label="Navegació mòbil">
              {navLinks.map(({ to, label }) => (
                <NavLink key={to} to={to} onClick={() => setMenuOpen(false)} className={linkClass}>
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>
        )}
      </header>

      <main id="main-content" className="px-6 lg:px-12 py-6 min-h-[60vh]" tabIndex="-1">
        {children}
      </main>

      <StaffFooterLine />
      <CookieBanner />
    </>
  )
}
