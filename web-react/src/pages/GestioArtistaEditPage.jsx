/**
 * GestioArtistaEditPage — /compte/artista/:pk/editar
 *
 * Self-service editor for verified artist managers (UserArtista with
 * verificat=True). Lets them rewrite the non-critical fields on their
 * Artista without staff intervention. Critical fields (nom/slug,
 * Deezer IDs, localitats, aprovat state, MusicBrainz lockouts) stay
 * staff-only — those still need a `/compte/artista/gestio` request or
 * a "Corregir" feedback report.
 *
 * Backend: GET/PATCH /api/v1/compte/artista/<pk>/editar/. The endpoint
 * enforces the manager-verified check itself; we still bounce
 * unauthenticated visitors to /compte/accedir to avoid a flash of
 * 403 content.
 *
 * Save behaviour: PATCH sends only the user-edited fields, the
 * backend audit-logs only when something actually changed (so this
 * page is safe to call repeatedly). On success we re-hydrate state
 * from the response so future PATCHes diff against the canonical
 * server snapshot.
 */
import { useEffect, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import Alert from '../components/ui/Alert'
import { useAuth } from '../context/AuthContext'
import { artistaUrl } from '../lib/urls'

const inputClass =
  'w-full mt-1 px-3 py-2 rounded-md bg-white text-tq-ink text-sm border border-gray-300 ' +
  'focus:outline-none focus:ring-2 focus:ring-tq-yellow'

function FieldError({ msg }) {
  if (!msg) return null
  return <p className="text-xs text-red-600 mt-1">{msg}</p>
}

export default function GestioArtistaEditPage() {
  const { pk } = useParams()
  const { profile, loading: authLoading } = useAuth()

  const [data, setData] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [forbidden, setForbidden] = useState(false)
  const [loading, setLoading] = useState(true)

  // Local edits — diffed against `data` on submit so we PATCH only
  // the changed fields. Initialised to the server snapshot.
  const [edits, setEdits] = useState({})
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState({})
  const [saved, setSaved] = useState(null)

  useEffect(() => {
    if (authLoading || !profile) return
    setLoading(true)
    setLoadError(null)
    api.get(`/compte/artista/${pk}/editar/`)
      .then(d => {
        setData(d)
        setEdits({
          bio: d.bio,
          genere: d.genere,
          percentatge_femeni: d.percentatge_femeni,
          ...d.social,
        })
      })
      .catch(e => {
        if (e.status === 403) setForbidden(true)
        else setLoadError(e.message || 'Error')
      })
      .finally(() => setLoading(false))
  }, [authLoading, profile, pk])

  if (authLoading) return null
  if (!profile) return <Navigate to={`/compte/accedir?next=/compte/artista/${pk}/editar`} replace />

  if (loading) {
    return (
      <section className="max-w-3xl mx-auto py-10 space-y-3">
        <div className="h-8 bg-white/10 rounded w-1/2 animate-pulse" />
        <div className="h-48 bg-white/10 rounded animate-pulse" />
      </section>
    )
  }

  if (forbidden) {
    return (
      <section className="max-w-3xl mx-auto py-10 text-white">
        <Alert tone="danger">
          No ets gestor verificat d'aquest artista. Demana la gestió des
          de la seua pàgina pública o contacta amb staff.
        </Alert>
        <p className="mt-4">
          <Link to="/compte" className="text-tq-yellow underline">← Torna al teu compte</Link>
        </p>
      </section>
    )
  }

  if (loadError) {
    return (
      <section className="max-w-3xl mx-auto py-10 text-white">
        <Alert tone="danger">{loadError}</Alert>
      </section>
    )
  }

  if (!data) return null

  function set(field, value) {
    setEdits(s => ({ ...s, [field]: value }))
    setSaved(null)
  }

  function diff() {
    const out = {}
    for (const [k, v] of Object.entries(edits)) {
      const original = k in data ? data[k] : (data.social?.[k] ?? '')
      if ((v ?? '') !== (original ?? '')) out[k] = v
    }
    return out
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setErrors({})
    setSaved(null)
    const payload = diff()
    if (Object.keys(payload).length === 0) {
      setSaved({ tone: 'info', msg: 'Cap canvi per desar.' })
      return
    }
    setBusy(true)
    try {
      const res = await api.patch(`/compte/artista/${pk}/editar/`, payload)
      // Re-hydrate from canonical server snapshot so subsequent diffs
      // are stable and any normalisation (URL trimming etc.) is shown.
      setData(res)
      setEdits({
        bio: res.bio,
        genere: res.genere,
        percentatge_femeni: res.percentatge_femeni,
        ...res.social,
      })
      setSaved({
        tone: 'success',
        msg: res.canviats?.length
          ? `Desat. Camps actualitzats: ${res.canviats.join(', ')}.`
          : 'Sense canvis.',
      })
    } catch (err) {
      if (err.payload?.errors) setErrors(err.payload.errors)
      else setSaved({ tone: 'danger', msg: err.message || 'Error en desar.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="max-w-3xl mx-auto py-8 text-white space-y-6">
      <header>
        <p className="text-[10px] uppercase tracking-widest text-white/60">
          Gestió de l'artista
        </p>
        <h1 className="text-2xl font-bold font-display mt-1">{data.nom}</h1>
        <p className="text-sm text-white/70 mt-1">
          Pots editar la biografia, el gènere, la representació femenina
          i les xarxes socials. Per canviar el nom, els IDs Deezer o la
          localització, demana-ho a staff.
        </p>
        <p className="mt-2">
          <Link to={artistaUrl(data.slug)} className="text-tq-yellow underline text-sm">
            Veure la pàgina pública →
          </Link>
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-6">
        <fieldset className="bg-white text-tq-ink rounded-lg p-5 space-y-4">
          <legend className="font-semibold">Sobre l'artista</legend>

          <label className="block text-xs font-semibold">
            Biografia
            <textarea
              value={edits.bio || ''}
              onChange={e => set('bio', e.target.value)}
              rows={6}
              className={inputClass + ' font-normal'}
              placeholder="Una breu presentació de l'artista…"
            />
            <FieldError msg={errors.bio} />
          </label>

          <label className="block text-xs font-semibold">
            Gènere musical
            <input
              type="text"
              value={edits.genere || ''}
              onChange={e => set('genere', e.target.value)}
              className={inputClass + ' font-normal'}
              placeholder="ex. pop, indie, hip-hop…"
            />
            <FieldError msg={errors.genere} />
          </label>

          <label className="block text-xs font-semibold">
            Representació femenina
            <select
              value={edits.percentatge_femeni || ''}
              onChange={e => set('percentatge_femeni', e.target.value)}
              className={inputClass + ' font-normal'}
            >
              <option value="">—</option>
              {data.percentatge_choices.map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
            <FieldError msg={errors.percentatge_femeni} />
          </label>
        </fieldset>

        <fieldset className="bg-white text-tq-ink rounded-lg p-5">
          <legend className="font-semibold">Xarxes i enllaços</legend>
          <p className="text-xs text-gray-500 mt-1 mb-3">
            URLs completes (https://…). Deixa-ho buit per esborrar.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {data.social_fields.map(([field, label]) => (
              <label key={field} className="block text-xs font-semibold">
                {label}
                <input
                  type="url"
                  value={edits[field] || ''}
                  onChange={e => set(field, e.target.value)}
                  className={inputClass + ' font-normal'}
                  placeholder="https://…"
                />
                <FieldError msg={errors[field]} />
              </label>
            ))}
          </div>
        </fieldset>

        {saved && <Alert tone={saved.tone}>{saved.msg}</Alert>}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={busy}
            className="px-4 py-2 bg-tq-yellow text-tq-ink font-semibold rounded-md disabled:opacity-50"
          >
            {busy ? 'Desant…' : 'Desar canvis'}
          </button>
          <Link
            to="/compte"
            className="text-sm text-white/70 hover:text-white"
          >
            Cancel·lar
          </Link>
        </div>
      </form>
    </section>
  )
}
