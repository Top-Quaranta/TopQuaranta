/**
 * StaffSocialPage — /staff/social
 *
 * Distribution cockpit (house kit). Shows:
 *  - The master distribution switch + the six-channel grid (effective
 *    state + last send; links to the per-channel views).
 *  - Instagram config (credentials, phase, story cap, token TTL).
 *  - The week calendar + "Generar totes les slides" dry-run button.
 *
 * The publications list (search, filters, links, lifecycle actions) and
 * the slide gallery moved to /staff/social/publicacions
 * (PublicacionsTable). Mastodon/Bluesky/Telegram have their own views.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import MatriuGrid from './social/MatriuGrid'
import {
  Btn,
  Input,
  PageHeader,
  Pill,
  Select,
  TableCard,
} from '../../components/staff/StaffTable'

// Effective per-channel state from /staff/social/estat-canals/, mapped
// to house Pill tones (semantic, token-driven — no raw palette).
const EFECTIU_PILL = {
  actiu:         { tone: 'green', label: 'Actiu' },
  pausat_global: { tone: 'gray',  label: 'Pausat pel mestre' },
  pausat_canal:  { tone: 'red',   label: 'Pausat (canal)' },
}

// The six channels of the cockpit grid. `field` is the per-channel
// switch on ConfiguracioGlobal; `view` points at the channel's own
// house-style page when it has one (slice 1: the three simple
// channels) — the rest keep an inline toggle until later slices.
const CHANNELS = [
  { key: 'instagram',  label: 'Instagram',  field: 'instagram_actiu',  view: null },
  { key: 'mastodon',   label: 'Mastodon',   field: 'mastodon_actiu',   view: '/staff/social/mastodon' },
  { key: 'bluesky',    label: 'Bluesky',    field: 'bluesky_actiu',    view: '/staff/social/bluesky' },
  { key: 'telegram',   label: 'Telegram',   field: 'telegram_actiu',   view: '/staff/social/telegram' },
  { key: 'newsletter', label: 'Newsletter', field: 'newsletter_actiu', view: '/staff/social/newsletter' },
  { key: 'rss',        label: 'RSS',        field: 'rss_actiu',        view: null },
]

function fmtLastSend(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  return d.toLocaleString('ca', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

export default function StaffSocialPage() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [output, setOutput] = useState('')
  // Credentials form local state — never pre-filled with the existing
  // token (we only ever show first/last 4 chars of what's already saved).
  const [tokenDraft, setTokenDraft] = useState('')
  const [userIdDraft, setUserIdDraft] = useState('')

  // Per-channel honest state (effective state + last send) from the
  // dedicated endpoint, alongside the main social_list payload.
  const [estat, setEstat] = useState(null)
  const reload = () =>
    Promise.all([
      api.get('/staff/social/'),
      api.get('/staff/social/estat-canals/').catch(() => null),
    ])
      .then(([d, e]) => { setData(d); setEstat(e) })
      .catch(() => setData(null))
  useEffect(() => { reload() }, [])

  if (!data) return <p className="p-6">Carregant…</p>
  const { config, credentials, calendari } = data

  const tokenTone =
    config.token_days_left == null  ? 'bg-gray-200 text-gray-700' :
    config.token_days_left <  7      ? 'bg-red-100 text-red-900' :
    config.token_days_left <  21     ? 'bg-yellow-100 text-yellow-900' :
                                       'bg-emerald-100 text-emerald-900'

  // Master distribution switch (distribucio_activa). Gates ALL six
  // channels — the real global pause (replaces the old "Kill switch"
  // that only wrote instagram_actiu).
  async function toggleMaster() {
    const next = !config.distribucio_activa
    if (next === false && !confirm(
      'Pausar TOTA la distribució?\n\nCap canal publicarà (Instagram, ' +
      'Mastodon, Bluesky, Telegram, newsletter, RSS) fins que reactivis ' +
      'el mestre. Els switches per canal es conserven.'
    )) return
    setBusy(true)
    try {
      await api.post('/staff/social/toggle/', { channel: 'global', actiu: next })
      await reload()
    } finally { setBusy(false) }
  }

  async function setFase(n) {
    if (!confirm(`Passar a fase ${n}?`)) return
    await api.post('/staff/social/fase/', { fase: n })
    await reload()
  }

  async function setStoryCap(n) {
    await api.post('/staff/social/story-cap/', { n })
    await reload()
  }

  async function previewAll() {
    setBusy(true)
    setOutput('▶ Generant totes les slides de la setmana (PPCC + territoris + novetats)…')
    try {
      const res = await api.post('/staff/social/preview-all/', {})
      const lines = []
      ;(res.runs || []).forEach(r => {
        lines.push(`$ manage.py ${r.args.join(' ')}`)
        if (!r.ok && r.error) lines.push(`⚠ ${r.error}`)
      })
      lines.push('')
      lines.push(res.output || '(sense sortida)')
      setOutput(lines.join('\n'))
      await reload()
      requestAnimationFrame(() => {
        document.getElementById('social-output')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
    } catch (e) {
      setOutput(`✖ Error: ${e.payload?.error || e.message || e}\n\n${e.payload?.output || ''}`)
    } finally { setBusy(false) }
  }

  async function saveCredentials() {
    if (!tokenDraft.trim()) {
      alert('Enganxa el token.')
      return
    }
    setBusy(true)
    try {
      const res = await api.post('/staff/social/credentials/', {
        access_token: tokenDraft.trim(),
        // Optional override; backend resolves this from the token if empty.
        instagram_user_id: userIdDraft.trim(),
      })
      setTokenDraft(''); setUserIdDraft('')
      await reload()
      alert(
        `Credencials desades. Compte detectat: @${res.resolved_username || '?'} ` +
        `(ID ${res.resolved_user_id}). Comprova-les amb "Provar token".`
      )
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }

  async function testCredentials() {
    setBusy(true); setOutput('')
    try {
      const res = await api.post('/staff/social/credentials/test/')
      setOutput(JSON.stringify(res, null, 2))
    } catch (e) {
      setOutput(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }

  async function clearCredentials() {
    if (!confirm('Esborrar les credencials d\'Instagram desades? Es tornarà a mode DRY-RUN.')) return
    setBusy(true)
    try {
      await api.post('/staff/social/credentials/clear/')
      await reload()
    } finally { setBusy(false) }
  }

  // Mastodon / Bluesky / Telegram credentials now live in their own
  // house-style views (web-react/src/pages/staff/social/ChannelView.jsx
  // + channelDescriptors.jsx) — slice 1 of the distribution-views
  // redistribution. This cockpit keeps only the master switch, the
  // six-channel grid and the channels not yet migrated (Instagram,
  // newsletter, RSS).

  // ── Channel toggles (instagram / newsletter / rss; the migrated
  // channels toggle from their own view) ──
  async function toggleChannel(channel) {
    setBusy(true)
    try {
      await api.post('/staff/social/toggle/', { channel })
      await reload()
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }

  // Per-publication lifecycle actions (preview / publicar / reset /
  // re-publicar / eliminar-remot) + the slides gallery now live on the
  // unified publications table (pages/staff/social/PublicacionsTable.jsx
  // → /staff/social/publicacions). This cockpit keeps the master switch,
  // the channel grid, the Instagram config + the week calendar (whose
  // "Generar totes les slides" button renders the week in dry-run).

  return (
    <section className="space-y-6">
      <PageHeader
        title="Distribució"
        subtitle={`Control del calendari setmanal · mode ${
          config.dry_run ? 'DRY-RUN' : 'PRODUCCIÓ'
        }`}
        right={
          <Pill tone={config.dry_run ? 'gray' : 'green'}>
            {config.dry_run ? 'DRY-RUN' : 'Producció'}
          </Pill>
        }
      />

      {/* ── Master distribution switch (kit) ──────────────────── */}
      <TableCard className="p-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <p className="text-[11px] uppercase tracking-widest text-tq-ink/75">
              Interruptor mestre de distribució
            </p>
            <p className="text-sm mt-1 font-semibold flex items-center gap-2 flex-wrap">
              <Pill tone={config.distribucio_activa ? 'green' : 'red'}>
                {config.distribucio_activa ? 'Activa' : 'Pausada'}
              </Pill>
              {config.distribucio_activa
                ? 'cada canal segueix el seu propi switch'
                : 'cap canal publica (els sis)'}
            </p>
          </div>
          <Btn
            tone={config.distribucio_activa ? 'danger' : 'primary'}
            size="md"
            disabled={busy}
            onClick={toggleMaster}
          >
            {config.distribucio_activa ? 'Pausar-ho tot' : 'Reactivar distribució'}
          </Btn>
        </div>
        <p className="text-xs mt-3">
          <Link
            to="/staff/social/newsletter"
            className="underline decoration-dotted hover:decoration-solid"
          >
            Newsletter (esborrany + generació) →
          </Link>
        </p>
      </TableCard>

      {/* ── Channel grid (kit) ────────────────────────────────── */}
      <div>
        <h2 className="text-base font-bold text-white font-display mb-1">Canals</h2>
        <p className="text-sm text-white/70 mb-3">
          Els sis canals com a iguals. El mestre de dalt els gateja tots; cada canal
          té a més el seu propi switch. Mastodon, Bluesky i Telegram tenen vista
          pròpia; Instagram, newsletter i RSS es gestionen encara aquí sota.
        </p>
        <TableCard className="p-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {CHANNELS.map((c) => {
              const st = estat?.canals?.[c.key]
              const efectiu = st?.efectiu || (config[c.field] ? 'actiu' : 'pausat_canal')
              const ef = EFECTIU_PILL[efectiu] || { tone: 'gray', label: efectiu }
              const actiu = !!config[c.field]
              return (
                <div
                  key={c.key}
                  className="p-3 border border-tq-ink/10 rounded-md flex items-start justify-between gap-2"
                >
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-widest text-tq-ink/75">
                      {c.label}
                    </p>
                    <div className="mt-1">
                      <Pill tone={ef.tone}>{ef.label}</Pill>
                    </div>
                    {c.key === 'instagram' && st?.fase_distribucio != null && (
                      <p className="text-[10px] text-tq-ink/75 mt-1">
                        Fase {st.fase_distribucio}/5
                      </p>
                    )}
                    {c.key !== 'rss' && (
                      <p className="text-[10px] text-tq-ink/75 mt-1">
                        Últim: {fmtLastSend(st?.ultim_enviament)}
                        {st?.font === 'audit' && ' (audit)'}
                      </p>
                    )}
                  </div>
                  <div className="shrink-0">
                    {c.view ? (
                      <Btn tone="secondary" onClick={() => navigate(c.view)}>
                        Gestiona →
                      </Btn>
                    ) : (
                      <Btn
                        tone={actiu ? 'danger' : 'primary'}
                        disabled={busy}
                        onClick={() => toggleChannel(c.key)}
                        title={actiu ? 'Pausar aquest canal' : 'Activar aquest canal'}
                      >
                        {actiu ? 'Pausar' : 'Activar'}
                      </Btn>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </TableCard>
      </div>

      {/* ── Legacy controls (not yet migrated: Instagram config,
          calendar, publications list). Wrapped in an explicit white
          surface so the `text-tq-ink` inside reads on the dark body —
          slices 2-4 move these out into their own house-style views. */}
      <div className="bg-white text-tq-ink rounded-lg shadow-md p-4 md:p-6 space-y-6">

      {/* ── Credentials card ──────────────────────────────────── */}
      <div className={
        'rounded-md p-4 border ' +
        (credentials.configured
          ? 'border-emerald-300 bg-emerald-50'
          : 'border-yellow-300 bg-yellow-50')
      }>
        <p className="text-[10px] uppercase tracking-widest text-tq-ink/75 mb-1">
          Credencials Instagram
        </p>
        {credentials.configured ? (
          <>
            <p className="text-sm">
              <strong>Configurades</strong> · Token{' '}
              <code className="bg-white px-1.5 py-0.5 rounded">
                {credentials.token_masked}
              </code>{' '}
              · IG user ID <code className="bg-white px-1.5 py-0.5 rounded">
                {credentials.instagram_user_id}
              </code>
              {' '}· Origen <code>{credentials.source}</code>
              {credentials.expires_at && <> · Caduca {credentials.expires_at.slice(0, 10)}</>}
              {credentials.updated_by && <> · Desat per <strong>{credentials.updated_by}</strong></>}
            </p>
            <div className="flex gap-2 mt-3">
              <button
                type="button"
                onClick={testCredentials}
                disabled={busy}
                className="px-3 py-1.5 bg-tq-ink text-tq-yellow rounded text-xs font-semibold hover:bg-tq-ink/90"
              >
                Provar token (read-only)
              </button>
              <button
                type="button"
                onClick={clearCredentials}
                disabled={busy}
                className="px-3 py-1.5 bg-red-700 text-white rounded text-xs font-semibold hover:bg-red-800"
              >
                Esborrar credencials
              </button>
            </div>
          </>
        ) : (
          <p className="text-sm">
            <strong>Sense credencials.</strong> Genera un token al
            developers.facebook.com (Instagram → API setup → Generate token)
            i enganxa'l aquí sota.
          </p>
        )}

        {/* Form to set / replace credentials */}
        <details className="mt-3">
          <summary className="text-xs cursor-pointer font-semibold text-tq-ink/70">
            {credentials.configured ? 'Substituir credencials…' : 'Afegir credencials…'}
          </summary>
          <div className="mt-2 space-y-2">
            <label className="block text-xs">
              <span className="block mb-1 font-semibold">Long-lived access token</span>
              <input
                type="password"
                autoComplete="off"
                value={tokenDraft}
                onChange={e => setTokenDraft(e.target.value)}
                placeholder="IGAA..."
                className="w-full px-2 py-1 border border-gray-300 rounded text-xs font-mono"
              />
              <span className="block text-[10px] text-tq-ink/75 mt-1">
                El token es genera a developers.facebook.com →
                Instagram → API setup → Generate token.
              </span>
            </label>
            <details className="text-xs">
              <summary className="cursor-pointer text-tq-ink/70">
                Override manual del Instagram user ID (rar; només si la
                detecció automàtica no funciona)
              </summary>
              <input
                type="text"
                value={userIdDraft}
                onChange={e => setUserIdDraft(e.target.value)}
                placeholder="178…"
                className="mt-1 w-full px-2 py-1 border border-gray-300 rounded text-xs font-mono"
              />
            </details>
          </div>
          <button
            type="button"
            onClick={saveCredentials}
            disabled={busy || !tokenDraft}
            className="mt-2 px-3 py-1.5 bg-tq-yellow text-tq-ink rounded text-xs font-semibold hover:bg-tq-yellow-deep hover:text-white disabled:opacity-50"
          >
            Desar
          </button>
          <p className="text-[10px] text-tq-ink/75 mt-1">
            En desar, el backend confirma el token amb una crida a la
            Graph API i extreu el teu Instagram user ID
            automàticament. El token només es desa al servidor (fila
            singleton <code>InstagramAuth</code>); mai no es mostra
            sencer després.
          </p>
        </details>
      </div>

      {/* ── Config controls ───────────────────────────────────── */}
      <div className="grid sm:grid-cols-2 gap-3">
        <div className="p-3 border rounded-md">
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/75">Fase distribució (només Instagram)</p>
          <div className="flex gap-1 mt-2">
            {[1, 2, 3, 4, 5].map(n => (
              <button
                key={n}
                type="button"
                disabled={busy}
                onClick={() => setFase(n)}
                className={
                  'px-3 py-1 rounded text-sm font-semibold ' +
                  (config.fase_distribucio === n
                    ? 'bg-tq-yellow text-tq-ink'
                    : 'bg-gray-100 text-tq-ink hover:bg-gray-200')
                }
              >
                {n}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-tq-ink/75 mt-1">
            1=dissabte · 2=+dimecres · 3=+dilluns · 4=+divendres · 5=+dimarts
          </p>
        </div>

        <div className="p-3 border rounded-md">
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/75">Token Instagram</p>
          <span className={'inline-block mt-2 px-2 py-0.5 rounded text-xs font-semibold ' + tokenTone}>
            {config.token_days_left == null ? 'No configurat' :
             `${config.token_days_left} dies fins caducar`}
          </span>
        </div>
      </div>

      <div className="p-3 border rounded-md max-w-md">
        <p className="text-[10px] uppercase tracking-widest text-tq-ink/75 mb-1">
          Story cap Global (cançons)
        </p>
        <Select aria-label="Story cap Global (cançons)" value={config.story_max_cancons_ppcc}
          onChange={e => setStoryCap(parseInt(e.target.value, 10))}
        >
          {[5, 10, 15, 20, 30, 40].map(n => <option key={n} value={n}>{n} stories</option>)}
        </Select>
        <p className="text-[10px] text-tq-ink/75 mt-1">
          Si la story completion rate cau per sota del 25 % al story #N,
          baixa aquí a N.
        </p>
      </div>

      {/* Channels not yet migrated to their own view (Mastodon,
          Bluesky and Telegram now live under /staff/social/<canal> via
          the channel grid above). */}
      <p className="text-[11px] text-tq-ink/75">
        La <strong>newsletter</strong> usa l'SMTP configurat a <code>EMAIL_HOST</code>;
        envia cada diumenge als usuaris amb <code>vol_newsletter=True</code> (revisa
        l'<Link to="/staff/social/esborrany" className="underline">esborrany</Link> abans).
        L'<strong>RSS</strong> es serveix a <code>/rss/top.xml</code> +{' '}
        <code>/rss/novetats.xml</code> sense altres credencials. Mastodon, Bluesky i
        Telegram tenen ara la seva pròpia vista (graella de dalt).
      </p>

      {/* ── Matriu de distribució (canal × tipus) ─────────────── */}
      <MatriuGrid />

      {/* ── Calendari de la setmana ───────────────────────────── */}
      <section>
        <h2 className="text-base font-bold font-display mb-2">
          Calendari d'aquesta setmana
        </h2>
        <p className="text-xs text-tq-ink/75 mb-2">
          El cron entra cada dia, però només publica si la fase actual
          inclou aquell slot. La rotació territorial està resolta — així
          ja saps quin top toca abans de prémer res.
        </p>
        <div className="mb-3">
          <button
            type="button"
            disabled={busy}
            onClick={previewAll}
            className="px-3 py-1.5 rounded bg-tq-ink text-tq-yellow text-xs font-bold hover:bg-tq-ink/90 disabled:opacity-50"
          >
            Generar totes les slides de la setmana (dry-run)
          </button>
          <span className="text-[11px] text-tq-ink/75 ml-2">
            Renderitza tots els slots (PPCC + territoris + novetats) sense publicar.
            Després pots veure'ls amb "Veure slides" a la taula de baix.
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="text-xs min-w-[560px] w-full border-collapse">
            <thead>
              <tr className="text-left text-tq-ink/70">
                <th className="py-1 pr-3">Dia</th>
                <th className="py-1 pr-3">Plataforma</th>
                <th className="py-1 pr-3">Tipus</th>
                <th className="py-1 pr-3">Territori</th>
                <th className="py-1 pr-3">Fase mín.</th>
                <th className="py-1">Estat</th>
              </tr>
            </thead>
            <tbody>
              {(calendari || []).map(s => {
                const inFase = config.fase_distribucio >= s.min_fase
                return (
                  <tr key={`${s.platform}-${s.tipus}-${s.weekday}`}
                      className={inFase ? '' : 'opacity-80'}>
                    <td className="py-1 pr-3" title={s.publication_date}>
                      <strong>{s.weekday_name}</strong>{' '}
                      <span className="text-tq-ink/75">
                        · setm. {s.project_week}
                      </span>
                    </td>
                    <td className="py-1 pr-3">{s.platform.replace('instagram_', '')}</td>
                    <td className="py-1 pr-3">{s.tipus}</td>
                    <td className="py-1 pr-3">{s.territori_label}</td>
                    <td className="py-1 pr-3">{s.min_fase}</td>
                    <td className="py-1">
                      {inFase
                        ? <span className="text-emerald-700 font-semibold">actiu</span>
                        : <span className="text-tq-ink/70">cal fase ≥ {s.min_fase}</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── Insights externs ─────────────────────────────────── */}
      <div className="p-3 border border-tq-ink/15 rounded-md bg-gray-50 text-xs">
        <p className="font-semibold mb-1">Insights — on mirar les mètriques</p>
        <p className="text-tq-ink/70">
          Les estadístiques (reach, completion rate, follower growth,
          engagement) no apareixen aquí encara — les mira al{' '}
          <a
            href="https://business.facebook.com/latest/insights/overview"
            target="_blank" rel="noopener"
            className="underline hover:text-tq-yellow-deep"
          >
            Meta Business Suite Insights
          </a>{' '}
          o a la mateixa app d'Instagram (Profile → Insights).
        </p>
        <p className="text-tq-ink/75 mt-1">
          Sprint K integrarà el subset rellevant directament al panell
          (Insights API + comptadors interns ètics). De moment, mira
          cada dilluns: si en 4 setmanes consecutives la fase actual
          aguanta els llindars de reach i engagement, puja a la fase
          següent.
        </p>
      </div>

      {/* ── Captured stdout ──────────────────────────────────── */}
      {output && (
        <pre
          id="social-output"
          className="bg-tq-ink text-tq-yellow text-xs p-3 rounded overflow-x-auto whitespace-pre-wrap"
        >
          {output}
        </pre>
      )}

      {/* ── Posts list (moved) ───────────────────────────────── */}
      <p className="text-sm text-tq-ink/75">
        La llista de publicacions (amb cerca, filtres, enllaços i accions de
        cicle de vida) viu ara a{' '}
        <Link to="/staff/social/publicacions" className="underline font-semibold">
          Publicacions
        </Link>
        .
      </p>
      </div>
    </section>
  )
}
