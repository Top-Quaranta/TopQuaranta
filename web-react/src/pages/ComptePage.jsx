/**
 * ComptePage — authenticated account hub (/compte), redisseny web.
 *
 * Restyled to the dark-glass language; all data/logic conserved:
 * /compte/dashboard/, the managed-artists + propostes grids, the stats
 * tiles, the contextual guidance cards, the onboarding bounce and the
 * staff CTA. Surfaces are glass; ui/Badge (colour pills) kept as-is.
 */
import useApi from '../hooks/useApi'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import Alert from '../components/ui/Alert'
import Badge from '../components/ui/Badge'
import { useAuth } from '../context/AuthContext'
import { artistaUrl } from '../lib/urls'
import { Band, Glass, Kicker, Crit, Numeral } from '../components/rd/primitives'

const ESTAT_VARIANT = { pendent: 'warning', aprovat: 'success', rebutjat: 'danger' }
const ESTAT_LABEL = { pendent: 'Pendent', aprovat: 'Aprovat', rebutjat: 'Rebutjat' }

function EstatBadge({ estat }) {
  return <Badge variant={ESTAT_VARIANT[estat] || 'default'} className="rounded-full">{ESTAT_LABEL[estat] || estat}</Badge>
}

function PerfilCard({ user, onLogout }) {
  return (
    <Glass as="article" className="rd-cc-card flex flex-col">
      <Kicker color="var(--color-tq-yellow)">perfil</Kicker>
      <h2 className="text-lg font-extrabold mt-1 truncate" style={{ fontFamily: 'var(--font-body)' }} title={user?.email}>{user?.email}</h2>
      {user?.username && user.username !== user.email && <p className="text-sm text-white/55 truncate mt-0.5">@{user.username}</p>}
      {user?.date_joined && <p className="text-xs text-white/45 mt-1">Membre des del {user.date_joined.slice(0, 10)}</p>}
      <div className="flex gap-2 mt-auto pt-4">
        <Link to="/compte/perfil" className="rd-btn rd-btn--hot flex-1" style={{ justifyContent: 'center', fontSize: 13, padding: '9px 14px' }}>Editar</Link>
        <button type="button" onClick={onLogout} className="rd-btn rd-btn--ghost" style={{ fontSize: 13, padding: '9px 14px' }}>Sortir</button>
      </div>
    </Glass>
  )
}

function StatsCard({ stats, artistaNom }) {
  const tiles = [
    { label: 'Setmanes', value: stats.setmanes_al_ranking },
    { label: 'Millor posició', value: stats.millor_posicio ? `#${stats.millor_posicio}` : '—' },
    { label: 'Cançons', value: stats.cancons_al_ranking },
    { label: 'Territoris', value: stats.territoris_presents },
  ]
  return (
    <Glass as="article" className="rd-cc-card md:col-span-2">
      <Kicker color="var(--color-tq-yellow)">{artistaNom} al top</Kicker>
      <dl className="grid grid-cols-4 gap-2 mt-3">
        {tiles.map(t => (
          <div key={t.label} className="text-center">
            <dd><Numeral n={t.value ?? '—'} size={28} /></dd>
            <dt className="text-[10px] text-white/50 uppercase tracking-wide mt-1">{t.label}</dt>
          </div>
        ))}
      </dl>
    </Glass>
  )
}

function QualitatPill({ qualitat }) {
  if (!qualitat) return null
  const { score, n_alerts } = qualitat
  const variant = score === 100 ? 'success' : score >= 60 ? 'warning' : 'danger'
  const alertsTxt = n_alerts === 0 ? 'cap alerta' : `${n_alerts} alerta${n_alerts === 1 ? '' : 's'}`
  return <Badge variant={variant} className="rounded-full">{score}% complet · {alertsTxt}</Badge>
}

function ArtistaCard({ u, millorPosicio }) {
  const portalUrl = `/compte/artista/${u.artista.slug}/`
  return (
    <Glass className="p-4 flex flex-col gap-2 min-h-[6.5rem]">
      <Link to={u.verificat ? portalUrl : artistaUrl(u.artista.slug)} className="block">
        <p className="font-semibold truncate text-white">{u.artista.nom}</p>
      </Link>
      {u.verificat && (
        <p className="text-xs text-white/55">
          {millorPosicio ? <>Millor posició: <strong className="text-white tabular-nums">#{millorPosicio}</strong></> : <>Encara no està al top.</>}
        </p>
      )}
      <div className="flex flex-wrap gap-1.5 mt-auto items-center">
        {u.verificat && <Badge variant="success" className="rounded-full">Verificat</Badge>}
        {u.verificat && <QualitatPill qualitat={u.qualitat} />}
        <EstatBadge estat={u.estat} />
        {u.verificat && u.artista.pk && (
          <div className="ml-auto flex gap-1.5">
            <Link to="/mapa" className="rd-btn rd-btn--ghost" style={{ fontSize: 11, padding: '5px 10px' }}>Mapa</Link>
            <Link to={portalUrl} className="rd-btn rd-btn--hot" style={{ fontSize: 11, padding: '5px 10px' }}>Gestionar</Link>
          </div>
        )}
      </div>
    </Glass>
  )
}

function GuidanceCard({ title, body, ctaTo, ctaLabel }) {
  return (
    <Glass as="article" className="p-4 flex items-start gap-3">
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-sm text-white">{title}</p>
        <p className="text-xs text-white/65 mt-0.5 leading-relaxed">{body}</p>
        <Link to={ctaTo} className="rd-btn rd-btn--hot mt-2" style={{ fontSize: 12, padding: '7px 13px' }}>{ctaLabel}</Link>
      </div>
    </Glass>
  )
}

function PropostaCard({ p }) {
  const inner = (
    <>
      <p className="font-semibold truncate text-white">{p.nom}</p>
      {p.justificacio && <p className="text-xs text-white/55 line-clamp-2">{p.justificacio}</p>}
      <div className="mt-auto flex items-center gap-2">
        <EstatBadge estat={p.estat} />
        {p.created_at && <span className="text-[10px] text-white/40">{p.created_at.slice(0, 10)}</span>}
      </div>
    </>
  )
  const cls = 'rd-glass p-4 flex flex-col gap-2 min-h-[6.5rem] block'
  return p.artista_creat ? <Link to={artistaUrl(p.artista_creat.slug)} className={cls}>{inner}</Link> : <div className={cls}>{inner}</div>
}

function AddCard({ to, label }) {
  return (
    <Link to={to} className="flex items-center justify-center bg-transparent border-2 border-dashed border-white/20 hover:border-tq-yellow hover:bg-white/5 text-white rounded-2xl p-4 min-h-[6.5rem] transition-colors">
      <span className="text-sm font-semibold"><span className="text-tq-yellow mr-1.5">+</span> {label}</span>
    </Link>
  )
}

export default function ComptePage() {
  const { profile, loading: authLoading, signOut } = useAuth()
  const navigate = useNavigate()
  const { data, error, loading } = useApi(!authLoading && profile ? '/compte/dashboard/' : null)

  if (authLoading) return null
  if (!profile) return <Navigate to="/compte/accedir" replace />
  if (profile.is_authenticated && profile.onboarding_complet === false) return <Navigate to="/onboarding" replace />

  const handleLogout = async () => { await signOut(); navigate('/', { replace: true }) }
  const nom = (data?.user?.username && data.user.username !== data.user.email) ? data.user.username : (profile.email || '').split('@')[0]

  return (
    <Band tone="ink2">
      <div className="max-w-6xl mx-auto flex flex-col gap-7">
        <header>
          <Kicker color="var(--color-tq-yellow)">el teu compte</Kicker>
          <Crit as="h1" className="rd-sec-title">HOLA{nom ? `, ${nom.toUpperCase()}` : ''}</Crit>
        </header>

        <div className={'grid gap-4 ' + (data?.stats ? 'grid-cols-1 md:grid-cols-3' : 'grid-cols-1')}>
          <PerfilCard user={data?.user || profile} onLogout={handleLogout} />
          {data?.stats && data?.artista_verificat && <StatsCard stats={data.stats} artistaNom={data.artista_verificat.artista.nom} />}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Glass as={Link} to="/comunitat/perfil" className="p-4 block">
            <Kicker color="var(--color-tq-yellow)">comunitat</Kicker>
            <p className="font-semibold text-sm mt-1 text-white">Perfil de comunitat</p>
            <p className="text-xs text-white/60 mt-1">Nom públic, localitat, instruments, visibilitat al directori…</p>
          </Glass>
          <Glass as={Link} to="/comunitat" className="p-4 block">
            <Kicker color="var(--color-tq-yellow)">comunitat</Kicker>
            <p className="font-semibold text-sm mt-1 text-white">Anar a Comunitat</p>
            <p className="text-xs text-white/60 mt-1">Llegir el feed, publicar, explorar el directori.</p>
          </Glass>
        </div>

        {profile.is_staff && (
          <Link to="/staff" className="rd-btn rd-btn--hot" style={{ justifyContent: 'center' }}>Anar al panell staff →</Link>
        )}

        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} style={{ height: 112, borderRadius: 18, background: 'rgba(255,255,255,0.06)' }} />)}
          </div>
        )}
        {error && <Alert tone="danger">{error}</Alert>}

        {!loading && !error && data && (
          <>
            {data.gestio_list.every(u => !u.verificat) && (
              <GuidanceCard title="Tens un artista o grup?" body="Proposa'l per aparèixer al top setmanal i al mapa. Revisem cada proposta a mà." ctaTo="/compte/artista/proposta" ctaLabel="Proposar artista" />
            )}
            {data.perfil && !data.perfil.visible_directori && (
              <GuidanceCard title="Vols que altres músics et trobin?" body="Activa el teu perfil al directori intern i digues si estàs obert a col·laboracions." ctaTo="/comunitat/perfil" ctaLabel="Activar perfil" />
            )}
            {data.perfil && data.perfil.visible_directori && (
              <p className="text-xs text-white/70">✓ El teu perfil és visible al directori. <Link to="/comunitat/perfil" className="text-tq-yellow underline">Editar perfil</Link></p>
            )}

            <section>
              <Crit as="h2" className="rd-cc-h2" style={{ marginBottom: 12 }}>ELS MEUS ARTISTES</Crit>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {data.gestio_list.map(u => (
                  <ArtistaCard key={u.pk} u={u} millorPosicio={data.artista_verificat && data.artista_verificat.pk === u.pk ? data.stats?.millor_posicio : null} />
                ))}
                <AddCard to="/compte/artista/gestio" label="Sol·licitar gestió" />
              </div>
            </section>

            <section>
              <Crit as="h2" className="rd-cc-h2" style={{ marginBottom: 12 }}>LES MEVES PROPOSTES</Crit>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {data.propostes_list.map(p => <PropostaCard key={p.pk} p={p} />)}
                <AddCard to="/compte/artista/proposta" label="Proposar artista" />
              </div>
            </section>
          </>
        )}
      </div>
    </Band>
  )
}
