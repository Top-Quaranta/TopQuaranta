/**
 * ArtistaCrearPage — /staff/artistes/crear
 *
 * Minimal creation form. After success redirects to the edit page so
 * the staff can flesh out locations, socials and extra Deezer IDs.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { Btn, Input, PageHeader, TableCard } from '../../components/rd/surface'

export default function ArtistaCrearPage() {
  const navigate = useNavigate()
  const [nom, setNom] = useState('')
  const [lastfmNom, setLastfmNom] = useState('')
  const [deezerId, setDeezerId] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setErr('')
    try {
      const out = await api.post('/staff/artistes/crear/', {
        nom,
        lastfm_nom: lastfmNom,
        deezer_id: deezerId,
      })
      navigate(`/staff/artistes/${out.pk}`)
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <PageHeader title="Nou artista" subtitle="Creació manual" />
      <TableCard className="p-4 max-w-lg">
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="text-xs font-semibold">
            Nom *
            <Input
              required
              value={nom}
              onChange={e => setNom(e.target.value)}
              className="w-full mt-1 font-normal"
            />
          </label>
          <label className="text-xs font-semibold">
            Nom a Last.fm
            <Input
              value={lastfmNom}
              onChange={e => setLastfmNom(e.target.value)}
              placeholder="(per defecte igual al nom)"
              className="w-full mt-1 font-normal"
            />
          </label>
          <label className="text-xs font-semibold">
            Deezer ID
            <Input
              value={deezerId}
              onChange={e => setDeezerId(e.target.value)}
              inputMode="numeric"
              placeholder="(opcional)"
              className="w-full mt-1 font-normal"
            />
          </label>
          {err && <p className="text-sm text-red-600">{err}</p>}
          <div className="flex gap-2 pt-2">
            <Btn type="submit" size="md" disabled={busy}>
              Crear
            </Btn>
            <Btn
              tone="secondary"
              size="md"
              onClick={() => navigate('/staff/artistes')}
            >
              Cancel·lar
            </Btn>
          </div>
        </form>
      </TableCard>
    </section>
  )
}
