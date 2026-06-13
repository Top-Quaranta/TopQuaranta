/**
 * ComunitatLayout — shell for every /comunitat/* route (redisseny web).
 *
 * Anonymous visitors get the content full-bleed (the /comunitat funnel
 * and the public feed own their own bands — no sidebar). Authenticated
 * users get a dark sidebar (rd language) with the section links and a
 * padded content column. Sits inside the public rd shell, so the page
 * font/background come from `.rd-root`.
 */
import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const linkClass = ({ isActive }) =>
  'text-sm px-3 py-2 rounded-lg transition-colors whitespace-nowrap md:w-full md:text-left ' +
  (isActive
    ? 'bg-tq-yellow text-tq-ink font-semibold'
    : 'text-white/70 hover:text-white hover:bg-white/10')

export default function ComunitatLayout({ children }) {
  const { profile } = useAuth()

  // Anonymous: no sidebar — the funnel / public feed are full-bleed.
  if (!profile) return <>{children}</>

  const sections = [
    { to: '/comunitat/perfil',    label: 'Perfil'      },
    { to: '/comunitat',           label: 'Feed',       end: true },
    { to: '/comunitat/directori', label: 'Directori'   },
    { to: '/comunitat/publicar',  label: '+ Publicar'  },
    { to: '/comunitat/missatges', label: 'Missatges'   },
    { to: '/comunitat/public',    label: 'Feed públic' },
  ]

  return (
    <div className="flex flex-col md:flex-row min-h-[70vh]">
      <aside
        className="bg-tq-ink/80 text-white md:w-56 md:shrink-0 border-r border-white/10"
        aria-label="Navegació comunitat"
      >
        <div className="px-4 py-3 border-b border-white/10 hidden md:block">
          <p className="rd-kicker" style={{ fontSize: 13 }}>la comunitat</p>
        </div>
        <nav className="flex md:flex-col gap-0.5 px-2 py-2 overflow-x-auto md:overflow-visible">
          {sections.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className={linkClass}>
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex-1 min-w-0 px-6 lg:px-10 py-8">{children}</div>
    </div>
  )
}
