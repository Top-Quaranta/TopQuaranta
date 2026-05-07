/**
 * ComunitatDetailPage — /comunitat/:pk
 *
 * Single publication view. Author / staff see edit + delete buttons;
 * others see read-only. Reuses the server-side authorisation checks
 * (API returns 404 to unauthorised callers on unpublished rows).
 */
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import Alert from '../components/ui/Alert'
import { useAuth } from '../context/AuthContext'
import Markdown from '../components/Markdown'
import useApi from '../hooks/useApi'

function Comentaris({ pubPk, autorPostUsername }) {
  const { profile } = useAuth()
  const { data: items, error: loadErr, reload } = useApi(
    `/comunitat/publicacions/${pubPk}/comentaris/`,
  )
  const [cos, setCos] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function send(e) {
    e.preventDefault()
    if (!cos.trim()) return
    setBusy(true); setErr('')
    try {
      await api.post(`/comunitat/publicacions/${pubPk}/comentaris/`, { cos })
      setCos('')
      reload()
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  async function remove(id) {
    if (!confirm('Esborrar aquest comentari?')) return
    try {
      await api.delete(`/comunitat/comentaris/${id}/`)
      reload()
    } catch (e) { setErr(e.payload?.error || e.message) }
  }

  // Show fetch errors (load) alongside mutation errors (send/remove).
  const displayErr = err || loadErr

  return (
    <section className="mt-6">
      <h2 className="text-lg font-bold mb-3">
        Comentaris {items && `(${items.length})`}
      </h2>
      {displayErr && <p className="text-red-300 text-sm mb-3">{displayErr}</p>}
      {items?.length === 0 && (
        <p className="text-white/50 text-sm mb-3">Cap comentari encara.</p>
      )}
      <ul className="space-y-3 mb-4">
        {items?.map(c => {
          const canDelete = profile && (
            profile.is_staff ||
            profile.username === c.autor?.username ||
            profile.username === autorPostUsername
          )
          return (
            <li key={c.pk} className="bg-white text-tq-ink rounded-lg p-3 flex gap-3">
              {c.autor?.imatge_url ? (
                <img src={c.autor.imatge_url} alt="" className="w-9 h-9 rounded-full object-cover shrink-0" />
              ) : (
                <div className="w-9 h-9 rounded-full bg-tq-yellow/30 flex items-center justify-center text-tq-ink font-bold text-xs shrink-0">
                  {(c.autor?.nom_public || c.autor?.username || '?')[0].toUpperCase()}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold text-sm">
                    {c.autor?.nom_public || c.autor?.username || 'Anònim'}
                    {c.autor?.is_staff && <span className="ml-1 text-[10px] uppercase text-tq-yellow-deep">staff</span>}
                  </span>
                  <span className="text-[11px] text-tq-ink/50">
                    {new Date(c.created_at).toLocaleString('ca', { dateStyle: 'short', timeStyle: 'short' })}
                  </span>
                </div>
                <p className="text-sm whitespace-pre-wrap mt-0.5">{c.cos}</p>
                {canDelete && (
                  <button
                    type="button"
                    onClick={() => remove(c.pk)}
                    className="text-[11px] text-red-600 underline mt-1 hover:text-red-800"
                  >
                    Esborrar
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      {profile ? (
        <form onSubmit={send} className="flex flex-col gap-2">
          <textarea
            value={cos}
            onChange={e => setCos(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="Escriu un comentari…"
            className="px-3 py-2 rounded bg-white/5 border border-white/10 text-sm text-white resize-y"
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={busy || !cos.trim()}
              className="px-4 py-2 bg-tq-yellow text-tq-ink rounded font-semibold text-sm disabled:opacity-50"
            >
              Publicar comentari
            </button>
          </div>
        </form>
      ) : (
        <p className="text-sm text-white/60">
          <Link to="/compte/accedir" className="underline">Inicia sessió</Link> per comentar.
        </p>
      )}
    </section>
  )
}

function EstatBadge({ estat }) {
  const tone = {
    esborrany: 'bg-gray-300 text-gray-800',
    pendent:   'bg-yellow-200 text-yellow-900',
    publicat:  'bg-emerald-200 text-emerald-900',
    rebutjat:  'bg-red-200 text-red-900',
  }[estat] || 'bg-gray-300 text-gray-800'
  return (
    <span className={'text-[10px] uppercase tracking-wide font-semibold px-2 py-0.5 rounded-full ' + tone}>
      {estat}
    </span>
  )
}

export default function ComunitatDetailPage() {
  const { pk } = useParams()
  const { profile } = useAuth()
  const navigate = useNavigate()
  const { data: pub, error: err } = useApi(`/comunitat/publicacions/${pk}/`)

  if (err) {
    return (
      <section className="max-w-3xl mx-auto text-white">
        <p className="text-sm text-red-300">{err}</p>
      </section>
    )
  }
  if (!pub) return (
    <section className="max-w-3xl mx-auto py-6 text-white/70 text-sm">Carregant…</section>
  )

  const canEdit = profile?.is_staff || (profile?.username === pub.autor.username)

  async function remove() {
    if (!confirm('Esborrar aquesta publicació?')) return
    await api.delete(`/comunitat/publicacions/${pk}/`)
    navigate('/comunitat')
  }

  return (
    <article className="max-w-3xl mx-auto text-white">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-white/60">
            per {pub.autor.nom_public}
            {pub.autor.is_staff && ' · staff'}
          </p>
          <h1 className="text-3xl font-bold font-display mt-1">{pub.titol}</h1>
        </div>
        <div className="flex gap-1">
          {pub.visibilitat === 'publica' && (
            <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
              Pública
            </span>
          )}
          <EstatBadge estat={pub.estat} />
        </div>
      </div>
      {pub.publicat_at && (
        <p className="text-xs text-white/50 mb-4">Publicat {pub.publicat_at.slice(0, 10)}</p>
      )}

      <div className="bg-white text-tq-ink rounded-lg p-6">
        <Markdown>{pub.cos}</Markdown>
      </div>

      {pub.notes_staff && (
        <Alert tone="danger" className="mt-4"><strong>Nota del staff:</strong> {pub.notes_staff}</Alert>
      )}

      {canEdit && (
        <div className="flex gap-2 mt-5">
          <Link
            to={`/comunitat/${pub.pk}/editar`}
            className="px-3 py-1.5 bg-tq-yellow text-tq-ink rounded-md text-sm font-semibold"
          >
            Editar
          </Link>
          <button
            type="button"
            onClick={remove}
            className="px-3 py-1.5 border border-red-400 text-red-300 rounded-md text-sm hover:bg-red-400 hover:text-white"
          >
            Esborrar
          </button>
        </div>
      )}

      <Comentaris pubPk={pub.pk} autorPostUsername={pub.autor.username} />
    </article>
  )
}
