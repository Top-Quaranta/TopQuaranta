/**
 * SpotifyCallbackPage — landing page Spotify redirects to after
 * the staff approves the app on the OAuth consent screen.
 *
 * Mounted at TWO routes for backward compatibility:
 *   - /spotify/callback                       (legacy, kept so the
 *                                              SSH-based autoritzar_spotify
 *                                              flow still works if anyone
 *                                              tries to use it).
 *   - /staff/social/spotify/callback          (canonical since FASE B of
 *                                              the playlists revival).
 *
 * Behaviour by route:
 *   - Legacy path: show the raw `code` for terminal paste-back (the
 *     pre-FASE-B behaviour).
 *   - Canonical path: POST the code straight to the backend so it
 *     can exchange it for a refresh_token and persist. Then redirect
 *     to /staff/social/spotify/ with a query-param banner.
 *
 * The route discriminator uses `window.location.pathname` because
 * react-router's `useLocation()` doesn't change between the moment
 * Spotify lands us here and the redirect away.
 */
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '../lib/api'
import Alert from '../components/ui/Alert'

export default function SpotifyCallbackPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const code = params.get('code')
  const state = params.get('state')
  const error = params.get('error')

  // `pending` covers the inflight POST; `result` holds the final
  // success/error message we render before the redirect kicks in.
  const [pending, setPending] = useState(false)
  const [result, setResult] = useState(null)

  const isStaffPath = window.location.pathname.startsWith('/staff/')

  // Auto-POST to the backend exchange endpoint when we land on the
  // canonical /staff/ path with a code in hand. The legacy /spotify/
  // path keeps the paste-it-yourself behaviour for fallback.
  useEffect(() => {
    if (!isStaffPath || !code || error || pending || result) return
    setPending(true)
    api
      .post('/staff/social/spotify/oauth-callback/', { code, state })
      .then(d => {
        setResult({ ok: true, payload: d })
        // Bounce to the management page after a short pause so the
        // user sees the success message at least once.
        setTimeout(() => {
          navigate('/staff/social/spotify/?oauth=ok', { replace: true })
        }, 1500)
      })
      .catch(e => {
        setResult({
          ok: false,
          error: e?.body?.error || e?.message || 'Error desconegut',
        })
      })
  }, [isStaffPath, code, state, error, pending, result, navigate])

  return (
    <section className="max-w-xl mx-auto py-12 text-white">
      <p className="text-[10px] uppercase tracking-widest text-white/60 mb-1">
        Spotify · autorització
      </p>
      <h1 className="text-3xl font-bold mb-3">Callback</h1>

      {error && (
        <Alert tone="danger" className="mb-4">
          Spotify ha tornat un error: <strong>{error}</strong>
        </Alert>
      )}

      {/* Canonical (staff) flow */}
      {isStaffPath && code && pending && !result && (
        <Alert tone="info" className="mb-4">
          Intercanviant el codi amb Spotify…
        </Alert>
      )}
      {isStaffPath && result?.ok && (
        <Alert tone="success" className="mb-4">
          Autoritzat com a <strong>{result.payload.spotify_user_id}</strong> ·
          producte: <strong>{result.payload.product}</strong>. Redirigint…
        </Alert>
      )}
      {isStaffPath && result?.ok === false && (
        <>
          <Alert tone="danger" className="mb-4">
            No s'ha pogut completar l'autorització: {result.error}
          </Alert>
          <p className="text-sm text-white/70">
            Torna a{' '}
            <a
              href="/staff/social/spotify/"
              className="text-tq-yellow underline"
            >
              /staff/social/spotify/
            </a>{' '}
            i reinicia el flux.
          </p>
        </>
      )}

      {/* Legacy (terminal) flow */}
      {!isStaffPath && code && (
        <>
          <p className="text-sm text-white/80 mb-3">
            Spotify ha autoritzat TopQuaranta. Copia el codi d'avall i
            enganxa'l a la sessió del terminal on estàs executant{' '}
            <code className="bg-white/10 px-1.5 py-0.5 rounded text-[11px]">
              manage.py autoritzar_spotify
            </code>
            .
          </p>

          <div className="bg-tq-ink-soft border border-tq-yellow/30 rounded-md p-4">
            <p className="text-[10px] uppercase tracking-wide text-tq-yellow mb-2">
              Code
            </p>
            <p
              className="font-mono text-sm break-all select-all"
              style={{ userSelect: 'all' }}
            >
              {code}
            </p>
          </div>

          <p className="text-[11px] text-white/50 mt-4 leading-relaxed">
            Aquest codi caduca en pocs minuts. Si triges, torna a
            executar el comando per generar-ne un de nou.
          </p>
        </>
      )}

      {!code && !error && (
        <p className="text-sm text-white/70">
          Aquesta pàgina només té sentit quan hi arribes des del flow
          d'autorització Spotify. Si has arribat aquí sense voler,
          torna{' '}
          <a href="/" className="text-tq-yellow underline">
            a l'inici
          </a>
          .
        </p>
      )}
    </section>
  )
}
