/**
 * StaffSocialPage — /staff/social
 *
 * Operations cockpit for the Instagram distribution. Shows:
 *  - The active phase + kill switch + token TTL.
 *  - The list of recent SocialPost rows with status badges.
 *  - A preview button per slot that triggers `publicar_social
 *    --dry-run` server-side and prints the captured stdout.
 *  - A "Publicar ara" button that re-publishes with --force.
 *
 * No fancy chrome — staff tool, not public-facing. Lists collapse
 * to scroll on mobile via the Table wrapper.
 */
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { Table, Select } from '../../components/staff/StaffTable'

const STATUS_TONE = {
  pendent:  'bg-yellow-100 text-yellow-900',
  publicat: 'bg-emerald-100 text-emerald-900',
  error:    'bg-red-100 text-red-900',
  omes:     'bg-gray-200 text-gray-800',
}

function StatusBadge({ status }) {
  return (
    <span className={
      'inline-block text-[10px] uppercase tracking-wide font-semibold px-2 py-0.5 rounded-full ' +
      (STATUS_TONE[status] || 'bg-gray-200 text-gray-800')
    }>
      {status}
    </span>
  )
}

export default function StaffSocialPage() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [output, setOutput] = useState('')
  // Credentials form local state — never pre-filled with the existing
  // token (we only ever show first/last 4 chars of what's already saved).
  const [tokenDraft, setTokenDraft] = useState('')
  const [userIdDraft, setUserIdDraft] = useState('')

  const reload = () => api.get('/staff/social/').then(setData).catch(() => setData(null))
  useEffect(() => { reload() }, [])

  if (!data) return <p className="p-6">Carregant…</p>
  const { config, results, credentials, calendari } = data

  const tokenTone =
    config.token_days_left == null  ? 'bg-gray-200 text-gray-700' :
    config.token_days_left <  7      ? 'bg-red-100 text-red-900' :
    config.token_days_left <  21     ? 'bg-yellow-100 text-yellow-900' :
                                       'bg-emerald-100 text-emerald-900'

  async function toggle() {
    setBusy(true)
    try {
      await api.post('/staff/social/toggle/', { actiu: !config.instagram_actiu })
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

  async function preview(post) {
    setBusy(true); setOutput('')
    try {
      const res = await api.post('/staff/social/preview/', {
        data: post.setmana, tipus: post.tipus, platform: post.platform,
      })
      setOutput(res.output || '(sense sortida)')
    } catch (e) {
      setOutput(`Error: ${e.message || e}`)
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

  async function publicarAra(post) {
    if (!confirm(`Publicar ara: ${post.platform} · ${post.tipus} · ${post.territori || '—'} · ${post.setmana}?`)) return
    setBusy(true); setOutput('')
    try {
      const res = await api.post('/staff/social/publicar-ara/', {
        data: post.setmana, tipus: post.tipus, platform: post.platform,
      })
      setOutput(res.output || '(sense sortida)')
      await reload()
    } catch (e) {
      setOutput(`Error: ${e.message || e}`)
    } finally { setBusy(false) }
  }

  return (
    // The body of the SPA is `bg-tq-ink` (dark). Wrap the whole
    // staff page in an explicit white surface so all the
    // `text-tq-ink` inside reads correctly. Same pattern other
    // staff pages get implicitly via their tables.
    <section className="bg-white text-tq-ink rounded-lg shadow-md p-4 md:p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold font-display">Distribució — Instagram</h1>
        <p className="text-sm text-tq-ink/60 mt-1">
          Control del calendari setmanal. Cada slot publica via Graph
          API. Mode <strong>{config.dry_run ? 'DRY-RUN' : 'PRODUCCIÓ'}</strong>
          {' '} (les credencials viuen a la fila singleton{' '}
          <code>InstagramAuth</code>; sense token, mode DRY-RUN automàtic).
        </p>
      </header>

      {/* ── Credentials card ──────────────────────────────────── */}
      <div className={
        'rounded-md p-4 border ' +
        (credentials.configured
          ? 'border-emerald-300 bg-emerald-50'
          : 'border-yellow-300 bg-yellow-50')
      }>
        <p className="text-[10px] uppercase tracking-widest text-tq-ink/60 mb-1">
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
                className="px-3 py-1.5 bg-red-600 text-white rounded text-xs font-semibold hover:bg-red-700"
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
              <span className="block text-[10px] text-tq-ink/60 mt-1">
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
          <p className="text-[10px] text-tq-ink/60 mt-1">
            En desar, el backend confirma el token amb una crida a la
            Graph API i extreu el teu Instagram user ID
            automàticament. El token només es desa al servidor (fila
            singleton <code>InstagramAuth</code>); mai no es mostra
            sencer després.
          </p>
        </details>
      </div>

      {/* ── Config controls ───────────────────────────────────── */}
      <div className="grid sm:grid-cols-3 gap-3">
        <div className="p-3 border rounded-md">
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/60">Kill switch</p>
          <button
            type="button"
            onClick={toggle}
            disabled={busy}
            className={
              'mt-2 px-3 py-1.5 rounded-md text-sm font-semibold ' +
              (config.instagram_actiu
                ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                : 'bg-red-600 text-white hover:bg-red-700')
            }
          >
            {config.instagram_actiu ? 'ACTIU — clica per pausar' : 'PAUSAT — clica per activar'}
          </button>
        </div>

        <div className="p-3 border rounded-md">
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/60">Fase distribució</p>
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
          <p className="text-[10px] text-tq-ink/60 mt-1">
            1=dissabte · 2=+dimecres · 3=+dilluns · 4=+divendres · 5=+dimarts
          </p>
        </div>

        <div className="p-3 border rounded-md">
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/60">Token Instagram</p>
          <span className={'inline-block mt-2 px-2 py-0.5 rounded text-xs font-semibold ' + tokenTone}>
            {config.token_days_left == null ? 'No configurat' :
             `${config.token_days_left} dies fins caducar`}
          </span>
        </div>
      </div>

      <div className="p-3 border rounded-md max-w-md">
        <p className="text-[10px] uppercase tracking-widest text-tq-ink/60 mb-1">
          Story cap Global (cançons)
        </p>
        <Select
          value={config.story_max_cancons_ppcc}
          onChange={e => setStoryCap(parseInt(e.target.value, 10))}
        >
          {[5, 10, 15, 20, 30, 40].map(n => <option key={n} value={n}>{n} stories</option>)}
        </Select>
        <p className="text-[10px] text-tq-ink/60 mt-1">
          Si la story completion rate cau per sota del 25 % al story #N,
          baixa aquí a N.
        </p>
      </div>

      {/* ── Calendari de la setmana ───────────────────────────── */}
      <section>
        <h2 className="text-base font-bold font-display mb-2">
          Calendari d'aquesta setmana
        </h2>
        <p className="text-xs text-tq-ink/60 mb-2">
          El cron entra cada dia, però només publica si la fase actual
          inclou aquell slot. La rotació territorial està resolta — així
          ja saps quin top toca abans de prémer res.
        </p>
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
                      className={inFase ? '' : 'opacity-60'}>
                    <td className="py-1 pr-3">
                      <strong>{s.weekday_name}</strong>{' '}
                      <span className="text-tq-ink/60">
                        {s.publication_date.slice(5)}
                      </span>
                    </td>
                    <td className="py-1 pr-3">{s.platform.replace('instagram_', '')}</td>
                    <td className="py-1 pr-3">{s.tipus}</td>
                    <td className="py-1 pr-3">{s.territori_label}</td>
                    <td className="py-1 pr-3">{s.min_fase}</td>
                    <td className="py-1">
                      {inFase
                        ? <span className="text-emerald-700 font-semibold">actiu</span>
                        : <span className="text-tq-ink/50">cal fase ≥ {s.min_fase}</span>}
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
        <p className="text-tq-ink/60 mt-1">
          Sprint K integrarà el subset rellevant directament al panell
          (Insights API + comptadors interns ètics). De moment, mira
          cada dilluns: si en 4 setmanes consecutives la fase actual
          aguanta els llindars de reach i engagement, puja a la fase
          següent.
        </p>
      </div>

      {/* ── Captured stdout ──────────────────────────────────── */}
      {output && (
        <pre className="bg-tq-ink text-tq-yellow text-xs p-3 rounded overflow-x-auto whitespace-pre-wrap">{output}</pre>
      )}

      {/* ── Posts list ───────────────────────────────────────── */}
      <Table>
        <thead>
          <tr>
            <th className="text-left">Setmana del</th>
            <th className="text-left">Plataforma</th>
            <th className="text-left">Tipus</th>
            <th className="text-left">Territori</th>
            <th className="text-left">Estat</th>
            <th className="text-left">Publicat</th>
            <th className="text-left">Accions</th>
          </tr>
        </thead>
        <tbody>
          {results.map(p => (
            <tr key={p.pk}>
              {/* publication_date is the calendar date the slot
                  publishes on (Saturday for top global, Wednesday
                  for territorial, etc.) — way more meaningful than
                  the internal Monday-of-ISO-week. */}
              <td>{p.publication_date}</td>
              <td className="text-xs">{p.platform.replace('instagram_', '')}</td>
              <td className="text-xs">{p.tipus}</td>
              <td>{p.territori_label}</td>
              <td><StatusBadge status={p.status} /></td>
              <td className="text-xs">{p.published_at ? p.published_at.slice(0, 16).replace('T', ' ') : '—'}</td>
              <td>
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => preview(p)}
                    disabled={busy}
                    className="text-xs px-2 py-1 rounded bg-gray-100 hover:bg-gray-200"
                  >
                    Preview
                  </button>
                  <button
                    type="button"
                    onClick={() => publicarAra(p)}
                    disabled={busy}
                    className="text-xs px-2 py-1 rounded bg-tq-ink text-tq-yellow font-semibold hover:bg-tq-ink/90"
                  >
                    Publicar
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>

      {results.length === 0 && (
        <p className="text-sm text-tq-ink/60 italic">
          Encara no hi ha cap publicació. Utilitza Preview per generar-ne en mode dry-run.
        </p>
      )}
    </section>
  )
}
