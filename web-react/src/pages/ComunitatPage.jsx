/**
 * ComunitatPage — /comunitat (redisseny web).
 *
 * Anonymous: the registration FUNNEL — hero + three glass feature cards
 * (EL DIRECTORI / PUBLICACIONS / MISSATGES), full-bleed (ComunitatLayout
 * renders anon children without the sidebar).
 *
 * Authenticated: the moderated unified feed (internal + public + own),
 * restyled in the new language inside the sidebar content column.
 * Endpoints unchanged: /comunitat/publicacions/ + /compte/dashboard/.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { stripMarkdown } from '../lib/strip-markdown'
import { useAuth } from '../context/AuthContext'
import useApi from '../hooks/useApi'
import { Band, Glow, Glass, Kicker, Crit } from '../components/rd/primitives'

const FILTRE_OPTS = [['', 'Tot'], ['internes', 'Internes'], ['publiques', 'Públiques'], ['meves', 'Meves']]

function PillFilter({ value, onChange }) {
  return (
    <div className="flex gap-1.5 flex-wrap" role="tablist" aria-label="Filtre de feed">
      {FILTRE_OPTS.map(([v, l]) => (
        <button
          key={v} type="button" role="tab" aria-selected={value === v}
          onClick={() => onChange(v)}
          className={`rd-pill${value === v ? ' rd-pill-on' : ''}`}
          style={value === v ? { background: 'var(--color-tq-yellow)', color: '#0a0a0a' } : undefined}
        >
          {l}
        </button>
      ))}
    </div>
  )
}

function formatDate(iso) { return iso ? iso.slice(0, 10) : '' }

function EstatBadge({ estat }) {
  const tone = {
    esborrany: 'bg-gray-200 text-gray-800',
    pendent: 'bg-yellow-100 text-yellow-900',
    publicat: 'bg-emerald-100 text-emerald-900',
    rebutjat: 'bg-red-100 text-red-900',
  }[estat] || 'bg-gray-200 text-gray-800'
  return <span className={'text-[10px] uppercase tracking-wide font-semibold px-2 py-0.5 rounded-full ' + tone}>{estat}</span>
}

/* ── Anonymous funnel ── */
const FEATURES = [
  { kicker: 'perfils públics', title: 'EL DIRECTORI', body: "Crea el teu perfil de músic i fes-te trobar: instrument, territori, què busques. El directori és obert i cercable." },
  { kicker: 'crides i novetats', title: 'PUBLICACIONS', body: 'Comparteix concerts, estrenes i crides per trobar gent. Les publicacions passen per moderació abans de sortir.' },
  { kicker: 'parla directament', title: 'MISSATGES', body: 'Escriu a qualsevol membre des del seu perfil. Notificacions per correu opcionals, sense soroll.' },
]

function AnonFunnel() {
  return (
    <>
      <Band tone="hero">
        <Glow variant="a" />
        <Glow variant="b" />
        <div className="max-w-3xl">
          <Kicker className="block mb-2">troba la teua gent</Kicker>
          <Crit as="h1" className="rd-hero-h1">LA <span style={{ color: 'var(--color-tq-yellow)' }}>COMUNITAT</span></Crit>
          <p className="rd-hero-sub">
            Toques algun instrument i busques grup? Sou un grup i us falta algú?
            Registra't i troba la teua gent al directori i a les publicacions.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link to="/compte/accedir?mode=registre" className="rd-btn rd-btn--hot">Registra't →</Link>
            <Link to="/compte/accedir" className="rd-btn rd-btn--ghost">Ja tinc compte</Link>
          </div>
        </div>
      </Band>

      <Band tone="ink2">
        <div className="rd-com-grid">
          {FEATURES.map(f => (
            <Glass as="article" key={f.title} className="rd-com-card">
              <Kicker color="var(--color-tq-yellow)">{f.kicker}</Kicker>
              <Crit as="h2" className="rd-com-title">{f.title}</Crit>
              <p className="rd-com-body">{f.body}</p>
            </Glass>
          ))}
        </div>
        <p className="rd-method">
          La comunitat és per a persones, no per a màrqueting: perfils reals,
          moderació humana i{' '}
          <Link to="/com-funciona" className="rd-method-link" style={{ color: 'var(--color-tq-yellow)' }}>cap vigilància de dades →</Link>
        </p>
      </Band>
    </>
  )
}

export default function ComunitatPage() {
  const { profile } = useAuth()
  const [filtre, setFiltre] = useState('')
  const [page, setPage] = useState(1)
  const _params = new URLSearchParams({ filtre, page })
  const { data } = useApi(profile ? `/comunitat/publicacions/?${_params}` : null)
  const { data: dashboard } = useApi(profile ? '/compte/dashboard/' : null)
  const visibleDirectori = !!dashboard?.perfil?.visible_directori

  if (!profile) return <AnonFunnel />

  return (
    <section className="max-w-3xl mx-auto text-white">
      <Glass className="rd-com-pitch">
        <Kicker color="var(--color-tq-yellow)">la comunitat</Kicker>
        <Crit as="h1" className="rd-com-title" style={{ marginTop: 6 }}>EL TEU ESPAI</Crit>
        <p className="rd-com-body" style={{ marginTop: 8 }}>
          Connecta, col·labora i comparteix projectes. Si fas música, activa el
          teu perfil al directori i fes saber que estàs obert a col·laboracions.
        </p>
        <Link
          to={visibleDirectori ? '/comunitat/directori' : '/comunitat/perfil'}
          className="rd-btn rd-btn--hot mt-4" style={{ fontSize: 13, padding: '9px 16px' }}
        >
          {visibleDirectori ? 'Explora el directori' : 'Activa el teu perfil'}
        </Link>
      </Glass>

      <div className="flex items-start justify-between gap-3 mt-6 mb-4 flex-wrap">
        <div>
          <Crit as="h2" style={{ fontSize: 22 }}>FEED</Crit>
          <p className="text-xs text-white/55 mt-0.5">Internes (només registrats) + públiques + les teves.</p>
        </div>
        <PillFilter value={filtre} onChange={v => { setPage(1); setFiltre(v) }} />
      </div>

      {!data && <p className="rd-empty">Carregant…</p>}
      {data?.results?.length === 0 && <p className="rd-empty">Cap publicació encara.</p>}
      <ul className="flex flex-col gap-3">
        {data?.results?.map(p => (
          <li key={p.pk}>
            <Link to={`/comunitat/${p.pk}`} className="rd-com-post rd-glass">
              <div className="flex items-center justify-between gap-2 mb-1">
                <h3 className="font-extrabold text-lg truncate" style={{ fontFamily: 'var(--font-body)' }}>{p.titol}</h3>
                <div className="flex gap-1 shrink-0">
                  {p.visibilitat === 'publica' && (
                    <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-900">Pública</span>
                  )}
                  <EstatBadge estat={p.estat} />
                </div>
              </div>
              <p className="text-sm text-white/70 line-clamp-3 whitespace-pre-wrap">{stripMarkdown(p.cos)}</p>
              <p className="text-[11px] text-white/45 mt-2">
                per {p.autor.nom_public}{p.autor.is_staff && ' · staff'}{p.publicat_at && ` · ${formatDate(p.publicat_at)}`}
              </p>
            </Link>
          </li>
        ))}
      </ul>

      {data?.num_pages > 1 && (
        <nav className="rd-pager" style={{ marginTop: 24, justifyContent: 'flex-start' }} aria-label="Paginació">
          <button type="button" disabled={!data.has_previous} onClick={() => setPage(p => p - 1)} className="rd-btn rd-btn--ghost">Anterior</button>
          <span className="text-sm text-white/60 tabular-nums">Pàg {data.page} de {data.num_pages}</span>
          <button type="button" disabled={!data.has_next} onClick={() => setPage(p => p + 1)} className="rd-btn rd-btn--ghost">Següent</button>
        </nav>
      )}
    </section>
  )
}
