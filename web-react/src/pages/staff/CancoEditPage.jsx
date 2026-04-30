/**
 * CancoEditPage — /staff/cancons/:pk
 *
 * Simple edit form for a single track.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { Btn, Input, PageHeader, TableCard } from '../../components/staff/StaffTable'
import ArtistaPicker from '../../components/staff/ArtistaPicker'
import ArtistesColPicker from '../../components/staff/ArtistesColPicker'
import MusicBrainzPanel from '../../components/staff/MusicBrainzPanel'
import TopBreakdownPanel from '../../components/TopBreakdownPanel'

export default function CancoEditPage() {
  const { pk } = useParams()
  const navigate = useNavigate()
  const [c, setC] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get(`/staff/cancons/${pk}/`).then(setC).catch(e => setErr(e.message))
  }, [pk])

  if (err) return <p className="text-red-300">{err}</p>
  if (!c) return <p className="text-white/70">Carregant…</p>

  function patch(p) { setC(prev => ({ ...prev, ...p })) }

  async function refetchSenyal() {
    setBusy(true); setErr(''); setMsg('')
    try {
      const out = await api.post(`/staff/cancons/${pk}/refetch-senyal/`)
      if (out.ok) {
        setMsg(
          `Last.fm OK · ${out.playcount?.toLocaleString() || 0} plays · ` +
          `${out.listeners?.toLocaleString() || 0} listeners` +
          (out.drift ? ` (drift: artista="${out.returned_artist}", tema="${out.returned_track}")` : '')
        )
      } else {
        // Not an exception — Last.fm simply doesn't have this track.
        // Surface as a neutral notice instead of a red error.
        setMsg(
          'ℹ️ ' + (out.error || 'Last.fm no té aquesta cançó indexada.') +
          ' · És normal si ningú no l\'ha escoltada mai a Last.fm; ' +
          'el senyal seguirà sent zero fins que hi hagi scrobbles.'
        )
      }
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  async function save() {
    setBusy(true); setErr(''); setMsg('')
    try {
      const out = await api.patch(`/staff/cancons/${pk}/`, {
        nom: c.nom,
        isrc: c.isrc,
        lastfm_nom: c.lastfm_nom,
        verificada: c.verificada,
        activa: c.activa,
        data_llancament: c.data_llancament,
        deezer_id: c.deezer_id,
        artista_pk: c.artista?.pk,
        artistes_col_pks: (c.artistes_col || []).map(a => a.pk),
      })
      setC(out)
      setMsg('Desat.')
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  return (
    <section>
      <PageHeader
        title={`Editar cançó: ${c.nom}`}
        subtitle={<Link to={`/canco/${c.slug}`} className="underline">perfil públic</Link>}
        right={
          <>
            {c.deezer_id && (
              <a
                href={`https://www.deezer.com/track/${c.deezer_id}`}
                target="_blank"
                rel="noopener"
                className="text-sm font-semibold px-3 py-1.5 rounded bg-white/10 text-white hover:bg-white/20 transition-colors"
              >
                ▶ Escoltar a Deezer
              </a>
            )}
            <Btn tone="outline" size="md" onClick={() => navigate('/staff/cancons')}>Tornar</Btn>
            <Btn size="md" onClick={save} disabled={busy}>Desar</Btn>
          </>
        }
      />
      {err && <p className="text-red-300 mb-3">{err}</p>}
      {msg && <p className="text-emerald-300 mb-3">{msg}</p>}
      <TableCard className="p-4 max-w-2xl">
        <div className="grid gap-3">
          <label className="text-xs font-semibold">Nom
            <Input value={c.nom} onChange={e => patch({ nom: e.target.value })} className="w-full mt-1 font-normal" />
          </label>
          <div className="text-xs font-semibold">
            Artista
            <div className="mt-1 font-normal">
              <ArtistaPicker
                value={c.artista?.pk ? c.artista : null}
                onChange={next => patch({ artista: next })}
              />
            </div>
            <p className="mt-1 text-[11px] font-normal text-tq-ink/75">
              Si l'artista correcte no existeix, clica "+ Crear" per afegir-lo
              primer, després torna aquí i tria'l de la llista.
            </p>
          </div>
          <div className="text-xs font-semibold">
            Col·laboradors
            <div className="mt-1 font-normal">
              <ArtistesColPicker
                value={c.artistes_col || []}
                blockedPk={c.artista?.pk}
                onChange={next => patch({ artistes_col: next })}
              />
            </div>
          </div>
          {c.album && (
            <label className="text-xs font-semibold">Àlbum
              <div className="mt-1 font-normal text-sm">
                <Link className="underline" to={`/staff/albums/${c.album.pk}`}>{c.album.nom}</Link>
              </div>
            </label>
          )}
          <label className="text-xs font-semibold">ISRC
            <Input value={c.isrc || ''} onChange={e => patch({ isrc: e.target.value })} className="w-full mt-1 font-normal" />
          </label>
          <div className="text-xs font-semibold">
            Nom Last.fm
            <Input
              value={c.lastfm_nom || ''}
              onChange={e => patch({ lastfm_nom: e.target.value })}
              className="w-full mt-1 font-normal"
            />
            <p className="mt-1 text-[11px] font-normal text-tq-ink/75">
              Si Last.fm no troba la cançó, el pipeline queda bloquejat fins demà.
              Desa el canvi i prem "Reintentar Last.fm" per forçar la consulta ara.
              Recorda que també pot ser el <em>Nom a Last.fm</em> de l'artista el que falla.
            </p>
            <div className="mt-2">
              <Btn
                size="sm"
                tone="secondary"
                onClick={refetchSenyal}
                disabled={busy}
              >
                Reintentar Last.fm ara
              </Btn>
            </div>
          </div>
          <label className="text-xs font-semibold">Deezer ID
            <Input value={c.deezer_id || ''} inputMode="numeric" onChange={e => patch({ deezer_id: e.target.value })} className="w-full mt-1 font-normal" />
          </label>
          <label className="text-xs font-semibold">Data llançament
            <Input type="date" value={c.data_llancament || ''} onChange={e => patch({ data_llancament: e.target.value })} className="w-full mt-1 font-normal" />
          </label>
          <label className="text-xs font-semibold flex items-center gap-2">
            <input type="checkbox" checked={c.verificada} onChange={e => patch({ verificada: e.target.checked })} />
            Verificada
          </label>
          <label className="text-xs font-semibold flex items-center gap-2">
            <input type="checkbox" checked={c.activa} onChange={e => patch({ activa: e.target.checked })} />
            Activa
          </label>
        </div>
      </TableCard>

      <div className="mt-4 max-w-2xl">
        <MusicBrainzPanel kind="canco" data={c} />
      </div>

      <div className="mt-6">
        <TopBreakdownPanel slug={c.slug} />
      </div>
    </section>
  )
}
