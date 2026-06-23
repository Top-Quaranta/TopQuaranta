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
import { Btn, Callout, Pill } from '../../components/rd/surface'

// Coverage bar colour bands match the FASE F monitoring thresholds:
// >=0.95 green, 0.85-0.95 yellow, <0.85 red. NULL coverage (never
// synced or no source data yet) is grey.
function coverageBar(ratio) {
  let bar = 'bg-tq-ink/15'
  if (ratio !== null && ratio !== undefined) {
    if (ratio >= 0.95) bar = 'bg-green-500'
    else if (ratio >= 0.85) bar = 'bg-yellow-500'
    else bar = 'bg-red-500'
  }
  const pct =
    ratio === null || ratio === undefined ? '—' : `${Math.round(ratio * 100)}%`
  const width =
    ratio === null || ratio === undefined ? '0%' : `${Math.round(ratio * 100)}%`
  return (
    <div className="flex items-center gap-1">
      <div className="w-20 h-2 bg-tq-ink/10 rounded">
        <div className={`${bar} h-2 rounded`} style={{ width }} />
      </div>
      <span className="text-[11px] text-tq-ink/60 w-9 text-right">{pct}</span>
    </div>
  )
}

function PlaylistRow({ pl }) {
  const last =
    pl.last_sync_at !== null
      ? new Date(pl.last_sync_at).toLocaleString('ca-ES')
      : 'mai'
  // Pre-sync (target_coverage): of the cançons this playlist would
  // push next time, how many are already cache-resolved. Useful to
  // decide if a manual sync is worth running.
  const target = pl.target_coverage || { total: 0, found: 0, ratio: null }
  return (
    <tr className="border-b border-tq-ink/10">
      <td className="px-3 py-2 text-sm font-mono">{pl.codi}</td>
      <td className="px-3 py-2 text-sm">{pl.territori || '—'}</td>
      <td className="px-3 py-2 text-xs text-tq-ink/60">{last}</td>
      <td className="px-3 py-2 text-sm">{pl.last_sync_ok ? '✓' : '✗'}</td>
      <td className="px-3 py-2 text-sm">
        {pl.last_n_matched}/{pl.last_n_tracks}
      </td>
      <td className="px-3 py-2">{coverageBar(pl.coverage)}</td>
      <td className="px-3 py-2 text-sm">
        {target.found}/{target.total}
      </td>
      <td className="px-3 py-2">{coverageBar(target.ratio)}</td>
      <td className="px-3 py-2">
        {pl.spotify_url && (
          <a
            href={pl.spotify_url}
            target="_blank"
            rel="noopener"
            className="text-[11px] text-tq-yellow-deep underline"
          >
            obrir
          </a>
        )}
      </td>
    </tr>
  )
}

function PlaylistTable({ playlists }) {
  // Shared markup for any of the three sections below. The column
  // set is the same; only the row source changes.
  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b border-tq-ink/15 text-xs text-tq-ink/60 uppercase">
          <th className="px-3 py-2">Codi</th>
          <th className="px-3 py-2">Territori</th>
          <th className="px-3 py-2">Últim sync</th>
          <th className="px-3 py-2">OK</th>
          <th className="px-3 py-2">Match/Total (sync)</th>
          <th className="px-3 py-2">Cobertura (sync)</th>
          <th className="px-3 py-2">Cache/Target</th>
          <th className="px-3 py-2">Cobertura (futura)</th>
          <th className="px-3 py-2"></th>
        </tr>
      </thead>
      <tbody>
        {playlists.map(pl => (
          <PlaylistRow key={pl.codi} pl={pl} />
        ))}
      </tbody>
    </table>
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
        <Callout tone="red">{error}</Callout>
      </section>
    )
  }
  if (!estat) {
    return <p className="text-tq-ink/60 px-6 py-8">Carregant…</p>
  }

  const productBadge =
    estat.product === 'premium' ? (
      <Pill tone="green">Premium</Pill>
    ) : estat.product ? (
      <Pill tone="red">{estat.product}</Pill>
    ) : (
      <Pill tone="gray">no autoritzat</Pill>
    )

  return (
    <section className="max-w-5xl mx-auto py-6 text-tq-ink">
      <header className="mb-6">
        <p className="text-[10px] uppercase tracking-widest text-tq-ink/60">
          Distribució · Spotify
        </p>
        <h1 className="text-2xl font-bold">Sincronització de playlists</h1>
        {estat.enrichment_coverage && (
          <div className="mt-2 text-sm">
            <span className="text-tq-ink/60">Cobertura d'enriquiment del catàleg: </span>
            <span className="font-bold">
              {estat.enrichment_coverage.ratio == null
                ? '—'
                : `${Math.round(estat.enrichment_coverage.ratio * 100)} %`}
            </span>
            <span className="text-tq-ink/50">
              {' '}
              ({estat.enrichment_coverage.enriched.toLocaleString('ca-ES')}/
              {estat.enrichment_coverage.total.toLocaleString('ca-ES')} cançons amb
              ISRC)
            </span>
          </div>
        )}
      </header>

      {oauthBanner === 'ok' && (
        <Callout tone="green" className="mb-4">
          OAuth completat. La sincronització ja pot rodar.
        </Callout>
      )}

      {/* Section 1 — Identity & OAuth */}
      <section className="bg-white border border-tq-ink/10 rounded p-4 mb-6">
        <h2 className="text-sm font-semibold mb-3 text-tq-ink/80">
          Identitat & OAuth
        </h2>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <dt className="text-tq-ink/60">Producte Spotify</dt>
          <dd>{productBadge}</dd>
          <dt className="text-tq-ink/60">User ID</dt>
          <dd className="font-mono">{estat.spotify_user_id || '—'}</dd>
          <dt className="text-tq-ink/60">Display name</dt>
          <dd>{estat.display_name || '—'}</dd>
          <dt className="text-tq-ink/60">Country</dt>
          <dd>{estat.country || '—'}</dd>
          <dt className="text-tq-ink/60">Scope</dt>
          <dd className="font-mono text-xs">{estat.scope || '—'}</dd>
          <dt className="text-tq-ink/60">Última actualització</dt>
          <dd>
            {estat.updated_at
              ? new Date(estat.updated_at).toLocaleString('ca-ES')
              : 'mai'}
          </dd>
        </dl>

        {estat.live_error && (
          <Callout tone="red" className="mt-3">
            Spotify ha rebutjat el refresh_token: {estat.live_error}.
            Reautoritza per a continuar.
          </Callout>
        )}
        {estat.oauth_present && estat.product && estat.product !== 'premium' && (
          <Callout tone="red" className="mt-3">
            L'usuari de Spotify no és Premium (product=
            <strong>{estat.product}</strong>). La sincronització
            retornarà 403. Activa Premium al compte i reautoritza.
          </Callout>
        )}

        <div className="mt-4">
          <Btn
            tone="primary"
            size="md"
            onClick={startOAuth}
            disabled={pending}
          >
            {estat.oauth_present ? 'Reautoritzar Spotify' : 'Autoritzar Spotify'}
          </Btn>
        </div>
      </section>

      {/* Section 2a — Weekly public mirrors (FASE D, 2026-05-23).
          These are the 5 charts users follow. Visually distinguished
          because they are the externally visible face of the data. */}
      {estat.playlists.some(p => p.freq === 'weekly') && (
        <section className="bg-white border-2 border-tq-yellow/40 rounded p-4 mb-6">
          <div className="flex justify-between items-center mb-2">
            <div>
              <h2 className="text-sm font-semibold text-tq-yellow-deep">
                Playlists públiques setmanals
              </h2>
              <p className="text-xs text-tq-ink/60 mt-1">
                Cara externa: 5 playlists que els usuaris segueixen.
                Font: TopSetmanal (setmana més recent per territori).
                Cobertura futura mostra quantes cançons del top
                ja estan resolucionades al cache; mira aquest número
                abans de prémer sync.
              </p>
            </div>
            <div className="flex gap-2">
              <Btn
                tone="secondary"
                size="sm"
                onClick={() => runSync('weekly', true)}
                disabled={pending || !estat.oauth_present}
              >
                Dry-run weekly
              </Btn>
              <Btn
                tone="primary"
                size="sm"
                onClick={() => runSync('weekly', false)}
                disabled={pending || !estat.oauth_present}
              >
                Sync weekly
              </Btn>
            </div>
          </div>
          <PlaylistTable
            playlists={estat.playlists.filter(p => p.freq === 'weekly')}
          />
        </section>
      )}

      {/* Section 2b — Daily provisional tops. Internal-facing
          (operators inspect them; users don't usually follow). */}
      <section className="bg-white border border-tq-ink/10 rounded p-4 mb-6">
        <div className="flex justify-between items-center mb-3">
          <div>
            <h2 className="text-sm font-semibold text-tq-ink/80">
              Playlists provisionals diàries
            </h2>
            <p className="text-xs text-tq-ink/60 mt-1">
              Font: TopProvisional. Cron diari 07:15 UTC.
            </p>
          </div>
          <div className="flex gap-2">
            <Btn
              tone="secondary"
              size="sm"
              onClick={() => runSync('daily', true)}
              disabled={pending || !estat.oauth_present}
            >
              Dry-run daily
            </Btn>
            <Btn
              tone="primary"
              size="sm"
              onClick={() => runSync('daily', false)}
              disabled={pending || !estat.oauth_present}
            >
              Sync daily
            </Btn>
          </div>
        </div>
        <PlaylistTable
          playlists={estat.playlists.filter(
            p => p.freq === 'daily' && p.kind !== 'no_verificades'
          )}
        />
      </section>

      {/* Section 2c — No_verificades triage chunks. */}
      <section className="bg-white border border-tq-ink/10 rounded p-4 mb-6">
        <div className="flex justify-between items-center mb-3">
          <div>
            <h2 className="text-sm font-semibold text-tq-ink/80">
              Triage no verificades
            </h2>
            <p className="text-xs text-tq-ink/60 mt-1">
              7 chunks de 100 cançons pendents de verificar ordenades
              per ml_confianca desc. Sincronitzades amb el mateix
              cron daily.
            </p>
          </div>
        </div>
        <PlaylistTable
          playlists={estat.playlists.filter(p => p.kind === 'no_verificades')}
        />
      </section>

      {estat.playlists.length === 0 && (
        <section className="bg-white border border-tq-ink/10 rounded p-4 mb-6">
          <p className="text-sm text-tq-ink/60">
            Cap fila a SpotifyPlaylist. Executa{' '}
            <code className="text-xs bg-tq-ink/10 px-1">
              configurar_spotify_playlists
            </code>{' '}
            per a registrar els IDs.
          </p>
        </section>
      )}

      {/* Sync output */}
      {syncRun && (
        <section className="bg-white border border-tq-ink/10 rounded p-4 mb-6">
          <h2 className="text-sm font-semibold mb-3 text-tq-ink/80">
            Resultat sync més recent
          </h2>
          {syncRun.error && (
            <Callout tone="red" className="mb-3">
              {syncRun.error}
            </Callout>
          )}
          {syncRun.stdout && (
            <pre className="bg-tq-ink text-white/90 p-3 text-xs overflow-x-auto whitespace-pre-wrap rounded">
              {syncRun.stdout}
            </pre>
          )}
          {syncRun.stderr && (
            <pre className="bg-red-950 text-red-100 p-3 text-xs overflow-x-auto whitespace-pre-wrap rounded mt-2">
              {syncRun.stderr}
            </pre>
          )}
        </section>
      )}

      {/* Section 3 — Cron */}
      <section className="bg-white border border-tq-ink/10 rounded p-4">
        <h2 className="text-sm font-semibold mb-3 text-tq-ink/80">Cron</h2>
        <p className="text-sm">
          Estat:{' '}
          {estat.cron_silenced ? (
            <Pill tone="yellow">silenciat</Pill>
          ) : (
            <Pill tone="green">actiu</Pill>
          )}
        </p>
        <p className="text-xs text-tq-ink/60 mt-2 leading-relaxed">
          La gestió del flag <code>silenced</code> es fa via commit a{' '}
          <code className="text-xs bg-tq-ink/10 px-1">
            deploy/cron-meta.json
          </code>
          . No es pot canviar en runtime perquè qualsevol mutació es
          revertiria al pròxim deploy.
        </p>
      </section>
    </section>
  )
}
