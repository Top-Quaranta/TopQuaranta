/**
 * ArtistaEditPage — /staff/artistes/:pk
 *
 * Complex form: basic fields + social links + multiple locations +
 * multiple Deezer IDs. Saves via PATCH. Locations and Deezer IDs are
 * replace-semantics: we send the full list each time.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { Btn, Input, PageHeader, Pill, Select, TableCard } from '../../components/staff/StaffTable'
import LocationCascade from '../../components/staff/LocationCascade'
import MusicBrainzPanel from '../../components/staff/MusicBrainzPanel'
import LastfmPanel from '../../components/staff/LastfmPanel'


// Inline editor for Last.fm name aliases. Mirrors the Deezer-IDs
// list pattern: same artist, multiple identifiers, all summed into
// one signal. Candidates come from `manage.py detectar_lastfm_aliases`
// (top-tracks overlap ≥50%) and need staff confirmation before they
// start contributing to the playcount sum.
function LastfmAliasesInline({ pk, aliases, onChange }) {
  const [showAdd, setShowAdd] = useState(false)
  const [newNom, setNewNom] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function action(aliasPk, name) {
    setBusy(true); setErr('')
    try {
      await api.post(`/staff/artistes/${pk}/lastfm-aliases/${aliasPk}/`, { action: name })
      await onChange()
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  async function add() {
    if (!newNom.trim()) return
    setBusy(true); setErr('')
    try {
      await api.post(`/staff/artistes/${pk}/lastfm-aliases/`, { nom: newNom.trim() })
      setNewNom(''); setShowAdd(false)
      await onChange()
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  const visible = aliases.filter(a => !a.rebutjat)
  const rejected = aliases.filter(a => a.rebutjat)

  return (
    <div className="text-xs">
      <div className="flex items-center gap-2 mb-1 text-tq-ink/75 font-semibold">
        <span>Aliases Last.fm</span>
        <span className="opacity-80 font-normal">(es sumen al senyal quan estan confirmats)</span>
      </div>
      {visible.length === 0 && (
        <p className="italic text-tq-ink/75 mb-1">Cap variant detectada o afegida.</p>
      )}
      <ul>
        {visible.map(al => (
          <li key={al.pk} className="py-1 border-b border-tq-ink/5 last:border-0 flex items-center gap-2 flex-wrap">
            {al.confirmat
              ? <Pill tone="green">Confirmat</Pill>
              : <Pill tone="yellow">Candidat</Pill>}
            <code className="font-mono font-semibold">{al.nom}</code>
            {al.top_tracks_overlap != null && (
              <span className="text-tq-ink/75">
                {(al.top_tracks_overlap * 100).toFixed(0)}% top-tracks
                {al.playcount_variant != null && (
                  <> · {al.playcount_variant.toLocaleString('ca')} plays</>
                )}
              </span>
            )}
            <a
              href={`https://www.last.fm/music/${encodeURIComponent(al.nom)}`}
              target="_blank"
              rel="noopener"
              className="underline text-tq-ink/70 hover:text-tq-ink"
            >
              obrir ↗
            </a>
            <span className="ml-auto flex gap-1">
              {!al.confirmat && (
                <Btn tone="primary" disabled={busy} onClick={() => action(al.pk, 'confirm')}>
                  Confirmar
                </Btn>
              )}
              {!al.confirmat && (
                <Btn tone="secondary" disabled={busy} onClick={() => action(al.pk, 'reject')}>
                  Rebutjar
                </Btn>
              )}
              {al.confirmat && (
                <Btn tone="ghost" disabled={busy} onClick={() => action(al.pk, 'delete')}>
                  Esborrar
                </Btn>
              )}
            </span>
          </li>
        ))}
      </ul>
      {rejected.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer text-tq-ink/75 italic text-[11px]">
            {rejected.length} alies rebutjats (homònims)
          </summary>
          <ul className="mt-1">
            {rejected.map(al => (
              <li key={al.pk} className="py-0.5 flex gap-2 items-center text-tq-ink/75">
                <Pill tone="gray">Rebutjat</Pill>
                <code className="font-mono">{al.nom}</code>
                <Btn tone="ghost" disabled={busy} onClick={() => action(al.pk, 'delete')}>
                  Esborrar (re-proposable)
                </Btn>
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="mt-1">
        {!showAdd ? (
          <Btn tone="ghost" onClick={() => setShowAdd(true)}>+ Afegir alies manualment</Btn>
        ) : (
          <div className="flex gap-1 items-center flex-wrap">
            <input
              aria-label="Nom alies Last.fm"
              type="text"
              value={newNom}
              onChange={e => setNewNom(e.target.value)}
              placeholder="ex. Böira"
              className="text-sm px-2.5 py-1.5 rounded border border-tq-ink/20 bg-white text-tq-ink focus:outline-none focus:ring-2 focus:ring-tq-yellow"
            />
            <Btn tone="primary" disabled={busy || !newNom.trim()} onClick={add}>Afegir</Btn>
            <Btn tone="ghost" onClick={() => { setShowAdd(false); setNewNom(''); setErr('') }}>
              Cancel·lar
            </Btn>
          </div>
        )}
      </div>
      {err && <p className="text-[11px] text-red-700 mt-1">{err}</p>}
    </div>
  )
}

export default function ArtistaEditPage() {
  const { pk } = useParams()
  const navigate = useNavigate()
  const [a, setA] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.get(`/staff/artistes/${pk}/`).then(setA).catch(e => setErr(e.message))
  }, [pk])

  // Soft refresh — used by the inline aliases editor to refetch
  // after a confirm/reject without forcing a full page reload.
  async function reload() {
    try {
      const fresh = await api.get(`/staff/artistes/${pk}/`)
      setA(fresh)
    } catch (e) {
      setErr(e.message)
    }
  }

  if (err) return <p className="text-sm text-red-300">{err}</p>
  if (!a) return <p className="text-sm text-white/70">Carregant…</p>

  function patch(partial) {
    setA(prev => ({ ...prev, ...partial }))
  }

  function patchSocial(field, value) {
    setA(prev => ({ ...prev, social: { ...prev.social, [field]: value } }))
  }

  function addLoc() {
    setA(prev => ({
      ...prev,
      localitats: [
        ...(prev.localitats || []),
        { municipi_id: null, municipi_nom: '', comarca: '', territori: '', manual: '' },
      ],
    }))
  }

  function updateLoc(i, patch) {
    setA(prev => ({
      ...prev,
      localitats: prev.localitats.map((l, idx) => (idx === i ? { ...l, ...patch } : l)),
    }))
  }

  function removeLoc(i) {
    setA(prev => ({
      ...prev,
      localitats: prev.localitats.filter((_, idx) => idx !== i),
    }))
  }

  function setDeezerIds(ids) {
    setA(prev => ({ ...prev, deezer_ids: ids }))
  }

  async function clearMB() {
    const block = confirm(
      `Desvincular el MBID actual de ${a.nom}?\n\n` +
      `Per defecte el bloquejaré perquè el cron no el reassigni.\n` +
      `Prem "Cancel·lar" per avortar.`
    )
    if (!block) return
    const disableAuto = confirm(
      `Vols també DESACTIVAR l'auto-match per aquest artista?\n\n` +
      `OK: si no existeix cap MBID correcte a MusicBrainz, el cron no ` +
      `proposarà cap coincidència futura (ni per altres homònims).\n\n` +
      `Cancel·lar: només bloqueja el MBID actual; el cron podrà proposar ` +
      `altres MBIDs si apareixen.`
    )
    setBusy(true); setErr(''); setMsg('')
    try {
      const out = await api.post(`/staff/artistes/${pk}/mb-clear/`, {
        block: true,
        disable_auto: disableAuto,
      })
      if (out.ok) {
        setMsg(
          `MBID desvinculat.` +
          (out.blocked ? ` Bloquejat: ${out.old_mbid.slice(0, 8)}….` : '') +
          (out.auto_match_disabled ? ' Auto-match desactivat.' : '')
        )
        const fresh = await api.get(`/staff/artistes/${pk}/`)
        setA(fresh)
      }
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  async function syncMB() {
    setBusy(true); setErr(''); setMsg('')
    try {
      const out = await api.post(`/staff/artistes/${pk}/sync-mb/`)
      if (out.ok) {
        const c = out.counters || {}
        setMsg(
          `MB sync: URLs=${c.urls_filled || 0} àlbums=${c.albums_matched || 0}/${c.rgs || 0} ` +
          `cançons=${c.cancons_matched || 0}/${c.recordings || 0} ISRCs=${c.isrcs || 0}`
        )
        // Re-fetch to show the fresh MB fields.
        const fresh = await api.get(`/staff/artistes/${pk}/`)
        setA(fresh)
      } else {
        setErr(out.msg || 'Sync ha fallat.')
      }
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  async function save() {
    setBusy(true)
    setErr('')
    setMsg('')
    try {
      const body = {
        nom: a.nom,
        lastfm_nom: a.lastfm_nom,
        genere: a.genere,
        percentatge_femeni: a.percentatge_femeni,
        aprovat: a.aprovat,
        musicbrainz_id: a.musicbrainz?.id || '',
        localitats: a.localitats.map(l => ({
          municipi_id: l.municipi_id || null,
          manual: l.manual || '',
        })),
        deezer_ids: a.deezer_ids,
        ...a.social,
      }
      const out = await api.patch(`/staff/artistes/${pk}/`, body)
      setA(out)
      setMsg('Desat.')
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <PageHeader
        title={`Editar: ${a.nom}`}
        subtitle={
          <>
            <Link to={`/artista/${a.slug}`} className="underline">perfil públic</Link>
            {' · '}pk={a.pk}
          </>
        }
        right={
          <>
            <Btn tone="outline" size="md" onClick={() => navigate('/staff/artistes')}>Tornar</Btn>
            <Btn size="md" onClick={save} disabled={busy}>Desar</Btn>
          </>
        }
      />

      {err && <p className="text-sm text-red-300 mb-3">{err}</p>}
      {msg && <p className="text-sm text-emerald-300 mb-3">{msg}</p>}

      <div className="grid lg:grid-cols-2 gap-4">
        <TableCard className="p-4">
          <h2 className="font-semibold mb-3">Bàsics</h2>
          <div className="flex flex-col gap-2">
            <label className="text-xs font-semibold">Nom
              <Input value={a.nom} onChange={e => patch({ nom: e.target.value })} className="w-full mt-1 font-normal" />
            </label>
            <label className="text-xs font-semibold">Nom a Last.fm
              <Input value={a.lastfm_nom || ''} onChange={e => patch({ lastfm_nom: e.target.value })} className="w-full mt-1 font-normal" />
            </label>
            {/* Alias names — sum into the canonical signal once
                confirmed. Same pattern as deezer_ids, just per
                Last.fm. Surfaces detector candidates inline so the
                edit page is the single point of artist editing. */}
            <LastfmAliasesInline
              pk={a.pk}
              aliases={a.lastfm?.aliases || []}
              onChange={reload}
            />

            <label className="text-xs font-semibold">Gènere
              <Input value={a.genere || ''} onChange={e => patch({ genere: e.target.value })} className="w-full mt-1 font-normal" />
            </label>
            <label className="text-xs font-semibold">% femení
              <Select aria-label="Percentatge femení" value={a.percentatge_femeni || ''} onChange={e => patch({ percentatge_femeni: e.target.value })} className="w-full mt-1 font-normal">
                <option value="">—</option>
                {a.percentatge_choices.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </label>
            <label className="text-xs font-semibold flex items-center gap-2 mt-1">
              <input type="checkbox" checked={a.aprovat} onChange={e => patch({ aprovat: e.target.checked })} />
              Aprovat
            </label>
          </div>
        </TableCard>

        <TableCard className="p-4">
          <h2 className="font-semibold mb-3">Xarxes</h2>
          <div className="grid grid-cols-2 gap-2">
            {a.social_fields.map(([field, label]) => (
              <label key={field} className="text-xs font-semibold">
                {label}
                <Input
                  value={a.social?.[field] || ''}
                  onChange={e => patchSocial(field, e.target.value)}
                  className="w-full mt-1 font-normal"
                />
              </label>
            ))}
          </div>
        </TableCard>

        <TableCard className="p-4">
          <div className="flex justify-between items-center mb-3">
            <h2 className="font-semibold">Deezer IDs</h2>
            <Btn size="sm" onClick={() => setDeezerIds([...a.deezer_ids, ''])}>+ Afegir</Btn>
          </div>
          <div className="flex flex-col gap-2">
            {a.deezer_ids.map((id, i) => (
              <div key={i} className="flex gap-2">
                <Input
                  aria-label={`Deezer ID #${i + 1}`}
                  value={id}
                  onChange={e => setDeezerIds(a.deezer_ids.map((x, j) => j === i ? e.target.value : x))}
                  className="flex-1"
                  inputMode="numeric"
                />
                <Btn tone="danger" onClick={() => setDeezerIds(a.deezer_ids.filter((_, j) => j !== i))}>×</Btn>
              </div>
            ))}
            {a.deezer_ids.length === 0 && <p className="text-xs opacity-60">Cap Deezer ID.</p>}
          </div>
        </TableCard>

        <TableCard className="p-4">
          <div className="flex justify-between items-center mb-3">
            <h2 className="font-semibold">Localitats</h2>
            <Btn size="sm" onClick={addLoc}>+ Afegir</Btn>
          </div>
          <div className="flex flex-col gap-3">
            {a.localitats.map((l, i) => (
              <div key={i} className="flex gap-2 items-start">
                <div className="flex-1">
                  <LocationCascade
                    value={{
                      territori: l.territori || '',
                      comarca: l.comarca || '',
                      municipi_id: l.municipi_id || null,
                      municipi_nom: l.municipi_nom || '',
                      manual: l.manual || '',
                    }}
                    onChange={next => updateLoc(i, next)}
                  />
                </div>
                <Btn tone="danger" onClick={() => removeLoc(i)}>×</Btn>
              </div>
            ))}
            {a.localitats.length === 0 && <p className="text-xs opacity-60">Cap localitat.</p>}
            <p className="text-[11px] opacity-60 mt-1">
              Tria territori → comarca → municipi. Per a llocs fora dels
              Països Catalans escull "Altres" i escriu el nom de la
              localitat a mà.
            </p>
          </div>
        </TableCard>

        <div className="lg:col-span-2 grid lg:grid-cols-2 gap-4">
          <div className="flex flex-col gap-3">
            <div className="bg-white text-tq-ink rounded-lg border border-black/5 p-4">
              <h2 className="font-semibold mb-2 text-sm">MusicBrainz ID</h2>
              <Input
                value={a.musicbrainz?.id || ''}
                onChange={e => patch({ musicbrainz: { ...a.musicbrainz, id: e.target.value.trim() } })}
                placeholder="UUID (ex: 1068d2b9-596a-4fdf-9b87-b779b9f25dd3)"
                className="w-full font-mono text-[12px]"
              />
              <p className="text-[11px] text-tq-ink/75 mt-1">
                Si deixes el camp buit, el cron l'intentarà resoldre pel nom.
                Per artistes homònims (Crim, Apa…) cerca l'UUID correcte a
                musicbrainz.org i enganxa'l aquí. Desa i després prem
                "Sincronitzar ara".
              </p>
            </div>
          </div>
          <MusicBrainzPanel
            kind="artista"
            data={{ ...a.musicbrainz, nom_hint: a.nom }}
            onSync={syncMB}
            onClear={clearMB}
            busy={busy}
          />
          <LastfmPanel data={{ ...(a.lastfm || {}), pk: a.pk }} />
        </div>
      </div>
    </section>
  )
}
