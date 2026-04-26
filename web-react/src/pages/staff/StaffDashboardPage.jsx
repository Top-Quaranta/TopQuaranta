/**
 * StaffDashboardPage — landing for /staff.
 *
 * Grid of tool cards. Each card shows the tool name + a short
 * description + a live counter (open pending items) pulled from
 * `/api/v1/staff/dashboard/`. Cards are React Router <Link>s so
 * navigation stays SPA-internal.
 *
 * When the counters API is loading we render the cards without the
 * badge so the layout doesn't jump; when an area has 0 open items we
 * still render the card (the tool itself remains useful) but hide
 * the badge.
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
            <span className="ml-2 opacity-60">
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

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <Tile
          to="/staff/estat"
          title="Estat del sistema"
          desc="Inventari, pipelines, ML i cues — dashboard visual."
        />
        <Tile
          to="/staff/pendents"
          title="Artistes pendents"
          desc="Aprovar o descartar artistes auto-descoberts per la ingesta."
          count={c.artistes_pendents}
        />
        <Tile
          to="/staff/propostes"
          title="Propostes d'artistes"
          desc="Propostes d'usuaris per afegir artistes nous al sistema."
          count={c.propostes_obertes}
        />
        <Tile
          to="/staff/solicituds"
          title="Sol·licituds de gestió"
          desc="Usuaris demanant poder gestionar un artista existent."
          count={c.solicituds_gestio_obertes}
        />
        <Tile
          to="/staff/feedback"
          title="Feedback d'usuaris"
          desc="Correccions i errors reportats des de les pàgines públiques."
          count={c.feedback_obert}
        />
        <Tile
          to="/staff/publicacions"
          title="Publicacions pendents"
          desc="Publicacions públiques esperant aprovació."
          count={c.publicacions_pendents}
        />
        <Tile
          to="/staff/cancons"
          title="Cançons"
          desc="Cançons no verificades a revisar."
          count={c.cancons_no_verificades}
        />
        <Tile
          to="/staff/artistes"
          title="Artistes"
          desc="Llista, edició i creació manual d'artistes aprovats."
        />
        <Tile
          to="/staff/albums"
          title="Albums"
          desc="Edició d'àlbums i correcció de portades."
        />
        <Tile
          to="/staff/top"
          title="Top provisional"
          desc="Revisar el ranking diari i rebutjar entrades."
        />
        <Tile
          to="/staff/senyal"
          title="Senyal diari"
          desc="Dades brutes Last.fm (playcount + listeners) per dia."
        />
        <Tile
          to="/staff/historial"
          title="Historial de decisions"
          desc="Log d'aprovacions i rebuigs previs."
        />
        <Tile
          to="/staff/configuracio"
          title="Configuració global"
          desc="Coeficients de l'algorisme de ranking."
        />
        <Tile
          to="/staff/auditlog"
          title="Auditoria staff"
          desc="Registre immutable d'accions destructives."
        />
        <Tile
          to="/staff/usuaris"
          title="Usuaris"
          desc="Llista d'usuaris, moderació d'spam, reset 2FA."
        />
      </div>
    </section>
  )
}
