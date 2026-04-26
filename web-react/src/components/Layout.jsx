/**
 * Layout — persistent shell wrapping every route.
 *
 * Monolingual: the project is Catalan-only, so no LanguageToggle.
 * Account button is icon-only (user silhouette) — an inline CTA is
 * noise on a branded yellow bar.
 *
 * Footer: a single line in the page's own colour context — "Open
 * source · GitHub · Privacy". No big black box.
 */
import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import TopQuarantaLogo from './TopQuarantaLogo'
import AccountButton from './AccountButton'
import FeedbackButton from './FeedbackButton'
import CookieBanner from './CookieBanner'
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

function FooterLine() {
  const { target } = useFeedbackContext()
  return (
    <footer className="px-6 lg:px-12 py-6 text-xs opacity-60 flex flex-wrap items-center gap-x-2 gap-y-1">
      <Link to="/com-funciona" className="underline hover:opacity-100">
        Com funciona
      </Link>
      <span>·</span>
      <Link to="/legal" className="underline hover:opacity-100">
        Legal
      </Link>
      <span>·</span>
      <a
        href="https://github.com/miquelmatoses/TopQuaranta"
        target="_blank"
        rel="noopener"
        className="underline hover:opacity-100"
      >
        GitHub
      </a>
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

export default function Layout({ children }) {
  return (
    <FeedbackProvider>
      <LayoutInner>{children}</LayoutInner>
    </FeedbackProvider>
  )
}

function LayoutInner({ children }) {
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
      {/* Skip link — visible only when focused via keyboard. WCAG 2.4.1
          (Bypass Blocks). Lets keyboard users jump past the header /
          main nav straight into the page content. */}
      <a
        href="#main-content"
        className="
          sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50
          focus:px-3 focus:py-2 focus:rounded-md focus:bg-tq-ink focus:text-tq-yellow
          focus:font-semibold focus:shadow-lg focus:outline-none focus:ring-2
          focus:ring-tq-yellow
        "
      >
        Salta al contingut principal
      </a>

      {/* ── Yellow header ── */}
      <header className="bg-tq-yellow text-tq-ink sticky top-0 z-40">
        <div className="h-12 flex items-center gap-6 px-6 lg:px-12">
          <Link to="/" className="shrink-0 text-tq-ink" aria-label="TopQuaranta — Inici">
            <TopQuarantaLogo className="h-7 w-auto" />
          </Link>

          <nav
            className="hidden md:flex flex-1 items-center gap-1 min-w-0"
            aria-label="Navegació principal"
          >
            {navLinks.map(({ to, label }) => (
              <NavLink key={to} to={to} className={linkClass}>
                {label}
              </NavLink>
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
                <NavLink
                  key={to}
                  to={to}
                  onClick={() => setMenuOpen(false)}
                  className={linkClass}
                >
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>
        )}
      </header>

      {/* ── Main — full-width container with lg side padding ── */}
      <main id="main-content" className="px-6 lg:px-12 py-6 min-h-[60vh]" tabIndex="-1">
        {children}
      </main>

      {/* ── Inline footer — single line, body colour context ── */}
      <FooterLine />

      {/* Cookie banner — shows once per browser; legally informative
          (only strictly necessary cookies, no consent needed but
          visitors deserve to know). */}
      <CookieBanner />
    </>
  )
}
