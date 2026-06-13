/**
 * ComptePerfilPage — edit profile.
 *
 * Single form that PATCHes /api/v1/compte/perfil/ with any subset of
 * email / username / password (password requires current_password).
 * Field-level errors come back as a `{ errors: {field: message} }`
 * payload on a 400; we render them under the matching input.
 */
import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import Alert from '../components/ui/Alert'
import { useAuth } from '../context/AuthContext'

export default function ComptePerfilPage() {
  const { profile, loading: authLoading, refresh } = useAuth()
  const navigate = useNavigate()
  const [initial, setInitial] = useState(null)
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [volNewsletter, setVolNewsletter] = useState(false)
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    if (authLoading || !profile) return
    api.get('/compte/perfil/').then(d => {
      setInitial(d)
      setEmail(d.email || '')
      setUsername(d.username || '')
      setVolNewsletter(!!d.vol_newsletter)
    })
  }, [authLoading, profile])

  if (authLoading) return null
  if (!profile) return <Navigate to="/compte/accedir" replace />
  if (!initial) return null

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrors({})
    setSuccess(false)

    if (newPassword && newPassword !== confirmPassword) {
      setErrors({ confirm_password: 'La confirmació no coincideix.' })
      return
    }

    const payload = {}
    if (email && email !== initial.email) payload.email = email
    if (username && username !== initial.username) payload.username = username
    if (newPassword) {
      payload.password = newPassword
      payload.current_password = currentPassword
    }
    if (volNewsletter !== !!initial.vol_newsletter) {
      payload.vol_newsletter = volNewsletter
    }
    if (Object.keys(payload).length === 0) {
      setSuccess(true)
      return
    }

    setBusy(true)
    try {
      await api.patch('/compte/perfil/', payload)
      await refresh()
      // K1 analytics: aggregate counter when a user opts INTO the
      // newsletter from the profile page (not at registration —
      // that's already counted via `registre_complet` dim1=newsletter).
      // Fire on the False→True transition only.
      if (payload.vol_newsletter === true && !initial.vol_newsletter) {
        const { trackEvent } = await import('../lib/analytics')
        trackEvent('newsletter_signup')
      }
      setSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      if (err.payload?.errors) setErrors(err.payload.errors)
      else setErrors({ __all__: err.message || 'Error desant' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="max-w-xl mx-auto text-white space-y-4">
      <header className="flex items-center gap-2">
        <Link to="/compte" className="text-tq-yellow text-sm hover:underline">← Compte</Link>
        <h1 className="text-2xl font-bold font-display ml-2">Editar perfil</h1>
      </header>

      <form onSubmit={handleSubmit} className="rd-glass p-5 space-y-4">
        <Field label="Correu electrònic" error={errors.email}>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full px-3 py-1.5 border border-white/15 bg-white/[0.07] text-white rounded-md text-sm"
            required
          />
        </Field>

        <Field label="Nom d'usuari" error={errors.username}>
          <input
            type="text"
            value={username}
            onChange={e => setUsername(e.target.value)}
            className="w-full px-3 py-1.5 border border-white/15 bg-white/[0.07] text-white rounded-md text-sm"
            required
          />
          <p className="text-xs text-white/55 mt-1">Visible al teu perfil públic quan gestiones un artista.</p>
        </Field>

        <div className="border-t border-white/10 pt-4 mt-2">
          <p className="text-sm font-semibold mb-2">Newsletter</p>
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={volNewsletter}
              onChange={e => setVolNewsletter(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-white/30 focus:ring-tq-yellow"
            />
            <span className="text-sm text-white">
              Vull rebre el resum setmanal del Top per correu electrònic.
              <span className="block text-xs text-white/55 mt-0.5">
                Cada dissabte enviem el Top de la setmana. Pots desactivar-ho aquí mateix
                en qualsevol moment.
              </span>
            </span>
          </label>
        </div>

        <div className="border-t border-white/10 pt-4 mt-2">
          <p className="text-sm font-semibold mb-2">Canviar contrasenya</p>
          <p className="text-xs text-white/55 mb-3">Deixa buit si no vols canviar-la.</p>

          <Field label="Contrasenya actual" error={errors.current_password}>
            <input
              type="password"
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
              className="w-full px-3 py-1.5 border border-white/15 bg-white/[0.07] text-white rounded-md text-sm"
              autoComplete="current-password"
            />
          </Field>
          <Field label="Nova contrasenya" error={errors.password}>
            <input
              type="password"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              className="w-full px-3 py-1.5 border border-white/15 bg-white/[0.07] text-white rounded-md text-sm"
              autoComplete="new-password"
            />
          </Field>
          <Field label="Confirmar nova contrasenya" error={errors.confirm_password}>
            <input
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              className="w-full px-3 py-1.5 border border-white/15 bg-white/[0.07] text-white rounded-md text-sm"
              autoComplete="new-password"
            />
          </Field>
        </div>

        {errors.__all__ && (
          <Alert tone="danger">{errors.__all__}</Alert>
        )}
        {success && (
          <Alert tone="success">Perfil actualitzat correctament.</Alert>
        )}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={busy}
            className="flex-1 px-4 py-2 bg-tq-ink text-white rounded-md font-semibold disabled:opacity-50"
          >
            {busy ? 'Desant…' : 'Desar canvis'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/compte')}
            className="px-4 py-2 border border-gray-300 text-gray-700 rounded-md font-semibold hover:bg-gray-100"
          >
            Cancel·lar
          </button>
        </div>
      </form>
    </section>
  )
}

function Field({ label, children, error }) {
  return (
    <label className="block mb-3">
      <span className="text-sm font-semibold text-tq-ink">{label}</span>
      <div className="mt-1">{children}</div>
      {error && <p className="text-xs text-red-700 mt-1">{error}</p>}
    </label>
  )
}
