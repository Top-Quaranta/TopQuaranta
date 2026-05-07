/**
 * SolicitarGestioPage — /compte/artista/gestio
 *
 * Authenticated form. Lets a user request management of an existing
 * aprovat=True artist. The artist is picked via a live-search
 * typeahead that hits /api/v1/artistes/?q=… (already exists for the
 * public directory).
 */
import { useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import Alert from '../components/ui/Alert'
import { useAuth } from '../context/AuthContext'
import useApi from '../hooks/useApi'

const inputClass =
  'px-3 py-2 rounded-md bg-white text-tq-ink text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-tq-yellow'

function useDebounced(value, ms = 200) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function ArtistaSearch({ onPick, initialSlug }) {
  const [q, setQ] = useState('')
  const dq = useDebounced(q)
  const [open, setOpen] = useState(false)
  // useApi treats null path as no-op, so the <2-char gate falls
  // through naturally without a manual reset of results.
  const path = dq && dq.length >= 2
    ? `/artistes/?q=${encodeURIComponent(dq)}&per_page=8`
    : null
  const { data, loading } = useApi(path)
  const results = data?.results || []

  return (
    <div className="relative">
      <input
        value={q}
        onChange={e => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className={inputClass + ' w-full'}
        placeholder="Escriu el nom de l'artista…"
        autoFocus
      />
      {open && q.length >= 2 && (
        <ul className="absolute left-0 right-0 top-full mt-1 bg-white text-tq-ink rounded-md shadow-lg max-h-64 overflow-auto z-10 border border-black/10">
          {loading && <li className="px-3 py-2 text-xs text-gray-500">Cercant…</li>}
          {!loading && results.length === 0 && (
            <li className="px-3 py-2 text-xs text-gray-500">Sense resultats</li>
          )}
          {results.map(a => (
            <li key={a.slug}>
              <button
                type="button"
                onMouseDown={e => {
                  e.preventDefault()
                  onPick(a)
                  setQ(a.nom)
                  setOpen(false)
                }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-tq-yellow/10 flex items-center gap-2"
              >
                <span className="font-semibold">{a.nom}</span>
                {a.genere && <span className="text-xs text-gray-500">· {a.genere}</span>}
                {a.territoris?.length > 0 && (
                  <span className="ml-auto text-[10px] text-gray-400">{a.territoris.join(', ')}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function SolicitarGestioPage() {
  const { profile, loading } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const [picked, setPicked] = useState(null) // {slug, nom, ...}
  const [text, setText] = useState('')
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)

  // If the user comes from an /artista/<slug> page with ?artista=<slug>,
  // pre-fill by resolving the slug to its public artista payload.
  const prefillSlug = params.get('artista')
  useEffect(() => {
    if (!prefillSlug || picked) return
    api
      .get(`/artistes/${prefillSlug}/`)
      .then(a => setPicked({ slug: a.slug, nom: a.nom, genere: a.genere }))
      .catch(() => {})
  }, [prefillSlug, picked])

  if (loading) return null
  if (!profile) return <Navigate to="/compte/accedir" replace />

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    if (!picked) {
      setErrors({ artista_slug: 'Tria un artista.' })
      setBusy(false)
      return
    }
    try {
      await api.post('/compte/solicituds/', {
        artista_slug: picked.slug,
        sollicitud_text: text,
      })
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
      <h1 className="text-3xl font-bold mb-2">Sol·licitar gestió d'un artista</h1>
      <p className="text-sm text-white/70 mb-6">
        Si ets un artista que ja figura al sistema (o formes part del seu
        equip), pots demanar gestionar el seu perfil. L'equip TopQuaranta
        revisarà la sol·licitud.
      </p>

      {errors.__all__ && (
        <Alert tone="danger" className="mb-4">{errors.__all__}</Alert>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="flex flex-col">
          <label className="text-xs font-semibold text-white/90 mb-1">
            Artista *
          </label>
          {picked ? (
            <div className="flex items-center gap-2 p-2 bg-white text-tq-ink rounded-md">
              <span className="font-semibold">{picked.nom}</span>
              <button
                type="button"
                onClick={() => setPicked(null)}
                className="ml-auto text-xs text-red-600 hover:underline"
              >
                Canviar
              </button>
            </div>
          ) : (
            <ArtistaSearch onPick={setPicked} />
          )}
          {errors.artista_slug && (
            <span className="text-[11px] text-red-300 mt-1">{errors.artista_slug}</span>
          )}
        </div>

        <label className="flex flex-col text-sm">
          <span className="text-xs font-semibold text-white/90">
            Explica per què hauries de gestionar-lo *
          </span>
          <textarea
            required
            rows={6}
            value={text}
            onChange={e => setText(e.target.value)}
            className={inputClass + ' mt-1 resize-y'}
            placeholder="Sóc el mànager, el músic, treballo al segell… afegeix el detall que vulguis per acreditar la relació."
          />
          {errors.sollicitud_text && (
            <span className="text-[11px] text-red-300 mt-1">{errors.sollicitud_text}</span>
          )}
        </label>

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={busy || !picked}
            className="px-4 py-2 bg-tq-yellow text-tq-ink rounded-md font-semibold text-sm disabled:opacity-50"
          >
            {busy ? 'Enviant…' : 'Enviar sol·licitud'}
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
