/**
 * ComunitatPublicarPage — /comunitat/publicar  (+ /comunitat/:pk/editar)
 *
 * Author or staff: create / edit a publication. Visibility selector
 * decides the flow:
 *   - interna  → publishes directly to the registered-user feed.
 *   - publica  → goes to pendent until staff approves. Staff posting
 *                publica skips that (their own posts auto-publish).
 *
 * Body is plain markdown. We keep rendering client-side minimal — a
 * pre-wrap block for now so simple line-break authoring works. A real
 * markdown renderer is a nice-to-have follow-up.
 */
import { useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import ImageUploadButton from '../components/ImageUploadButton'
import useApi from '../hooks/useApi'

const inputClass =
  'mt-1 w-full px-3 py-2 rounded-md bg-white/[0.07] text-white text-sm border border-white/15 placeholder-white/40 focus:outline-none focus:border-tq-yellow'

export default function ComunitatPublicarPage() {
  const { profile, loading } = useAuth()
  const navigate = useNavigate()
  const { pk } = useParams()
  const isEdit = !!pk

  const [titol, setTitol] = useState('')
  const [cos, setCos] = useState('')
  const cosRef = useRef(null)

  function insertAtCursor(text) {
    const el = cosRef.current
    if (!el) { setCos(c => c + text); return }
    const start = el.selectionStart ?? cos.length
    const end = el.selectionEnd ?? cos.length
    const next = cos.slice(0, start) + text + cos.slice(end)
    setCos(next)
    // Move caret to after inserted text on next tick.
    setTimeout(() => {
      el.focus()
      const pos = start + text.length
      el.setSelectionRange(pos, pos)
    }, 0)
  }
  const [visibilitat, setVisibilitat] = useState('interna')
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)

  // Edit mode: load existing post into the form once the fetch
  // settles. On any error (typically 404 if the pk is bogus or the
  // user no longer has access) bounce back to the index.
  const { data: existingPub, error: pubErr } = useApi(
    pk ? `/comunitat/publicacions/${pk}/` : null,
  )
  useEffect(() => {
    if (pubErr) navigate('/comunitat')
  }, [pubErr, navigate])
  useEffect(() => {
    if (!existingPub) return
    setTitol(existingPub.titol)
    setCos(existingPub.cos)
    setVisibilitat(existingPub.visibilitat)
  }, [existingPub])

  if (loading) return null
  if (!profile) return <Navigate to="/compte/accedir?next=/comunitat/publicar" replace />

  async function submit(save_as) {
    setBusy(true)
    setErrors({})
    try {
      const body = { titol, cos, visibilitat, save_as }
      let out
      if (isEdit) {
        out = await api.patch(`/comunitat/publicacions/${pk}/`, body)
      } else {
        out = await api.post('/comunitat/publicacions/', body)
      }
      navigate(`/comunitat/${out.pk}`)
    } catch (err) {
      if (err.payload?.errors) setErrors(err.payload.errors)
    } finally {
      setBusy(false)
    }
  }

  // When staff publishes public directly, the preview hint explains that.
  const willNeedApproval =
    !profile.is_staff && visibilitat === 'publica'

  return (
    <section className="max-w-3xl mx-auto text-white">
      <h1 className="text-2xl font-bold mb-4">
        {isEdit ? 'Editar publicació' : 'Nova publicació'}
      </h1>

      <form
        onSubmit={e => { e.preventDefault(); submit('submit') }}
        className="flex flex-col gap-4"
      >
        <label className="flex flex-col text-sm">
          <span className="text-xs font-semibold text-white/90">Títol</span>
          <input
            required
            value={titol}
            onChange={e => setTitol(e.target.value)}
            maxLength={200}
            className={inputClass}
          />
          {errors.titol && <span className="text-[11px] text-red-300 mt-0.5">{errors.titol}</span>}
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-xs font-semibold text-white/90">
            Cos <span className="opacity-60 font-normal">(markdown: **negreta**, *cursiva*, # títols, - llistes, [text](url), ![](url-imatge))</span>
          </span>
          <textarea
            ref={cosRef}
            required
            rows={14}
            value={cos}
            onChange={e => setCos(e.target.value)}
            maxLength={20000}
            className={inputClass + ' resize-y font-mono text-[13px]'}
            placeholder="## El meu primer post&#10;&#10;Estem molt contents de fer aquest primer pas..."
          />
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <ImageUploadButton
              kind="publicacio"
              onUploaded={url => insertAtCursor(`\n\n![](${url})\n\n`)}
            />
            <span className="text-[11px] text-white/50">
              Màx 5 MB · JPEG/PNG/WebP · quota per usuari: 20 MB
            </span>
          </div>
          {errors.cos && <span className="text-[11px] text-red-300 mt-0.5">{errors.cos}</span>}
        </label>

        <fieldset className="bg-white/5 rounded-md p-4">
          <legend className="text-xs font-semibold uppercase tracking-wide text-white/80 px-1">
            Visibilitat
          </legend>
          <label className="flex items-start gap-2 text-sm mb-2">
            <input
              type="radio"
              name="vis"
              checked={visibilitat === 'interna'}
              onChange={() => setVisibilitat('interna')}
              className="mt-1"
            />
            <span>
              <strong>Interna</strong> — visible només a usuaris registrats.
              Es publica a l'instant.
            </span>
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="radio"
              name="vis"
              checked={visibilitat === 'publica'}
              onChange={() => setVisibilitat('publica')}
              className="mt-1"
            />
            <span>
              <strong>Pública</strong> — visible a tothom, també sense sessió.
              {willNeedApproval && (
                <em className="block text-[11px] opacity-70 mt-1">
                  Passa per revisió de l'equip abans de publicar-se.
                </em>
              )}
            </span>
          </label>
        </fieldset>

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={busy}
            className="px-4 py-2 bg-tq-yellow text-tq-ink rounded-md font-semibold text-sm disabled:opacity-50"
          >
            {busy ? 'Enviant…' : willNeedApproval ? 'Enviar per revisió' : 'Publicar'}
          </button>
          {!isEdit && (
            <button
              type="button"
              onClick={() => submit('draft')}
              disabled={busy}
              className="px-4 py-2 border border-white/20 text-white rounded-md text-sm hover:bg-white/10"
            >
              Desar com a esborrany
            </button>
          )}
          <button
            type="button"
            onClick={() => navigate('/comunitat')}
            className="px-4 py-2 border border-white/20 text-white rounded-md text-sm hover:bg-white/10"
          >
            Cancel·lar
          </button>
        </div>
      </form>
    </section>
  )
}
