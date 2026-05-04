/**
 * StaffDashboardPage — landing for /staff.
 *
 * Tools grouped by the same taxonomy as the left sidebar
 * (`StaffLayout::GROUPS`) so the visual hierarchy stays consistent
 * and the operator's mental model is reused: whatever they're used to
 * scanning down on the side, they now also scan down here. Each group
 * gets its own banner; tools render as cards with a description and an
 * optional live counter pulled from `/api/v1/staff/dashboard/`.
 *
 * Adding a new staff tool: drop it in the right `GROUPS` entry and
 * (if it has a queue) wire its counter through `count`.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'

function CountBadge({ n }) {
  if (!n) return null
  return (
    <span className="ml-auto inline-flex items-center justify-center text-[11px] font-semibold bg-tq-yellow text-tq-ink rounded-full px-2 py-0.5 min-w-[1.5rem]">
      {n}
    </span>
  )
}

function Tile({ to, title, desc, count }) {
  return (
    <Link
      to={to}
      className="group flex flex-col p-4 bg-white text-tq-ink rounded-lg border border-black/5 hover:border-tq-ink/30 hover:shadow transition-all"
    >
      <div className="flex items-start gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <CountBadge n={count} />
      </div>
      <p className="text-xs opacity-70 mt-1 leading-snug">{desc}</p>
    </Link>
  )
}

// Each group renders as a banner + grid of tiles. `countKey` indexes
// into the dashboard counters payload — leave it `null` for evergreen
// tools that have no queue. Mirrors `StaffLayout::GROUPS` 1-to-1.
const GROUPS = [
  {
    label: 'Visió general',
    items: [
      { to: '/staff/estat',     title: 'Estat del sistema', desc: 'Inventari, pipelines, ML i cues — dashboard visual.' },
      { to: '/staff/analytics', title: 'Analytics',         desc: 'Mètriques agregades del web, comunitat i xarxes socials.' },
    ],
  },
  {
    label: 'Cua del dia',
    items: [
      { to: '/staff/pendents',     title: 'Artistes pendents',     desc: 'Aprovar o descartar artistes auto-descoberts per la ingesta.', countKey: 'artistes_pendents'        },
      { to: '/staff/propostes',    title: "Propostes d'artistes",  desc: "Propostes d'usuaris per afegir artistes nous al sistema.",     countKey: 'propostes_obertes'        },
      { to: '/staff/solicituds',   title: 'Sol·licituds de gestió', desc: 'Usuaris demanant poder gestionar un artista existent.',        countKey: 'solicituds_gestio_obertes' },
      { to: '/staff/feedback',     title: "Feedback d'usuaris",    desc: 'Correccions i errors reportats des de les pàgines públiques.', countKey: 'feedback_obert'           },
    ],
  },
  {
    label: 'Catàleg',
    items: [
      { to: '/staff/artistes', title: 'Artistes', desc: "Llista, edició i creació manual d'artistes aprovats." },
      { to: '/staff/cancons',  title: 'Cançons',  desc: 'Cançons no verificades a revisar.', countKey: 'cancons_no_verificades' },
      { to: '/staff/albums',   title: 'Àlbums',   desc: "Edició d'àlbums i correcció de portades." },
    ],
  },
  {
    label: 'Top',
    items: [
      { to: '/staff/top', title: 'Top provisional', desc: 'Revisar el ranking diari i rebutjar entrades.' },
    ],
  },
  {
    label: 'Comunitat',
    items: [
      { to: '/staff/publicacions', title: 'Publicacions pendents', desc: 'Publicacions públiques esperant aprovació.', countKey: 'publicacions_pendents' },
      { to: '/staff/usuaris',      title: 'Usuaris',               desc: "Llista d'usuaris, moderació d'spam, reset 2FA." },
    ],
  },
  {
    label: 'Distribució',
    items: [
      { to: '/staff/social', title: 'Distribució multi-canal', desc: 'Calendari setmanal a Instagram, Mastodon, Bluesky, Telegram, newsletter i RSS.' },
    ],
  },
  {
    label: 'Diagnòstic',
    items: [
      { to: '/staff/senyal',    title: 'Senyal diari',          desc: 'Dades brutes Last.fm (playcount + listeners) per dia.' },
      { to: '/staff/historial', title: 'Historial de decisions', desc: "Log d'aprovacions i rebuigs previs." },
      { to: '/staff/auditlog',  title: 'Auditoria staff',       desc: "Registre immutable d'accions destructives." },
    ],
  },
  {
    label: 'Sistema',
    items: [
      { to: '/staff/configuracio', title: 'Configuració global', desc: "Coeficients de l'algorisme de ranking i kill-switches." },
    ],
  },
]

export default function StaffDashboardPage() {
  const [counts, setCounts] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    api.get('/staff/dashboard/')
      .then(data => {
        if (active) setCounts(data)
      })
      .catch(e => {
        if (active) setError(e.message || 'Error')
      })
    return () => {
      active = false
    }
  }, [])

  const c = counts || {}

  return (
    <section>
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-white">Panell intern</h1>
        <p className="text-sm text-white/70">
          Eines d'administració TopQuaranta
          {counts && (
            <span className="ml-2 opacity-90">
              · {c.usuaris_total} usuaris actius
            </span>
          )}
        </p>
      </header>

      {error && (
        <p className="mb-4 text-sm text-red-300">
          No s'han pogut carregar els comptadors: {error}
        </p>
      )}

      <div className="space-y-7">
        {GROUPS.map(group => (
          <div key={group.label}>
            <h2 className="text-[11px] uppercase tracking-widest text-white/60 mb-2">
              {group.label}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {group.items.map(item => (
                <Tile
                  key={item.to}
                  to={item.to}
                  title={item.title}
                  desc={item.desc}
                  count={item.countKey ? c[item.countKey] : undefined}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
