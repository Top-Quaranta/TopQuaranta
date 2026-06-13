/**
 * ProposarArtistaPage — /compte/artista/proposta
 *
 * Authenticated form. Submits a PropostaArtista.
 *
 *   - nom (required)
 *   - justificacio (required)
 *   - deezer_ids (REQUIRED, ≥ 1) — without a Deezer ID no track of
 *     the artist can be verified, so the proposal can't reach the
 *     ranking. Enforced both server-side and client-side.
 *   - localitzacions (REQUIRED, ≥ 1) — cascade territori → comarca →
 *     municipi. When the user picks territori=ALT the cascade collapses
 *     into a free-text input for places outside the curated Municipi
 *     table, same UX as ArtistaEditPage.
 *   - social URLs (all optional, validated server-side).
 *
 * POSTs to /api/v1/compte/propostes/. On success, back to /compte.
 */
import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import Alert from '../components/ui/Alert'
import { useAuth } from '../context/AuthContext'
import LocationCascade from '../components/staff/LocationCascade'

const SOCIAL_FIELDS = [
  ['spotify_url',    'Spotify'],
  ['viasona_url',    'Viasona'],
  ['web_url',        'Web oficial'],
  ['bandcamp_url',   'Bandcamp'],
  ['youtube_url',    'YouTube'],
  ['viquipedia_url', 'Viquipèdia'],
  ['soundcloud_url', 'SoundCloud'],
  ['tiktok_url',     'TikTok'],
  ['facebook_url',   'Facebook'],
  ['instagram_url',  'Instagram'],
  ['twitter_url',    'X'],
]

function Field({ label, error, children, hint, required }) {
  return (
    <label className="flex flex-col text-sm">
      <span className="text-xs font-semibold text-white/90">
        {label}{required && <span className="text-tq-yellow"> *</span>}
      </span>
      {children}
      {hint && <span className="text-[11px] text-white/60 mt-0.5">{hint}</span>}
      {error && <span className="text-[11px] text-red-300 mt-0.5">{error}</span>}
    </label>
  )
}

const inputClass =
  'mt-1 px-3 py-2 rounded-md bg-white/[0.07] text-white text-sm border border-white/15 placeholder-white/40 focus:outline-none focus:border-tq-yellow'

const emptyLoc = () => ({
  territori: '',
  comarca: '',
  municipi_id: null,
  municipi_nom: '',
  manual: '',
})

export default function ProposarArtistaPage() {
  const { profile, loading } = useAuth()
  const navigate = useNavigate()

  const [nom, setNom] = useState('')
  const [justificacio, setJustificacio] = useState('')
  const [social, setSocial] = useState(Object.fromEntries(SOCIAL_FIELDS.map(([k]) => [k, ''])))
  const [deezerIds, setDeezerIds] = useState([''])
  const [locs, setLocs] = useState([emptyLoc()])
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)

  if (loading) return null
  if (!profile) return <Navigate to="/compte/accedir?next=/compte/artista/proposta" replace />

  function updateLoc(i, partial) {
    setLocs(locs.map((l, idx) => (idx === i ? { ...l, ...partial } : l)))
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    try {
      const payload = {
        nom,
        justificacio,
        ...social,
        deezer_ids: deezerIds.map(s => s.trim()).filter(Boolean),
        // LocationCascade emits either {municipi_id} for PPCC or
        // {manual} for territori=ALT; the backend accepts both shapes.
        localitzacions: locs
          .map(l => {
            if (l.municipi_id) return { municipi_id: l.municipi_id }
            if (l.territori === 'ALT' && l.manual) return { manual: l.manual }
            return null
          })
          .filter(Boolean),
      }
      await api.post('/compte/propostes/', payload)
      navigate('/compte')
    } catch (err) {
      if (err.payload?.errors) setErrors(err.payload.errors)
      else setErrors({ __all__: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="max-w-2xl mx-auto text-white">
      <h1 className="text-3xl font-bold mb-2">Proposar un artista nou</h1>
      <p className="text-sm text-white/70 mb-6">
        Omple el que sàpigues. L'equip TopQuaranta revisa cada proposta
        abans d'incorporar l'artista al sistema.
      </p>

      {errors.__all__ && (
        <Alert tone="danger" className="mb-4">{errors.__all__}</Alert>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Nom de l'artista" required error={errors.nom}>
          <input
            required
            value={nom}
            onChange={e => setNom(e.target.value)}
            className={inputClass}
            placeholder="p. ex. Sangtraït"
          />
        </Field>

        <Field
          label="Justificació"
          required
          error={errors.justificacio}
          hint="Per què cal afegir aquest artista? Quins àlbums, activitat recent, etc."
        >
          <textarea
            required
            value={justificacio}
            onChange={e => setJustificacio(e.target.value)}
            rows={5}
            className={inputClass + ' resize-y'}
          />
        </Field>

        <fieldset className="bg-white/5 rounded-md p-4">
          <legend className="text-xs font-semibold uppercase tracking-wide text-white/80 px-1">
            Deezer IDs <span className="text-tq-yellow">*</span>
          </legend>
          <p className="text-[11px] text-white/60 mb-2">
            <strong>Obligatori (almenys un).</strong> Sense un Deezer ID no
            podem verificar cap cançó de l'artista ni fer-la entrar al
            ranking. Els trobaràs a la URL del perfil de l'artista a Deezer,
            després de <code>/artist/</code>.
          </p>
          {deezerIds.map((v, i) => (
            <div key={i} className="flex gap-2 mb-2">
              <input
                value={v}
                inputMode="numeric"
                onChange={e =>
                  setDeezerIds(deezerIds.map((x, j) => (j === i ? e.target.value : x)))
                }
                className={inputClass + ' flex-1'}
                placeholder="p. ex. 12345"
                required={i === 0}
              />
              {deezerIds.length > 1 && (
                <button
                  type="button"
                  onClick={() => setDeezerIds(deezerIds.filter((_, j) => j !== i))}
                  className="px-2 text-sm text-red-300 hover:text-red-200"
                  aria-label="Eliminar"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            onClick={() => setDeezerIds([...deezerIds, ''])}
            className="text-xs font-semibold text-tq-yellow hover:underline"
          >
            + Afegir ID
          </button>
          {errors.deezer_ids && (
            <p className="text-[11px] text-red-300 mt-1">{errors.deezer_ids}</p>
          )}
        </fieldset>

        <fieldset className="bg-white/5 rounded-md p-4">
          <legend className="text-xs font-semibold uppercase tracking-wide text-white/80 px-1">
            Localitats <span className="text-tq-yellow">*</span>
          </legend>
          <p className="text-[11px] text-white/60 mb-2">
            <strong>Obligatori (almenys una).</strong> Tria territori → comarca
            → municipi. Per a artistes de fora dels Països Catalans, escull
            "Altres" i escriu el nom a mà.
          </p>
          <div className="flex flex-col gap-2">
            {locs.map((l, i) => (
              <div key={i} className="flex gap-2 items-start">
                <div className="flex-1">
                  <LocationCascade value={l} onChange={next => updateLoc(i, next)} />
                </div>
                {locs.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setLocs(locs.filter((_, j) => j !== i))}
                    className="px-2 text-sm text-red-300 hover:text-red-200"
                    aria-label="Eliminar"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setLocs([...locs, emptyLoc()])}
            className="text-xs font-semibold text-tq-yellow hover:underline mt-2"
          >
            + Afegir localitat
          </button>
          {errors.localitzacions && (
            <p className="text-[11px] text-red-300 mt-1">{errors.localitzacions}</p>
          )}
        </fieldset>

        <fieldset className="bg-white/5 rounded-md p-4">
          <legend className="text-xs font-semibold uppercase tracking-wide text-white/80 px-1">
            Enllaços (opcionals)
          </legend>
          <div className="grid sm:grid-cols-2 gap-3">
            {SOCIAL_FIELDS.map(([field, label]) => (
              <Field key={field} label={label} error={errors[field]}>
                <input
                  type="url"
                  value={social[field]}
                  onChange={e => setSocial({ ...social, [field]: e.target.value })}
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
            {busy ? 'Enviant…' : 'Enviar proposta'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/compte')}
            className="px-4 py-2 border border-white/20 text-white rounded-md text-sm hover:bg-white/10"
          >
            Cancel·lar
          </button>
        </div>
      </form>
    </section>
  )
}
