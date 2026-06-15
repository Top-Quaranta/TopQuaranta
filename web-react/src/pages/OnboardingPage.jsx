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
import { useEffect, useRef, useState } from 'react'
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
  const pasFired = useRef(false)

  useEffect(() => {
    if (loading || !profile) return
    api.get('/comunitat/perfil/').then(setPerfil).catch(() => {})
  }, [loading, profile])

  // Slice E: funnel instrumentation. Fire "inici" once on mount.
  useEffect(() => {
    import('../lib/analytics').then(({ trackEvent }) => trackEvent('onboarding_inici'))
  }, [])

  if (loading) return null
  if (!profile) return <Navigate to="/compte/accedir?next=/onboarding" replace />
  if (!perfil) return (
    <section className="max-w-2xl mx-auto py-12 text-white/70 text-sm">Carregant…</section>
  )

  function fire(clau, dim1 = '') {
    import('../lib/analytics').then(({ trackEvent }) => trackEvent(clau, dim1))
  }
  function patch(p) {
    if (!pasFired.current) { pasFired.current = true; fire('onboarding_pas') }
    setPerfil(prev => ({ ...prev, ...p }))
  }
  function patchSocial(k, v) { setPerfil(prev => ({ ...prev, social: { ...prev.social, [k]: v } })) }

  // `busca` is a comma-joined token list; toggle one token on/off.
  function toggleBusca(token) {
    const set = new Set((perfil.busca || '').split(',').map(t => t.trim()).filter(Boolean))
    if (set.has(token)) set.delete(token)
    else set.add(token)
    patch({ busca: Array.from(set).join(',') })
  }
  const buscaSet = new Set((perfil.busca || '').split(',').map(t => t.trim()).filter(Boolean))

  async function saveAndContinue(onboardingDone) {
    setBusy(true)
    setErrors({})
    try {
      const body = {
        nom_public: perfil.nom_public || '',
        bio: perfil.bio || '',
        rol_musical: perfil.rol_musical || 'escoltador',
        instruments: perfil.instruments || '',
        busca: perfil.busca || '',
        generes: perfil.generes || '',
        nivell: perfil.nivell || '',
        visible_directori: !!perfil.visible_directori,
        obert_colaboracions: !!perfil.obert_colaboracions,
        imatge_url: perfil.imatge_url || '',
        localitat_pk: loc.municipi_id || perfil.localitat?.pk || null,
        onboarding_complet: onboardingDone,
        ...(perfil.social || {}),
      }
      await api.patch('/comunitat/perfil/', body)
      if (onboardingDone) fire('onboarding_complet')
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
      fire('onboarding_saltat')
      if (refresh) await refresh()
      navigate('/compte')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="max-w-2xl mx-auto py-12 text-white">
      <p className="text-[10px] uppercase tracking-widest text-tq-yellow mb-2">
        Comunitat · TopQuaranta
      </p>
      <h1 className="text-3xl font-bold mb-2">
        Busques grup o gent per fer música en català?
      </h1>
      <p className="text-sm text-white/70 mb-4">
        Digues que fas música i què busques: et trobaran altres músics dels
        Països Catalans. Pots canviar-ho en qualsevol moment des de{' '}
        <code>/compte</code>.
      </p>

      <div className="bg-white/5 border border-white/10 rounded-md p-4 mb-6 text-sm text-white/80">
        <p className="text-[10px] uppercase tracking-widest text-white/60 mb-2">
          La comunitat de músics en català
        </p>
        <ul className="space-y-1.5 leading-relaxed">
          <li className="flex gap-2">
            <span className="text-tq-yellow shrink-0">·</span>
            <span><strong>Troba grup o col·laboradors</strong>: cantants,
            instrumentistes, productors que fan música en català.</span>
          </li>
          <li className="flex gap-2">
            <span className="text-tq-yellow shrink-0">·</span>
            <span><strong>Fes-te trobadís al directori</strong> i filtra per
            instrument, gènere, territori i què busca cadascú.</span>
          </li>
          <li className="flex gap-2">
            <span className="text-tq-yellow shrink-0">·</span>
            <span><strong>Connecta i publica</strong>: missatges directes i
            anuncis a la comunitat.</span>
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

        <Field label="Nivell" hint="Tant si ja en vius com si tot just comences." error={errors.nivell}>
          <select
            value={perfil.nivell || ''}
            onChange={e => patch({ nivell: e.target.value })}
            className={inputClass}
          >
            <option value="">(sense especificar)</option>
            {(perfil.nivell_choices || []).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </Field>

        <Field label="Què busques?" hint="Tria'n les que vulguis.">
          <div className="mt-1 flex flex-wrap gap-2">
            {(perfil.busca_choices || []).map(([v, l]) => (
              <button
                type="button"
                key={v}
                onClick={() => toggleBusca(v)}
                className={
                  'px-3 py-1 rounded-full text-xs border ' +
                  (buscaSet.has(v)
                    ? 'bg-tq-yellow text-tq-ink border-tq-yellow font-semibold'
                    : 'bg-transparent text-white border-white/25 hover:bg-white/10')
                }
              >
                {l}
              </button>
            ))}
          </div>
        </Field>

        <Field
          label="Gèneres / estils"
          hint="Separa'ls per comes. Ex: rock, folk, electrònica."
          error={errors.generes}
        >
          <input
            value={perfil.generes || ''}
            onChange={e => patch({ generes: e.target.value })}
            className={inputClass}
            placeholder="rock, pop, folk…"
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
          <p className="text-[11px] text-white/60 mb-2">
            Si no et fas visible, ningú no et trobarà al directori. La teva
            informació no surt enlloc fins que ho actives (RGPD).
          </p>
          <label className="flex items-center gap-2 text-sm mb-2">
            <input
              type="checkbox"
              checked={!!perfil.visible_directori}
              onChange={e => patch({ visible_directori: e.target.checked })}
            />
            <span>Fes-me <strong>visible al directori</strong> perquè altres músics em trobin.</span>
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
