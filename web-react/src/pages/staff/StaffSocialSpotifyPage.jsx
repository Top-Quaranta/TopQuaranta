/**
 * StaffSocialSpotifyPage — /staff/social/spotify/
 *
 * Single landing for the Spotify integration health and OAuth flow.
 *
 * Three sections:
 *   1. Identity & OAuth status (live `me()` call surfaced via the
 *      backend's /estat/ endpoint).
 *   2. Playlist table with last-sync KPIs.
 *   3. Cron silenced flag (read-only; commit to deploy/cron-meta.json
 *      to flip it permanently — see ADR-0009 + FASE C.4).
 *
 * The page is the home for FASE B-G of the playlists revival sprint.
 * Built incrementally: B builds the shell, C performs the first
 * real OAuth + sync, D adds the weekly playlists, F adds monitoring.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api } from '../../lib/api'
import Alert from '../../components/ui/Alert'
import Button from '../../components/ui/Button'

function PlaylistRow({ pl }) {
  // Coverage bar colour bands match the FASE F monitoring thresholds:
  // >=0.95 green, 0.85-0.95 yellow, <0.85 red. NULL coverage (never
  // synced) is grey.
  const cov = pl.coverage
  let bar = 'bg-white/20'
  if (cov !== null && cov !== undefined) {
    if (cov >= 0.95) bar = 'bg-green-500'
    else if (cov >= 0.85) bar = 'bg-yellow-500'
    else bar = 'bg-red-500'
  }
  const pct =
    cov === null || cov === undefined ? '—' : `${Math.round(cov * 100)}%`
  const last =
    pl.last_sync_at !== null
      ? new Date(pl.last_sync_at).toLocaleString('ca-ES')
      : 'mai'
  return (
    <tr className="border-b border-white/10">
      <td className="px-3 py-2 text-sm font-mono">{pl.codi}</td>
      <td className="px-3 py-2 text-sm">{pl.kind}</td>
      <td className="px-3 py-2 text-sm">{pl.territori || '—'}</td>
      <td className="px-3 py-2 text-xs text-white/60">{last}</td>
      <td className="px-3 py-2 text-sm">
        {pl.last_sync_ok ? '✓' : '✗'}
      </td>
      <td className="px-3 py-2 text-sm">
        {pl.last_n_matched}/{pl.last_n_tracks}
      </td>
      <td className="px-3 py-2">
        <div className="w-24 h-2 bg-white/10 rounded">
          <div
            className={`${bar} h-2 rounded`}
            style={{
              width:
                cov === null || cov === undefined
                  ? '0%'
                  : `${Math.round(cov * 100)}%`,
            }}
          />
        </div>
        <span className="text-[11px] text-white/60">{pct}</span>
      </td>
      <td className="px-3 py-2">
        {pl.spotify_url && (
          <a
            href={pl.spotify_url}
            target="_blank"
            rel="noopener"
            className="text-[11px] text-tq-yellow underline"
          >
            obrir
          </a>
        )}
      </td>
    </tr>
  )
}

export default function StaffSocialSpotifyPage() {
  const [params] = useSearchParams()
  const oauthBanner = params.get('oauth')

  const [estat, setEstat] = useState(null)
  const [error, setError] = useState(null)
  const [syncRun, setSyncRun] = useState(null)
  const [pending, setPending] = useState(false)

  const refresh = () => {
    setError(null)
    api
      .get('/staff/social/spotify/estat/')
      .then(setEstat)
      .catch(e => setError(e.message || 'Error'))
  }

  useEffect(() => {
    refresh()
  }, [])

  const startOAuth = async () => {
    setPending(true)
    try {
      const r = await api.post('/staff/social/spotify/oauth-start/', {})
      // Hard-navigate to Spotify. After consent Spotify will redirect
      // back to /staff/social/spotify/callback (the SpotifyCallbackPage
      // component) which auto-POSTs the code to the backend.
      window.location.href = r.url
    } catch (e) {
      setError(e?.body?.error || e.message || 'Error')
      setPending(false)
    }
  }

  const runSync = async (freq, dryRun) => {
    setPending(true)
    setSyncRun(null)
    try {
      const r = await api.post('/staff/social/spotify/sync/', {
        freq,
        dry_run: dryRun,
      })
      setSyncRun(r)
      refresh()
    } catch (e) {
      setSyncRun({
        ok: false,
        error: e?.body?.error || e.message || 'Error',
        stdout: e?.body?.stdout || '',
        stderr: e?.body?.stderr || '',
      })
    } finally {
      setPending(false)
    }
  }

  if (error) {
    return (
      <section className="max-w-5xl mx-auto py-8">
        <Alert tone="danger">{error}</Alert>
      </section>
    )
  }
  if (!estat) {
    return <p className="text-white/60 px-6 py-8">Carregant…</p>
  }

  const productBadge =
    estat.product === 'premium' ? (
      <span className="inline-block px-2 py-0.5 text-xs bg-green-600 text-white rounded">
        Premium
      </span>
    ) : estat.product ? (
      <span className="inline-block px-2 py-0.5 text-xs bg-red-600 text-white rounded">
        {estat.product}
      </span>
    ) : (
      <span className="inline-block px-2 py-0.5 text-xs bg-white/20 text-white rounded">
        no autoritzat
      </span>
    )

  return (
    <section className="max-w-5xl mx-auto py-6 text-white">
      <header className="mb-6">
        <p className="text-[10px] uppercase tracking-widest text-white/60">
          Distribució · Spotify
        </p>
        <h1 className="text-2xl font-bold">Sincronització de playlists</h1>
      </header>

      {oauthBanner === 'ok' && (
        <Alert tone="success" className="mb-4">
          OAuth completat. La sincronització ja pot rodar.
        </Alert>
      )}

      {/* Section 1 — Identity & OAuth */}
      <section className="bg-tq-ink-soft border border-white/10 rounded p-4 mb-6">
        <h2 className="text-sm font-semibold mb-3 text-white/80">
          Identitat & OAuth
        </h2>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <dt className="text-white/60">Producte Spotify</dt>
          <dd>{productBadge}</dd>
          <dt className="text-white/60">User ID</dt>
          <dd className="font-mono">{estat.spotify_user_id || '—'}</dd>
          <dt className="text-white/60">Display name</dt>
          <dd>{estat.display_name || '—'}</dd>
          <dt className="text-white/60">Country</dt>
          <dd>{estat.country || '—'}</dd>
          <dt className="text-white/60">Scope</dt>
          <dd className="font-mono text-xs">{estat.scope || '—'}</dd>
          <dt className="text-white/60">Última actualització</dt>
          <dd>
            {estat.updated_at
              ? new Date(estat.updated_at).toLocaleString('ca-ES')
              : 'mai'}
          </dd>
        </dl>

        {estat.live_error && (
          <Alert tone="danger" className="mt-3">
            Spotify ha rebutjat el refresh_token: {estat.live_error}.
            Reautoritza per a continuar.
          </Alert>
        )}
        {estat.oauth_present && estat.product && estat.product !== 'premium' && (
          <Alert tone="danger" className="mt-3">
            L'usuari de Spotify no és Premium (product=
            <strong>{estat.product}</strong>). La sincronització
            retornarà 403. Activa Premium al compte i reautoritza.
          </Alert>
        )}

        <div className="mt-4">
          <Button
            variant="primary"
            onClick={startOAuth}
            disabled={pending}
          >
            {estat.oauth_present ? 'Reautoritzar Spotify' : 'Autoritzar Spotify'}
          </Button>
        </div>
      </section>

      {/* Section 2 — Playlists */}
      <section className="bg-tq-ink-soft border border-white/10 rounded p-4 mb-6">
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-sm font-semibold text-white/80">Playlists</h2>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => runSync(null, true)}
              disabled={pending || !estat.oauth_present}
            >
              Dry-run totes
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => runSync(null, false)}
              disabled={pending || !estat.oauth_present}
            >
              Sync ara
            </Button>
          </div>
        </div>
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-white/20 text-xs text-white/60 uppercase">
              <th className="px-3 py-2">Codi</th>
              <th className="px-3 py-2">Tipus</th>
              <th className="px-3 py-2">Territori</th>
              <th className="px-3 py-2">Last sync</th>
              <th className="px-3 py-2">OK</th>
              <th className="px-3 py-2">Match/Total</th>
              <th className="px-3 py-2">Cobertura</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {estat.playlists.map(pl => (
              <PlaylistRow key={pl.codi} pl={pl} />
            ))}
          </tbody>
        </table>
        {estat.playlists.length === 0 && (
          <p className="text-sm text-white/60 mt-3">
            Cap fila a SpotifyPlaylist. Executa{' '}
            <code className="text-xs bg-white/10 px-1">
              configurar_spotify_playlists
            </code>{' '}
            per a registrar els IDs.
          </p>
        )}
      </section>

      {/* Sync output */}
      {syncRun && (
        <section className="bg-tq-ink-soft border border-white/10 rounded p-4 mb-6">
          <h2 className="text-sm font-semibold mb-3 text-white/80">
            Resultat sync més recent
          </h2>
          {syncRun.error && (
            <Alert tone="danger" className="mb-3">
              {syncRun.error}
            </Alert>
          )}
          {syncRun.stdout && (
            <pre className="bg-black/40 p-3 text-xs overflow-x-auto whitespace-pre-wrap rounded">
              {syncRun.stdout}
            </pre>
          )}
          {syncRun.stderr && (
            <pre className="bg-red-950/40 p-3 text-xs overflow-x-auto whitespace-pre-wrap rounded mt-2">
              {syncRun.stderr}
            </pre>
          )}
        </section>
      )}

      {/* Section 3 — Cron */}
      <section className="bg-tq-ink-soft border border-white/10 rounded p-4">
        <h2 className="text-sm font-semibold mb-3 text-white/80">Cron</h2>
        <p className="text-sm">
          Estat:{' '}
          {estat.cron_silenced ? (
            <span className="text-yellow-400">silenciat</span>
          ) : (
            <span className="text-green-400">actiu</span>
          )}
        </p>
        <p className="text-xs text-white/60 mt-2 leading-relaxed">
          La gestió del flag <code>silenced</code> es fa via commit a{' '}
          <code className="text-xs bg-white/10 px-1">
            deploy/cron-meta.json
          </code>
          . No es pot canviar en runtime perquè qualsevol mutació es
          revertiria al pròxim deploy.
        </p>
      </section>
    </section>
  )
}
