/**
 * SpotifyCallbackPage — /spotify/callback
 *
 * One-off landing page used by the `autoritzar_spotify` Django
 * management command. Spotify redirects here after the admin
 * approves the app; we read the `?code=…` query string and show it
 * prominently so the admin can copy it back into their SSH terminal.
 *
 * Nothing is sent to the backend from here — the code exchange
 * happens inside the management command using the client secret,
 * which we don't want to ship to the browser.
 */
import { useSearchParams } from 'react-router-dom'
import Alert from '../components/ui/Alert'

export default function SpotifyCallbackPage() {
  const [params] = useSearchParams()
  const code = params.get('code')
  const error = params.get('error')

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

      {code && (
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
