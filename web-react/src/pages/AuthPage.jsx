/**
 * AuthPage — /compte/accedir (redisseny web).
 *
 * Pill toggle Accedir / Registra't, in a glass card on the dark shell.
 * All auth logic is conserved: signIn (+ onboarding redirect + ?next),
 * register (/auth/register/ with the unbundled RGPD consents), the
 * anti-enumeration confirmation screen, field + general errors.
 */
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { Band, Glow, Glass, Kicker, Crit } from '../components/rd/primitives'

export default function AuthPage() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const nextPath = params.get('next') || '/'

  const [mode, setMode] = useState(params.get('mode') === 'registre' ? 'register' : 'login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [acceptaTermes, setAcceptaTermes] = useState(false)
  const [edatMin, setEdatMin] = useState(false)
  const [volNewsletter, setVolNewsletter] = useState(false)
  const [errors, setErrors] = useState({})
  const [generalError, setGeneralError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [registrationSent, setRegistrationSent] = useState(false)

  function switchMode(next) {
    if (next === mode) return
    setMode(next); setErrors({}); setGeneralError(null)
  }

  async function handleLogin(e) {
    e.preventDefault(); setErrors({}); setGeneralError(null); setBusy(true)
    try {
      const me = await signIn(email, password)
      if (me && me.is_authenticated && !me.onboarding_complet) navigate('/onboarding')
      else navigate(nextPath || '/')
    } catch (err) {
      setGeneralError(err.message || 'Error')
    } finally { setBusy(false) }
  }

  async function handleRegister(e) {
    e.preventDefault(); setErrors({}); setGeneralError(null); setBusy(true)
    try {
      await api.post('/auth/register/', {
        email, password1: password, password2,
        accepta_termes: acceptaTermes, edat_min: edatMin, vol_newsletter: volNewsletter,
      })
      setRegistrationSent(true)
    } catch (err) {
      if (err.payload?.errors) setErrors(err.payload.errors)
      else setGeneralError(err.message || 'Error')
    } finally { setBusy(false) }
  }

  if (registrationSent) {
    return (
      <Band tone="top-hero" className="rd-auth-band">
        <Glow variant="a" />
        <Glass className="rd-auth-card" style={{ textAlign: 'left' }}>
          <Kicker color="var(--color-tq-yellow)">compte</Kicker>
          <Crit as="h1" className="rd-auth-title">CORREU ENVIAT</Crit>
          <p className="text-sm text-white/80 leading-relaxed mt-2">
            T'hem enviat un correu a <strong>{email}</strong> amb un enllaç
            d'activació. Obre'l per acabar de crear el compte.
          </p>
          <p className="text-xs text-white/55 mt-3">Si no el trobes en uns minuts, revisa la carpeta de brossa.</p>
          <button
            type="button"
            onClick={() => { setRegistrationSent(false); setMode('login'); setPassword(''); setPassword2('') }}
            className="rd-btn rd-btn--hot mt-5" style={{ fontSize: 13, padding: '9px 16px' }}
          >
            Tornar a entrar
          </button>
        </Glass>
      </Band>
    )
  }

  const isLogin = mode === 'login'

  return (
    <Band tone="top-hero" className="rd-auth-band">
      <Glow variant="a" />
      <Glass className="rd-auth-card">
        <Crit as="h1" className="rd-auth-title">{isLogin ? 'ACCEDIR' : 'CREAR COMPTE'}</Crit>

        <div className="rd-auth-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={isLogin} onClick={() => switchMode('login')}
            className={`rd-pill${isLogin ? ' rd-pill-on' : ''}`}
            style={isLogin ? { background: 'var(--color-tq-yellow)', color: '#0a0a0a' } : undefined}>Entrar</button>
          <button type="button" role="tab" aria-selected={!isLogin} onClick={() => switchMode('register')}
            className={`rd-pill${!isLogin ? ' rd-pill-on' : ''}`}
            style={!isLogin ? { background: 'var(--color-tq-yellow)', color: '#0a0a0a' } : undefined}>Crear compte</button>
        </div>

        <form onSubmit={isLogin ? handleLogin : handleRegister} className="flex flex-col gap-4 mt-4">
          <label className="rd-fld">
            <span>Correu</span>
            <input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required />
            {errors.email && <p className="rd-fld-err">{errors.email}</p>}
          </label>

          <label className="rd-fld">
            <span>{isLogin ? 'Contrasenya' : 'Contrasenya nova'}</span>
            <input type="password" autoComplete={isLogin ? 'current-password' : 'new-password'} value={password} onChange={e => setPassword(e.target.value)} required />
            {errors.password1 && <p className="rd-fld-err">{errors.password1}</p>}
          </label>

          {!isLogin && (
            <label className="rd-fld">
              <span>Repeteix la contrasenya</span>
              <input type="password" autoComplete="new-password" value={password2} onChange={e => setPassword2(e.target.value)} required />
              {errors.password2 && <p className="rd-fld-err">{errors.password2}</p>}
            </label>
          )}

          {!isLogin && (
            <div className="flex flex-col gap-2 pt-1">
              <label className="rd-consent">
                <input type="checkbox" checked={acceptaTermes} onChange={e => setAcceptaTermes(e.target.checked)} required />
                <span>Accepto els <a href="/legal/termes" target="_blank" rel="noopener" className="underline">termes d'ús</a> i la <a href="/legal/privacitat" target="_blank" rel="noopener" className="underline">política de privacitat</a>.</span>
              </label>
              {errors.accepta_termes && <p className="rd-fld-err">{errors.accepta_termes}</p>}
              <label className="rd-consent">
                <input type="checkbox" checked={edatMin} onChange={e => setEdatMin(e.target.checked)} required />
                <span>Tinc 14 anys o més.</span>
              </label>
              {errors.edat_min && <p className="rd-fld-err">{errors.edat_min}</p>}
              <label className="rd-consent">
                <input type="checkbox" checked={volNewsletter} onChange={e => setVolNewsletter(e.target.checked)} />
                <span><strong>Opcional</strong> — vull rebre el top setmanal per correu (encara no l'enviem; demanem el consentiment ara per quan comencem).</span>
              </label>
            </div>
          )}

          {generalError && <p className="rd-fld-err" style={{ fontSize: 14 }}>{generalError}</p>}

          <button type="submit" disabled={busy} className="rd-btn rd-btn--hot" style={{ justifyContent: 'center', marginTop: 4 }}>
            {busy ? (isLogin ? 'Accedint…' : 'Enviant…') : (isLogin ? 'Accedir' : 'Crear compte')}
          </button>

          {!isLogin && (
            <p className="text-[11px] text-white/55 leading-relaxed">
              T'enviarem un correu amb un enllaç d'activació per verificar que el
              correu és teu. No podràs entrar fins que l'hagis confirmat.
            </p>
          )}
        </form>
      </Glass>
    </Band>
  )
}
