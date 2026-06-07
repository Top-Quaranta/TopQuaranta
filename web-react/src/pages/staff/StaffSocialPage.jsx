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
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { Table, Select, Input } from '../../components/staff/StaffTable'

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

// Effective per-channel state from /staff/social/estat-canals/.
const EFECTIU_TONE = {
  actiu:         'bg-emerald-100 text-emerald-900',
  pausat_global: 'bg-gray-300 text-gray-800',
  pausat_canal:  'bg-red-100 text-red-900',
}
const EFECTIU_LABEL = {
  actiu:         'Actiu',
  pausat_global: 'Pausat pel mestre',
  pausat_canal:  'Pausat (canal)',
}

function fmtLastSend(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  return d.toLocaleString('ca', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

export default function StaffSocialPage() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [output, setOutput] = useState('')
  // Credentials form local state — never pre-filled with the existing
  // token (we only ever show first/last 4 chars of what's already saved).
  const [tokenDraft, setTokenDraft] = useState('')
  const [userIdDraft, setUserIdDraft] = useState('')
  // Mastodon + Bluesky form drafts — same shape as the IG one
  // (never pre-filled with the existing secret).
  const [mstInstance, setMstInstance] = useState('')
  const [mstToken, setMstToken] = useState('')
  const [mstHandle, setMstHandle] = useState('')
  const [bskyHandle, setBskyHandle] = useState('')
  const [bskyPwd, setBskyPwd] = useState('')
  const [tgToken, setTgToken] = useState('')
  const [tgChatId, setTgChatId] = useState('')
  // pk → {feed:[…], stories:[…]} of rendered slide thumbnails. Populated
  // when the operator clicks "Veure slides" on a row.
  const [slidesByPk, setSlidesByPk] = useState({})

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
  const { config, results, credentials, calendari } = data
  const mastodon = data.mastodon || { configured: false }
  const bluesky = data.bluesky || { configured: false }
  const telegram = data.telegram || { configured: false }

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

  async function loadSlides(post) {
    setBusy(true)
    try {
      // `platform` scopes the response so a feed row only shows
      // feed PNGs and a story row only shows stories — without it
      // the gallery mixed both because they share tipus/setmana.
      const params = new URLSearchParams({
        tipus: post.tipus,
        territori: post.territori || 'general',
        setmana: post.setmana,
        platform: post.platform,
      })
      const res = await api.get(`/staff/social/slides/?${params}`)
      setSlidesByPk(prev => ({ ...prev, [post.pk]: res }))
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
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

  async function preview(post) {
    setBusy(true)
    setOutput('▶ Executant preview… (genera els PNGs però no publica)')
    try {
      const res = await api.post('/staff/social/preview/', {
        data: post.setmana, tipus: post.tipus, platform: post.platform,
      })
      const lines = []
      if (res.args) lines.push(`$ manage.py ${res.args.join(' ')}`)
      lines.push(res.output || '(sense sortida)')
      if (res.error) lines.push(`\n⚠ ${res.error}`)
      setOutput(lines.join('\n'))
      // Scroll the output into view in case the click happens far down.
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

  // ── Mastodon ──────────────────────────────────────────────────
  async function saveMastodon() {
    if (!mstInstance.trim() || !mstToken.trim()) {
      alert('Cal instance_url + access_token.')
      return
    }
    setBusy(true)
    try {
      await api.post('/staff/social/mastodon/', {
        instance_url: mstInstance.trim(),
        access_token: mstToken.trim(),
        handle: mstHandle.trim(),
      })
      setMstInstance(''); setMstToken(''); setMstHandle('')
      await reload()
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }
  async function testMastodon() {
    setBusy(true); setOutput('')
    try {
      const res = await api.post('/staff/social/mastodon/test/')
      setOutput(JSON.stringify(res, null, 2))
    } catch (e) {
      setOutput(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }
  async function clearMastodon() {
    if (!confirm('Esborrar credencials Mastodon? El cron passarà a mode DRY-RUN per a aquest canal.')) return
    setBusy(true)
    try {
      await api.post('/staff/social/mastodon/clear/')
      await reload()
    } finally { setBusy(false) }
  }

  // ── Bluesky ───────────────────────────────────────────────────
  async function saveBluesky() {
    if (!bskyHandle.trim() || !bskyPwd.trim()) {
      alert('Cal handle + app_password.')
      return
    }
    setBusy(true)
    try {
      await api.post('/staff/social/bluesky/', {
        handle: bskyHandle.trim(),
        app_password: bskyPwd.trim(),
      })
      setBskyHandle(''); setBskyPwd('')
      await reload()
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }
  async function testBluesky() {
    setBusy(true); setOutput('')
    try {
      const res = await api.post('/staff/social/bluesky/test/')
      setOutput(JSON.stringify(res, null, 2))
    } catch (e) {
      setOutput(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }
  async function clearBluesky() {
    if (!confirm('Esborrar credencials Bluesky? El cron passarà a mode DRY-RUN per a aquest canal.')) return
    setBusy(true)
    try {
      await api.post('/staff/social/bluesky/clear/')
      await reload()
    } finally { setBusy(false) }
  }

  // ── Telegram ──────────────────────────────────────────────────
  async function saveTelegram() {
    if (!tgToken.trim() || !tgChatId.trim()) {
      alert('Cal bot_token + chat_id.')
      return
    }
    setBusy(true)
    try {
      await api.post('/staff/social/telegram/', {
        bot_token: tgToken.trim(),
        chat_id: tgChatId.trim(),
      })
      setTgToken(''); setTgChatId('')
      await reload()
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }
  async function testTelegram() {
    setBusy(true); setOutput('')
    try {
      const res = await api.post('/staff/social/telegram/test/')
      setOutput(JSON.stringify(res, null, 2))
    } catch (e) {
      setOutput(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }
  async function clearTelegram() {
    if (!confirm('Esborrar credencials Telegram? El cron passarà a mode DRY-RUN per a aquest canal.')) return
    setBusy(true)
    try {
      await api.post('/staff/social/telegram/clear/')
      await reload()
    } finally { setBusy(false) }
  }

  // ── Channel toggles (mastodon / bluesky / telegram / newsletter / rss) ──
  async function toggleChannel(channel) {
    setBusy(true)
    try {
      await api.post('/staff/social/toggle/', { channel })
      await reload()
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }

  async function resetPost(post) {
    if (!confirm(
      `Reset estat: ${post.platform} · ${post.tipus} · ${post.territori_label || '—'}?\n\n` +
      `Marca la fila com "pendent" i esborra el media_id local. ` +
      `NO toca la publicació a Instagram. Útil per a reintentar el procés des de zero.`
    )) return
    setBusy(true); setOutput('▶ Reset estat…')
    try {
      const res = await api.post('/staff/social/reset/', { pk: post.pk })
      setOutput(`✓ Reset: status era ${res.previous?.status}, media_id era "${res.previous?.instagram_media_id || '(buit)'}"`)
      await reload()
    } catch (e) {
      setOutput(`✖ Error: ${e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }

  async function eliminarRemot(post) {
    if (!post.instagram_media_id) {
      alert('Aquest post no té id remota (mai s\'ha publicat o ja s\'ha resetejat).')
      return
    }
    const platLabel = post.platform.replace('instagram_', 'IG ')
    if (!confirm(
      `ESBORRAR DE ${platLabel.toUpperCase()}: ${post.tipus} · ${post.territori_label || '—'}\n` +
      `id remota: ${post.instagram_media_id}\n\n` +
      `Això elimina la publicació remota i deixa la fila llesta per re-publicar. ` +
      `És DESTRUCTIU. Confirmes?`
    )) return
    setBusy(true); setOutput(`▶ Esborrant publicació de ${platLabel}…`)
    try {
      // Single backend endpoint that dispatches by platform.
      const res = await api.post('/staff/social/eliminar-remot/', { pk: post.pk })
      setOutput(`${res.ok ? '✓' : '✖'} ${res.msg || ''}`)
      await reload()
    } catch (e) {
      setOutput(`✖ Error: ${e.payload?.error || e.message}\n\n${e.payload?.msg || ''}`)
    } finally { setBusy(false) }
  }

  async function publicarAra(post) {
    if (!confirm(`Publicar ara: ${post.platform} · ${post.tipus} · ${post.territori_label || '—'} · setmana del ${post.publication_date}?`)) return
    setBusy(true)
    setOutput('▶ Publicant… (això sí truca l\'API d\'Instagram si hi ha token vàlid)')
    try {
      const res = await api.post('/staff/social/publicar-ara/', {
        data: post.setmana, tipus: post.tipus, platform: post.platform,
      })
      const lines = []
      if (res.args) lines.push(`$ manage.py ${res.args.join(' ')}`)
      lines.push(res.output || '(sense sortida)')
      if (res.error) lines.push(`\n⚠ ${res.error}`)
      setOutput(lines.join('\n'))
      requestAnimationFrame(() => {
        document.getElementById('social-output')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
      await reload()
    } catch (e) {
      setOutput(`✖ Error: ${e.payload?.error || e.message || e}\n\n${e.payload?.output || ''}`)
    } finally { setBusy(false) }
  }

  async function republicar(post) {
    // Lot C — Sprint Distribució v2: one-click delete-remote +
    // re-render + re-publish. Use case: a cançó from a published top
    // is rejected after publication, the renderer now produces a
    // corrected slide, but the live post still shows the wrong row.
    // Manual workflow before this was Esborrar → Reset → Publicar
    // (3 clicks across 3 endpoints).
    const platLabel = post.platform.replace('instagram_', 'IG ')
    if (!confirm(
      `RE-PUBLICAR ${platLabel.toUpperCase()}: ${post.tipus} · ${post.territori_label || '—'}\n\n` +
      `Això esborra la publicació remota actual (${post.instagram_media_id}) i en publica una de nova ` +
      `amb el contingut actualitzat. És DESTRUCTIU.\n\n` +
      `Confirmes?`
    )) return
    setBusy(true)
    setOutput(`▶ Re-publicant ${platLabel}: esborrant remot + re-publicant…`)
    try {
      const res = await api.post('/staff/social/republicar/', { pk: post.pk })
      const lines = []
      lines.push(`✓ ${res.delete_msg || 'remot esborrat'}`)
      if (res.args) lines.push(`$ manage.py ${res.args.join(' ')}`)
      lines.push(res.publish_output || '(sense sortida)')
      setOutput(lines.join('\n'))
      requestAnimationFrame(() => {
        document.getElementById('social-output')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
      await reload()
    } catch (e) {
      const stepMsg = e.payload?.step ? ` (fallat al pas: ${e.payload.step})` : ''
      setOutput(`✖ Error${stepMsg}: ${e.payload?.msg || e.payload?.error || e.message}`)
    } finally { setBusy(false) }
  }

  return (
    // The body of the SPA is `bg-tq-ink` (dark). Wrap the whole
    // staff page in an explicit white surface so all the
    // `text-tq-ink` inside reads correctly. Same pattern other
    // staff pages get implicitly via their tables.
    <section className="bg-white text-tq-ink rounded-lg shadow-md p-4 md:p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold font-display">Distribució multi-canal</h1>
        <p className="text-sm text-tq-ink/75 mt-1">
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

      {/* ── Master distribution switch ────────────────────────── */}
      <div className={
        'p-4 rounded-md border-2 ' +
        (config.distribucio_activa
          ? 'border-emerald-300 bg-emerald-50'
          : 'border-red-400 bg-red-50')
      }>
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <p className="text-[11px] uppercase tracking-widest text-tq-ink/75">
              Interruptor mestre de distribució
            </p>
            <p className="text-sm mt-1 font-semibold">
              {config.distribucio_activa
                ? 'Distribució ACTIVA — cada canal segueix el seu propi switch'
                : 'Distribució PAUSADA — cap canal publica (els sis)'}
            </p>
          </div>
          <button
            type="button"
            onClick={toggleMaster}
            disabled={busy}
            className={
              'px-4 py-2 rounded-md text-sm font-semibold ' +
              (config.distribucio_activa
                ? 'bg-red-700 text-white hover:bg-red-800'
                : 'bg-emerald-700 text-white hover:bg-emerald-800')
            }
          >
            {config.distribucio_activa ? 'Pausar-ho tot' : 'Reactivar distribució'}
          </button>
        </div>
        <p className="text-xs mt-2">
          <Link to="/staff/social/esborrany" className="underline decoration-dotted hover:decoration-solid">
            Esborrany de la newsletter (revisió) →
          </Link>
        </p>
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

      {/* ── Canals de distribució ─────────────────────────────── */}
      <section>
        <h2 className="text-base font-bold font-display mb-2">
          Canals de distribució
        </h2>
        <p className="text-xs text-tq-ink/75 mb-3">
          Els sis canals com a iguals. El mestre de dalt els gateja tots;
          cada canal té a més el seu propi switch independent. Amb el
          mestre pausat, tots mostren «Pausat pel mestre» encara que el
          seu switch propi estigui actiu. Sense credencials, el cron salta
          aquell canal en silenci.
        </p>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
          {[
            { key: 'instagram', label: 'Instagram', val: config.instagram_actiu },
            { key: 'mastodon',  label: 'Mastodon',  val: config.mastodon_actiu },
            { key: 'bluesky',   label: 'Bluesky',   val: config.bluesky_actiu },
            { key: 'telegram',  label: 'Telegram',  val: config.telegram_actiu },
            { key: 'newsletter',label: 'Newsletter',val: config.newsletter_actiu },
            { key: 'rss',       label: 'RSS',       val: config.rss_actiu },
          ].map(c => {
            const st = estat?.canals?.[c.key]
            const efectiu = st?.efectiu || (c.val ? 'actiu' : 'pausat_canal')
            return (
              <div key={c.key} className="p-3 border rounded-md flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[10px] uppercase tracking-widest text-tq-ink/75">{c.label}</p>
                  <span className={
                    'inline-block mt-1 text-[10px] uppercase tracking-wide font-semibold px-2 py-0.5 rounded-full ' +
                    (EFECTIU_TONE[efectiu] || 'bg-gray-200 text-gray-800')
                  }>
                    {EFECTIU_LABEL[efectiu] || efectiu}
                  </span>
                  {c.key === 'instagram' && st?.fase_distribucio != null && (
                    <p className="text-[10px] text-tq-ink/75 mt-1">Fase {st.fase_distribucio}/5</p>
                  )}
                  {c.key !== 'rss' && (
                    <p className="text-[10px] text-tq-ink/75 mt-1">
                      Últim enviament: {fmtLastSend(st?.ultim_enviament)}
                      {st?.font === 'audit' && ' (audit)'}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => toggleChannel(c.key)}
                  title={c.val ? 'Pausar aquest canal' : 'Activar aquest canal'}
                  className={
                    'shrink-0 px-3 py-1 rounded text-xs font-semibold ' +
                    (c.val
                      ? 'bg-emerald-700 text-white hover:bg-emerald-800'
                      : 'bg-red-700 text-white hover:bg-red-800')
                  }
                >
                  {c.val ? 'Pausar' : 'Activar'}
                </button>
              </div>
            )
          })}
        </div>

        {/* Mastodon credentials */}
        <div className="p-3 border rounded-md mb-3">
          <h3 className="text-sm font-semibold mb-1">Credencials Mastodon</h3>
          {mastodon.configured ? (
            <p className="text-xs">
              <strong>{mastodon.handle || '(handle no establert)'}</strong>
              {' '}@ <code>{mastodon.instance_url}</code>
              {' '} · token <code>{mastodon.token_masked}</code>
              {mastodon.updated_by && <> · per <strong>{mastodon.updated_by}</strong></>}
              <button type="button" onClick={testMastodon} disabled={busy}
                className="ml-2 px-2 py-1 text-[11px] rounded bg-gray-100 hover:bg-gray-200">
                Provar
              </button>
              <button type="button" onClick={clearMastodon} disabled={busy}
                className="ml-1 px-2 py-1 text-[11px] rounded bg-red-100 text-red-800 hover:bg-red-200">
                Esborrar
              </button>
            </p>
          ) : (
            <p className="text-xs text-tq-ink/75">
              Sense credencials. Crea una "App" a la teva instància (Settings → Development →
              New Application, scopes: <code>write:media write:statuses</code>) i enganxa el token.
            </p>
          )}
          <details className="mt-2">
            <summary className="text-[11px] cursor-pointer">
              {mastodon.configured ? 'Substituir credencials…' : 'Afegir credencials…'}
            </summary>
            <div className="grid sm:grid-cols-3 gap-2 mt-2">
              <Input aria-label="Instància de Mastodon" placeholder="https://mastodont.cat" value={mstInstance}
                     onChange={e => setMstInstance(e.target.value)} />
              <Input aria-label="Access token de Mastodon" placeholder="access_token" value={mstToken}
                     onChange={e => setMstToken(e.target.value)} type="password" />
              <Input aria-label="Handle de Mastodon (opcional)" placeholder="handle (opcional)" value={mstHandle}
                     onChange={e => setMstHandle(e.target.value)} />
            </div>
            <button type="button" onClick={saveMastodon} disabled={busy || !mstInstance || !mstToken}
              className="mt-2 px-3 py-1.5 bg-tq-yellow text-tq-ink rounded text-xs font-semibold hover:bg-tq-yellow-deep hover:text-white disabled:opacity-50">
              Desar
            </button>
          </details>
        </div>

        {/* Bluesky credentials */}
        <div className="p-3 border rounded-md mb-3">
          <h3 className="text-sm font-semibold mb-1">Credencials Bluesky</h3>
          {bluesky.configured ? (
            <p className="text-xs">
              <strong>@{bluesky.handle}</strong>
              {' '} · contrasenya <code>{bluesky.password_masked}</code>
              {bluesky.did && <> · DID <code className="text-[10px]">{bluesky.did}</code></>}
              {bluesky.updated_by && <> · per <strong>{bluesky.updated_by}</strong></>}
              <button type="button" onClick={testBluesky} disabled={busy}
                className="ml-2 px-2 py-1 text-[11px] rounded bg-gray-100 hover:bg-gray-200">
                Provar
              </button>
              <button type="button" onClick={clearBluesky} disabled={busy}
                className="ml-1 px-2 py-1 text-[11px] rounded bg-red-100 text-red-800 hover:bg-red-200">
                Esborrar
              </button>
            </p>
          ) : (
            <p className="text-xs text-tq-ink/75">
              Sense credencials. Crea una <strong>App Password</strong> a {' '}
              <a className="underline" href="https://bsky.app/settings/app-passwords" target="_blank" rel="noopener">
                bsky.app/settings/app-passwords
              </a> {' '} (NO la contrasenya del compte).
            </p>
          )}
          <details className="mt-2">
            <summary className="text-[11px] cursor-pointer">
              {bluesky.configured ? 'Substituir credencials…' : 'Afegir credencials…'}
            </summary>
            <div className="grid sm:grid-cols-2 gap-2 mt-2">
              <Input aria-label="Handle de Bluesky" placeholder="topquaranta.bsky.social" value={bskyHandle}
                     onChange={e => setBskyHandle(e.target.value)} />
              <Input aria-label="App password de Bluesky" placeholder="app password" value={bskyPwd}
                     onChange={e => setBskyPwd(e.target.value)} type="password" />
            </div>
            <button type="button" onClick={saveBluesky} disabled={busy || !bskyHandle || !bskyPwd}
              className="mt-2 px-3 py-1.5 bg-tq-yellow text-tq-ink rounded text-xs font-semibold hover:bg-tq-yellow-deep hover:text-white disabled:opacity-50">
              Desar
            </button>
          </details>
        </div>

        {/* Telegram credentials */}
        <div className="p-3 border rounded-md mb-3">
          <h3 className="text-sm font-semibold mb-1">Credencials Telegram</h3>
          {telegram.configured ? (
            <p className="text-xs">
              <strong>{telegram.bot_username ? `@${telegram.bot_username}` : '(bot)'}</strong>
              {' '}→ canal <code>{telegram.chat_id}</code>
              {' '} · token <code>{telegram.token_masked}</code>
              {telegram.updated_by && <> · per <strong>{telegram.updated_by}</strong></>}
              <button type="button" onClick={testTelegram} disabled={busy}
                className="ml-2 px-2 py-1 text-[11px] rounded bg-gray-100 hover:bg-gray-200">
                Provar
              </button>
              <button type="button" onClick={clearTelegram} disabled={busy}
                className="ml-1 px-2 py-1 text-[11px] rounded bg-red-100 text-red-800 hover:bg-red-200">
                Esborrar
              </button>
            </p>
          ) : (
            <p className="text-xs text-tq-ink/75">
              Sense credencials. Parla amb {' '}
              <a className="underline" href="https://t.me/BotFather" target="_blank" rel="noopener">
                @BotFather
              </a>
              {' '}, fes <code>/newbot</code>, copia el token. Després afegeix el bot al teu canal com a admin amb permís de <em>Post messages</em> i fica el handle (<code>@topquaranta</code>) com a chat_id.
            </p>
          )}
          <details className="mt-2">
            <summary className="text-[11px] cursor-pointer">
              {telegram.configured ? 'Substituir credencials…' : 'Afegir credencials…'}
            </summary>
            <div className="grid sm:grid-cols-2 gap-2 mt-2">
              <Input aria-label="Bot token de Telegram" placeholder="bot_token (de @BotFather)" value={tgToken}
                     onChange={e => setTgToken(e.target.value)} type="password" />
              <Input aria-label="Canal de Telegram" placeholder="@canal o ID numèric" value={tgChatId}
                     onChange={e => setTgChatId(e.target.value)} />
            </div>
            <button type="button" onClick={saveTelegram} disabled={busy || !tgToken || !tgChatId}
              className="mt-2 px-3 py-1.5 bg-tq-yellow text-tq-ink rounded text-xs font-semibold hover:bg-tq-yellow-deep hover:text-white disabled:opacity-50">
              Desar
            </button>
          </details>
        </div>

        <p className="text-[11px] text-tq-ink/75">
          La <strong>newsletter</strong> usa l'SMTP configurat a <code>EMAIL_HOST</code>;
          envia automàticament cada dissabte als usuaris amb <code>vol_newsletter=True</code>.
          L'<strong>RSS</strong> es serveix a <code>/rss/top.xml</code> + <code>/rss/novetats.xml</code> sense altres credencials.
        </p>
      </section>

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

      {/* ── Posts list ───────────────────────────────────────── */}
      <Table>
        <thead>
          <tr>
            <th className="text-left">Data</th>
            <th className="text-left">Setmana</th>
            <th className="text-left">Plataforma</th>
            <th className="text-left">Tipus</th>
            <th className="text-left">Territori</th>
            <th className="text-left">Estat</th>
            <th className="text-left">Accions</th>
          </tr>
        </thead>
        <tbody>
          {results.flatMap((p, idx) => {
            // Per-platform row tint so the operator scans the table
            // by channel at a glance. Tints are deliberately faint
            // (~5-8 % opacity) to keep text contrast high; brand
            // colours follow each platform's identity:
            //  · IG → soft pink (Instagram gradient endpoint)
            //  · Mastodon → soft indigo/violet
            //  · Bluesky → soft sky-blue
            //  · Telegram → soft cyan
            //  · Newsletter → soft amber
            //  · RSS → soft orange
            const platformTints = {
              instagram_feed: 'bg-pink-50',
              instagram_story: 'bg-pink-50/60',
              mastodon: 'bg-indigo-50',
              bluesky: 'bg-sky-50',
              telegram: 'bg-cyan-50',
              newsletter: 'bg-amber-50',
              rss: 'bg-orange-50',
            }
            const rowBg = platformTints[p.platform] || 'bg-white'
            return [
            <tr key={p.pk} className={`${rowBg} align-top border-t border-tq-ink/10`}>
              <td className="text-xs whitespace-nowrap font-mono">
                {p.published_at
                  ? p.published_at.slice(0, 16).replace('T', ' ')
                  : <span className="text-tq-ink/50 italic" title={`Creat: ${p.created_at?.slice(0, 16).replace('T', ' ')}`}>
                      {p.created_at?.slice(0, 10) || '—'}
                    </span>}
              </td>
              <td className="font-semibold whitespace-nowrap" title={`Publicació prevista: ${p.publication_date}`}>
                Setmana {p.project_week}
                <div className="text-[10px] text-tq-ink/70 font-normal">
                  {p.publication_date}
                </div>
              </td>
              <td className="text-xs">{p.platform.replace('instagram_', '')}</td>
              <td className="text-xs">{p.tipus}</td>
              <td>{p.territori_label}</td>
              <td>
                <StatusBadge status={p.status} />
                {p.error_msg && (
                  <p className="text-[10px] text-red-700 mt-1 max-w-[18rem] break-words"
                     title={p.error_msg}>
                    {p.error_msg.length > 80
                      ? p.error_msg.slice(0, 80) + '…'
                      : p.error_msg}
                  </p>
                )}
              </td>
              <td>
                <div className="flex flex-wrap gap-1">
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
                    onClick={() => loadSlides(p)}
                    disabled={busy}
                    className="text-xs px-2 py-1 rounded bg-gray-100 hover:bg-gray-200"
                  >
                    Veure slides
                  </button>
                  <button
                    type="button"
                    onClick={() => publicarAra(p)}
                    disabled={busy}
                    className="text-xs px-2 py-1 rounded bg-tq-ink text-tq-yellow font-semibold hover:bg-tq-ink/90"
                  >
                    Publicar
                  </button>
                  <button
                    type="button"
                    onClick={() => resetPost(p)}
                    disabled={busy}
                    title="Marca la fila com a pendent. No toca IG. Útil per reintentar."
                    className="text-xs px-2 py-1 rounded bg-gray-100 hover:bg-gray-200"
                  >
                    Reset
                  </button>
                  {p.instagram_media_id && (() => {
                    // Platform-aware delete label. The DB field is
                    // historically named `instagram_media_id` but we
                    // reuse it for every channel's external id; the
                    // backend dispatches by `platform`.
                    const labels = {
                      'instagram_feed': 'Esborrar IG',
                      'instagram_story': 'Esborrar story IG',
                      'mastodon': 'Esborrar Mastodon',
                      'bluesky': 'Esborrar Bluesky',
                      'telegram': 'Esborrar Telegram',
                    }
                    const label = labels[p.platform] || `Esborrar ${p.platform}`
                    return (
                      <>
                        <button
                          type="button"
                          onClick={() => republicar(p)}
                          disabled={busy}
                          title="Esborra el remot + re-publica amb el contingut actualitzat. Útil si una cançó del top va ser rebutjada després de publicar."
                          className="text-xs px-2 py-1 rounded bg-amber-100 text-amber-900 hover:bg-amber-200"
                        >
                          Re-publicar
                        </button>
                        <button
                          type="button"
                          onClick={() => eliminarRemot(p)}
                          disabled={busy}
                          title={`Esborra la publicació remota a ${p.platform} + reset local`}
                          className="text-xs px-2 py-1 rounded bg-red-100 text-red-800 hover:bg-red-200"
                        >
                          {label}
                        </button>
                      </>
                    )
                  })()}
                </div>
              </td>
            </tr>,
            slidesByPk[p.pk] ? (
              <tr key={`${p.pk}-slides`} className={rowBg}>
                <td colSpan={7} className="p-3 border-b border-tq-ink/10">
                  <SlidesGallery slides={slidesByPk[p.pk]} />
                </td>
              </tr>
            ) : null,
          ]
          }).filter(Boolean)}
        </tbody>
      </Table>

      {results.length === 0 && (
        <p className="text-sm text-tq-ink/75 italic">
          Encara no hi ha cap publicació. Utilitza Preview per generar-ne en mode dry-run.
        </p>
      )}
    </section>
  )
}

function SlidesGallery({ slides }) {
  const both = (slides.feed?.length || 0) + (slides.stories?.length || 0)
  if (both === 0) {
    return (
      <p className="text-xs text-tq-ink/75 italic">
        Cap PNG renderitzat. Fes "Preview" primer per generar-los.
      </p>
    )
  }
  return (
    <div className="space-y-3">
      {slides.feed?.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/75 mb-1.5">
            Feed · {slides.feed.length} {slides.feed.length === 1 ? 'slide' : 'slides'}
          </p>
          <div className="flex flex-wrap gap-2">
            {slides.feed.map(s => (
              <a key={s.name} href={s.url} target="_blank" rel="noopener"
                 title={`${s.name} (${s.size_kb} kB)`}>
                <img src={s.url} alt={s.name}
                     className="w-32 h-40 object-cover rounded border border-tq-ink/20 hover:border-tq-ink" />
              </a>
            ))}
          </div>
        </div>
      )}
      {slides.stories?.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/75 mb-1.5">
            Stories · {slides.stories.length} {slides.stories.length === 1 ? 'story' : 'stories'}
          </p>
          <div className="flex flex-wrap gap-2">
            {slides.stories.map(s => (
              <a key={s.name} href={s.url} target="_blank" rel="noopener"
                 title={`${s.name} (${s.size_kb} kB)`}>
                <img src={s.url} alt={s.name}
                     className="w-24 h-44 object-cover rounded border border-tq-ink/20 hover:border-tq-ink" />
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
