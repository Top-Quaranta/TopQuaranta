/**
 * AuthPage — /compte/accedir
 *
 * Dual-mode: a pill toggle between "Entrar" and "Crear compte".
 * Sign-in hits /api/v1/auth/login/ and navigates home. Sign-up hits
 * /api/v1/auth/register/, which creates an inactive user and emails
 * an activation link; the form then collapses into a confirmation
 * message pointing users at their inbox. The actual activation still
 * happens via Django's /compte/activar/<uid>/<token>/ route (already
 * in the Caddy allow-list).
 *
 * Anti-enumeration: the backend responds with the same 201 shape for
 * "new" and "already-registered" emails, so the UI behaves the same
 * either way.
 *
 * A `?next=<path>` query-string is honored on successful sign-in so
 * flows like AdminRoute's 2FA bounce can resume where they left off.
 */
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'

const inputClass =
  'mt-1 w-full border border-gray-300 rounded-md px-3 py-2 text-sm'

function TabButton({ active, onClick, children }) {
  // role="tab" + aria-selected to satisfy axe's `aria-required-children`
  // rule on the parent role="tablist" wrapper. tabIndex follows the
  // standard tab pattern: only the active tab is in the focus order;
  // the others are reachable via arrow keys (handled by the browser
  // when role/state are set correctly).
  return (
    <button
      type="button"
      onClick={onClick}
      role="tab"
      aria-selected={active}
      tabIndex={active ? 0 : -1}
      className={
        'flex-1 text-sm font-semibold py-2 transition-colors ' +
        (active
          ? 'bg-tq-yellow text-tq-ink'
          : 'bg-transparent text-white/70 hover:text-white')
      }
    >
      {children}
    </button>
  )
}

export default function AuthPage() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const nextPath = params.get('next') || '/'

  const [mode, setMode] = useState(params.get('mode') === 'registre' ? 'register' : 'login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [errors, setErrors] = useState({})
  const [generalError, setGeneralError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [registrationSent, setRegistrationSent] = useState(false)

  function switchMode(next) {
    if (next === mode) return
    setMode(next)
    setErrors({})
    setGeneralError(null)
  }

  async function handleLogin(e) {
    e.preventDefault()
    setErrors({})
    setGeneralError(null)
    setBusy(true)
    try {
      const me = await signIn(email, password)
      // First-time post-registration users land on onboarding; the
      // flag is set by the activation-email handler. Users who
      // already did / skipped it go to their intended destination.
      if (me && me.is_authenticated && !me.onboarding_complet) {
        navigate('/onboarding')
      } else {
        navigate(nextPath || '/')
      }
    } catch (err) {
      setGeneralError(err.message || 'Error')
    } finally {
      setBusy(false)
    }
  }

  async function handleRegister(e) {
    e.preventDefault()
    setErrors({})
    setGeneralError(null)
    setBusy(true)
    try {
      await api.post('/auth/register/', {
        email,
        password1: password,
        password2,
      })
      setRegistrationSent(true)
    } catch (err) {
      if (err.payload?.errors) setErrors(err.payload.errors)
      else setGeneralError(err.message || 'Error')
    } finally {
      setBusy(false)
    }
  }

  if (registrationSent) {
    return (
      <section className="max-w-md mx-auto py-12 text-white">
        <div className="bg-tq-ink-soft border border-white/10 rounded-lg p-6">
          <p className="text-[10px] uppercase tracking-widest text-white/60 mb-1">
            Compte
          </p>
          <h1 className="text-2xl font-bold mb-3">Correu enviat</h1>
          <p className="text-sm text-white/80 leading-relaxed">
            T'hem enviat un correu a <strong>{email}</strong> amb un enllaç
            d'activació. Obre'l per acabar de crear el compte.
          </p>
          <p className="text-xs text-white/60 mt-3">
            Si no el trobes en uns minuts, revisa la carpeta de brossa.
          </p>
          <button
            type="button"
            onClick={() => {
              setRegistrationSent(false)
              setMode('login')
              setPassword('')
              setPassword2('')
            }}
            className="mt-5 text-xs font-semibold px-3 py-1.5 rounded bg-tq-yellow text-tq-ink hover:bg-tq-yellow-deep hover:text-white"
          >
            Tornar a entrar
          </button>
        </div>
      </section>
    )
  }

  const isLogin = mode === 'login'

  return (
    <section className="max-w-md mx-auto py-12 text-white">
      <h1 className="text-3xl font-bold mb-4">
        {isLogin ? 'Accedir' : 'Crear compte'}
      </h1>

      <div
        className="flex rounded-lg overflow-hidden mb-4 border border-white/10"
        role="tablist"
      >
        <TabButton active={isLogin} onClick={() => switchMode('login')}>
          Entrar
        </TabButton>
        <TabButton active={!isLogin} onClick={() => switchMode('register')}>
          Crear compte
        </TabButton>
      </div>

      <form
        onSubmit={isLogin ? handleLogin : handleRegister}
        className="space-y-4 bg-white p-6 rounded-lg text-tq-ink"
      >
        <label className="block">
          <span className="text-sm font-semibold">Correu</span>
          <input
            type="email"
            autoComplete={isLogin ? 'email' : 'email'}
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
            className={inputClass}
          />
          {errors.email && (
            <p className="text-xs text-red-600 mt-1">{errors.email}</p>
          )}
        </label>

        <label className="block">
          <span className="text-sm font-semibold">
            {isLogin ? 'Contrasenya' : 'Contrasenya nova'}
          </span>
          <input
            type="password"
            autoComplete={isLogin ? 'current-password' : 'new-password'}
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            className={inputClass}
          />
          {errors.password1 && (
            <p className="text-xs text-red-600 mt-1">{errors.password1}</p>
          )}
        </label>

        {!isLogin && (
          <label className="block">
            <span className="text-sm font-semibold">Repeteix la contrasenya</span>
            <input
              type="password"
              autoComplete="new-password"
              value={password2}
              onChange={e => setPassword2(e.target.value)}
              required
              className={inputClass}
            />
            {errors.password2 && (
              <p className="text-xs text-red-600 mt-1">{errors.password2}</p>
            )}
          </label>
        )}

        {generalError && (
          <p className="text-sm text-red-700">{generalError}</p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full px-4 py-2 bg-tq-ink text-white font-semibold rounded-md disabled:opacity-50"
        >
          {busy
            ? isLogin ? 'Accedint…' : 'Enviant…'
            : isLogin ? 'Accedir' : 'Crear compte'}
        </button>

        {!isLogin && (
          <p className="text-[11px] text-gray-500 leading-relaxed">
            T'enviarem un correu amb un enllaç d'activació per verificar
            que el correu és teu. No podràs entrar fins que l'hagis
            confirmat.
          </p>
        )}
      </form>
    </section>
  )
}
