/**
 * OnboardingPage — /onboarding
 *
 * Guided post-registration flow. Users land here automatically after
 * the first session if `profile.onboarding_complet === false` (set by
 * the account-created signal). A single "Saltar" button marks the
 * flow complete without any further distinction — the same effect
 * as filling it — so there's no state mid-way.
 *
 * The form is the same `PerfilUsuari` surface users can come back to
 * from `/comunitat/perfil` later; on "Desar" we also flip
 * onboarding_complet=true and bounce them to /compte.
 */
import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import LocationCascade from '../components/staff/LocationCascade'

const inputClass =
  'mt-1 px-3 py-2 rounded-md bg-white/[0.07] text-white text-sm border border-white/15 placeholder-white/40 focus:outline-none focus:border-tq-yellow'

function Field({ label, hint, error, children }) {
  return (
    <label className="flex flex-col text-sm">
      <span className="text-xs font-semibold text-white/90">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-white/60 mt-0.5">{hint}</span>}
      {error && <span className="text-[11px] text-red-300 mt-0.5">{error}</span>}
    </label>
  )
}

export default function OnboardingPage() {
  const { profile, loading, refresh } = useAuth()
  const navigate = useNavigate()
  const [perfil, setPerfil] = useState(null)
  const [loc, setLoc] = useState({ territori: '', comarca: '', municipi_id: null, manual: '' })
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (loading || !profile) return
    api.get('/comunitat/perfil/').then(setPerfil).catch(() => {})
  }, [loading, profile])

  if (loading) return null
  if (!profile) return <Navigate to="/compte/accedir?next=/onboarding" replace />
  if (!perfil) return (
    <section className="max-w-2xl mx-auto py-12 text-white/70 text-sm">Carregant…</section>
  )

  function patch(p) { setPerfil(prev => ({ ...prev, ...p })) }
  function patchSocial(k, v) { setPerfil(prev => ({ ...prev, social: { ...prev.social, [k]: v } })) }

  async function saveAndContinue(onboardingDone) {
    setBusy(true)
    setErrors({})
    try {
      const body = {
        nom_public: perfil.nom_public || '',
        bio: perfil.bio || '',
        rol_musical: perfil.rol_musical || 'escoltador',
        instruments: perfil.instruments || '',
        visible_directori: !!perfil.visible_directori,
        obert_colaboracions: !!perfil.obert_colaboracions,
        imatge_url: perfil.imatge_url || '',
        localitat_pk: loc.municipi_id || perfil.localitat?.pk || null,
        onboarding_complet: onboardingDone,
        ...(perfil.social || {}),
      }
      await api.patch('/comunitat/perfil/', body)
      if (refresh) await refresh()
      navigate('/compte')
    } catch (err) {
      if (err.payload?.errors) setErrors(err.payload.errors)
    } finally {
      setBusy(false)
    }
  }

  async function saltar() {
    setBusy(true)
    try {
      await api.patch('/comunitat/perfil/', { onboarding_complet: true })
      if (refresh) await refresh()
      navigate('/compte')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="max-w-2xl mx-auto py-12 text-white">
      <p className="text-[10px] uppercase tracking-widest text-tq-yellow mb-2">
        Benvingut · TopQuaranta
      </p>
      <h1 className="text-3xl font-bold mb-2">Completa el teu perfil</h1>
      <p className="text-sm text-white/70 mb-4">
        Digues qui ets a la comunitat. Aquesta informació només apareix al{' '}
        <strong>directori intern</strong> si tu ho decideixes; pots canviar-ho
        en qualsevol moment des de <code>/compte</code>.
      </p>

      {/* Sprint H — què pots fer aquí, en tres punts. Discret, dins
          una targeta neutra perquè no competeixi amb el formulari. */}
      <div className="bg-white/5 border border-white/10 rounded-md p-4 mb-6 text-sm text-white/80">
        <p className="text-[10px] uppercase tracking-widest text-white/60 mb-2">
          Què pots fer com a usuari registrat
        </p>
        <ul className="space-y-1.5 leading-relaxed">
          <li className="flex gap-2">
            <span className="text-tq-yellow shrink-0">·</span>
            <span><strong>Proposar i gestionar artistes</strong> per fer-los
            aparèixer al top i al mapa.</span>
          </li>
          <li className="flex gap-2">
            <span className="text-tq-yellow shrink-0">·</span>
            <span><strong>Activar el teu perfil al directori</strong> per
            connectar amb altres músics dels Països Catalans.</span>
          </li>
          <li className="flex gap-2">
            <span className="text-tq-yellow shrink-0">·</span>
            <span><strong>Publicar a la comunitat</strong>: comparteix
            projectes, demana col·laboradors, anuncia novetats.</span>
          </li>
        </ul>
      </div>

      <form
        onSubmit={e => { e.preventDefault(); saveAndContinue(true) }}
        className="flex flex-col gap-4"
      >
        <Field label="Nom públic" error={errors.nom_public}>
          <input
            value={perfil.nom_public}
            onChange={e => patch({ nom_public: e.target.value })}
            className={inputClass}
            placeholder="Com vols aparèixer"
          />
        </Field>

        <Field label="Rol musical" error={errors.rol_musical}>
          <select
            value={perfil.rol_musical}
            onChange={e => patch({ rol_musical: e.target.value })}
            className={inputClass}
          >
            {(perfil.rol_choices || []).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </Field>

        <Field
          label="Instruments / àmbit"
          hint="Ex: guitarra, veu, producció electrònica, baixos…"
          error={errors.instruments}
        >
          <input
            value={perfil.instruments || ''}
            onChange={e => patch({ instruments: e.target.value })}
            className={inputClass}
          />
        </Field>

        <Field label="Localitat" error={errors.localitat_pk}>
          <div className="mt-1">
            <LocationCascade value={loc} onChange={setLoc} />
          </div>
        </Field>

        <Field label="Bio" hint="Breu descripció pública. Màxim 2 000 caràcters." error={errors.bio}>
          <textarea
            rows={4}
            value={perfil.bio || ''}
            onChange={e => patch({ bio: e.target.value })}
            className={inputClass + ' resize-y'}
          />
        </Field>

        <fieldset className="bg-white/5 rounded-md p-4">
          <legend className="text-xs font-semibold uppercase tracking-wide text-white/80 px-1">
            Visibilitat
          </legend>
          <label className="flex items-center gap-2 text-sm mb-2">
            <input
              type="checkbox"
              checked={!!perfil.visible_directori}
              onChange={e => patch({ visible_directori: e.target.checked })}
            />
            Vull aparèixer al <strong>directori intern</strong> (altres usuaris registrats).
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!perfil.obert_colaboracions}
              onChange={e => patch({ obert_colaboracions: e.target.checked })}
            />
            Estic obert a <strong>col·laboracions</strong>.
          </label>
        </fieldset>

        <fieldset className="bg-white/5 rounded-md p-4">
          <legend className="text-xs font-semibold uppercase tracking-wide text-white/80 px-1">
            Enllaços (opcionals)
          </legend>
          <div className="grid sm:grid-cols-2 gap-3">
            {(perfil.social_fields || []).map(([f, label]) => (
              <Field key={f} label={label} error={errors[f]}>
                <input
                  type="url"
                  value={perfil.social?.[f] || ''}
                  onChange={e => patchSocial(f, e.target.value)}
                  className={inputClass}
                  placeholder="https://…"
                />
              </Field>
            ))}
          </div>
        </fieldset>

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={busy}
            className="px-4 py-2 bg-tq-yellow text-tq-ink rounded-md font-semibold text-sm disabled:opacity-50"
          >
            {busy ? 'Desant…' : 'Desar i continuar'}
          </button>
          <button
            type="button"
            onClick={saltar}
            disabled={busy}
            className="px-4 py-2 border border-white/20 text-white rounded-md text-sm hover:bg-white/10"
          >
            Saltar
          </button>
        </div>
      </form>
    </section>
  )
}
