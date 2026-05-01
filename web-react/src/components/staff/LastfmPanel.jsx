/**
 * LastfmPanel — read-only display of Last.fm artist metadata.
 *
 * Mirrors the layout pattern of `MusicBrainzPanel`. All fields come
 * from `Artista.lastfm_*` populated by the daily
 * `obtenir_metadata_lastfm` cron — there is no on-demand "sync now"
 * button (the artist is touched at most once a week by design, and a
 * staff member who needs fresh data can run the management command
 * with `--artista-id`).
 *
 * Bio HTML is embedded raw via `dangerouslySetInnerHTML`. Last.fm
 * already strips dangerous tags on its end and the field is only
 * visible to staff, so the risk surface is minimal.
 */
import { useState } from 'react'

import { api } from '../../lib/api'
import { Btn, Pill } from './StaffTable'

function Row({ label, value }) {
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
    return null
  }
  const rendered = Array.isArray(value) ? value.join(', ') : value
  return (
    <div className="flex gap-3 text-sm border-b border-tq-ink/5 py-1.5 last:border-0">
      <span className="w-36 text-[11px] uppercase tracking-wide text-tq-ink/75 shrink-0">
        {label}
      </span>
      <span className="min-w-0 break-words">{rendered}</span>
    </div>
  )
}

function formatSync(iso) {
  if (!iso) return 'mai sincronitzat'
  const d = new Date(iso)
  return d.toLocaleString('ca', { dateStyle: 'short', timeStyle: 'short' })
}

function formatNum(n) {
  if (n == null) return null
  return Number(n).toLocaleString('ca')
}

export default function LastfmPanel({ data }) {
  const hasAnything =
    data?.url || data?.bio_summary || data?.listeners != null || data?.image_large

  return (
    <div className="bg-white text-tq-ink rounded-lg border border-black/5 p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="font-semibold text-sm">Last.fm</h2>
        {data?.url && (
          <a
            href={data.url}
            target="_blank"
            rel="noopener"
            className="text-[11px] underline text-tq-ink/70 hover:text-tq-ink"
          >
            obrir a Last.fm ↗
          </a>
        )}
      </div>

      {data?.auto_match_disabled && (
        <p
          className="text-xs italic mb-2 p-2 rounded"
          style={{ background: 'rgba(239, 68, 68, 0.10)', color: 'var(--color-tq-danger)' }}
        >
          Auto-sync Last.fm <strong>desactivat</strong> per a aquest artista
          (col·lisió de nom amb un homònim). El cron mai el tocarà fins
          que un membre de l'staff aixequi el lockout.
        </p>
      )}

      {!hasAnything && !data?.auto_match_disabled && (
        <p className="text-xs text-tq-ink/75 italic mb-2">
          Aquest artista encara no s'ha sincronitzat amb Last.fm. El cron
          (05:00 UTC) l'agafarà segons la cua de prioritat. Per forçar-ho
          ara, executa{' '}
          <code className="bg-tq-ink/5 px-1 rounded">
            ./manage.py obtenir_metadata_lastfm --artista-id {data?.pk || '<pk>'}
          </code>.
        </p>
      )}

      {data?.image_large && (
        <img
          src={data.image_extralarge || data.image_large}
          alt=""
          className="w-32 h-32 object-cover rounded-md float-right ml-3 mb-3"
        />
      )}

      <Row label="Listeners" value={formatNum(data?.listeners)} />
      <Row label="Playcount total" value={formatNum(data?.playcount_total)} />
      <Row
        label="En gira"
        value={
          data?.ontour === true
            ? <Pill tone="green">Sí</Pill>
            : data?.ontour === false
              ? <Pill tone="gray">No</Pill>
              : null
        }
      />
      <Row
        label="Tags"
        value={(data?.tags || []).slice(0, 8).map(t => t.name).filter(Boolean)}
      />
      <Row
        label="Similars (rep.)"
        value={data?.nb_similars > 0 ? data.nb_similars : null}
      />
      <Row label="Última sync" value={formatSync(data?.last_sync)} />

      <AliasesSection pk={data?.pk} aliases={data?.aliases || []} />

      {data?.bio_summary && (
        <details className="mt-3 text-xs text-tq-ink/80">
          <summary className="cursor-pointer font-semibold text-tq-ink/75 uppercase tracking-wide text-[11px]">
            Bio (resum)
          </summary>
          <div
            className="mt-2 prose prose-sm max-w-none"
            dangerouslySetInnerHTML={{ __html: data.bio_summary }}
          />
          {data.bio_content && data.bio_content !== data.bio_summary && (
            <details className="mt-2">
              <summary className="cursor-pointer font-semibold text-tq-ink/75 text-[11px]">
                veure bio sencera
              </summary>
              <div
                className="mt-2 prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: data.bio_content }}
              />
            </details>
          )}
          {data.bio_published && (
            <p className="text-[10px] opacity-50 mt-2">
              Publicat: {new Date(data.bio_published).toLocaleDateString('ca')}
            </p>
          )}
        </details>
      )}
    </div>
  )
}

// ── Last.fm aliases (variants) ───────────────────────────────────────
//
// Last.fm pages are name-keyed: the same artist scrobbled with two
// different spellings (e.g. 'Boira' / 'Böira') ends up on two pages
// with separate playcounts. We sum across confirmed aliases when the
// signal is collected. Candidates come from
// `manage.py detectar_lastfm_aliases` (top-tracks overlap >= 50 %)
// — staff confirms or rejects each one before it contributes.

function AliasRow({ pk, alias, onChange }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function action(name) {
    setBusy(true)
    setErr('')
    try {
      await api.post(`/staff/artistes/${pk}/lastfm-aliases/${alias.pk}/`, {
        action: name,
      })
      await onChange()
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally {
      setBusy(false)
    }
  }

  let stateLabel, stateTone
  if (alias.confirmat) {
    stateLabel = 'Confirmat'
    stateTone = 'green'
  } else if (alias.rebutjat) {
    stateLabel = 'Rebutjat'
    stateTone = 'gray'
  } else {
    stateLabel = 'Candidat'
    stateTone = 'yellow'
  }

  const overlap = alias.top_tracks_overlap != null
    ? `${(alias.top_tracks_overlap * 100).toFixed(0)} % top-tracks coincideixen`
    : null
  const pcCanon = alias.playcount_canonical
  const pcVar = alias.playcount_variant
  const pcRatio = pcCanon && pcVar ? `${pcVar.toLocaleString('ca')} vs ${pcCanon.toLocaleString('ca')} (canòn.)` : null

  return (
    <li className="py-2 border-b border-tq-ink/5 last:border-0">
      <div className="flex items-center gap-2 flex-wrap">
        <Pill tone={stateTone}>{stateLabel}</Pill>
        <code className="font-mono text-sm font-semibold">{alias.nom}</code>
        <a
          href={`https://www.last.fm/music/${encodeURIComponent(alias.nom)}`}
          target="_blank"
          rel="noopener"
          className="text-[11px] underline text-tq-ink/70 hover:text-tq-ink"
        >
          obrir ↗
        </a>
        <span className="ml-auto flex gap-1">
          {!alias.confirmat && (
            <Btn tone="primary" disabled={busy} onClick={() => action('confirm')}>
              Confirmar
            </Btn>
          )}
          {!alias.rebutjat && !alias.confirmat && (
            <Btn tone="secondary" disabled={busy} onClick={() => action('reject')}>
              Rebutjar
            </Btn>
          )}
          {(alias.confirmat || alias.rebutjat) && (
            <Btn tone="ghost" disabled={busy} onClick={() => action('delete')}>
              Esborrar
            </Btn>
          )}
        </span>
      </div>
      <p className="text-[11px] text-tq-ink/75 mt-1 ml-7">
        {[overlap, pcRatio].filter(Boolean).join(' · ') || ' '}
      </p>
      {err && <p className="text-[11px] text-red-700 ml-7">{err}</p>}
    </li>
  )
}

function AliasesSection({ pk, aliases }) {
  const [showAdd, setShowAdd] = useState(false)
  const [newNom, setNewNom] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  // Re-fetch hook: parent will reload via location, but for snappier UX
  // we accept a stub `onChange` that triggers a SWR-style soft refresh
  // — we just mutate the alias list optimistically by reloading the page.
  async function refresh() {
    // Cheapest possible refresh: trigger a full page reload of the
    // edit view. Could be improved by hoisting alias state up; left
    // as TODO for a future polish.
    window.location.reload()
  }

  async function add() {
    if (!newNom.trim()) return
    setBusy(true)
    setErr('')
    try {
      await api.post(`/staff/artistes/${pk}/lastfm-aliases/`, { nom: newNom.trim() })
      setNewNom('')
      setShowAdd(false)
      await refresh()
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally {
      setBusy(false)
    }
  }

  const pendents = aliases.filter(a => !a.confirmat && !a.rebutjat).length
  const confirmats = aliases.filter(a => a.confirmat).length

  return (
    <details className="mt-4 border-t border-tq-ink/10 pt-3" open={pendents > 0}>
      <summary className="cursor-pointer font-semibold text-tq-ink/75 uppercase tracking-wide text-[11px] flex items-center gap-2">
        Aliases Last.fm
        {pendents > 0 && <Pill tone="yellow">{pendents} a revisar</Pill>}
        {confirmats > 0 && <Pill tone="green">{confirmats} actius</Pill>}
      </summary>
      <p className="text-[11px] text-tq-ink/75 mt-2">
        Variants ortogràfiques de l'artista a Last.fm. Quan en confirmis
        una, el cron de senyal sumarà els seus playcounts a la pàgina
        canònica. Els candidats venen del detector automàtic
        (<code>detectar_lastfm_aliases</code>) que valida coincidència de
        top-tracks per evitar homònims.
      </p>
      {aliases.length === 0 && (
        <p className="text-[11px] italic text-tq-ink/75 mt-2">
          Cap variant detectada o afegida.
        </p>
      )}
      <ul className="mt-2">
        {aliases.map(a => (
          <AliasRow key={a.pk} pk={pk} alias={a} onChange={refresh} />
        ))}
      </ul>
      <div className="mt-3">
        {!showAdd ? (
          <Btn tone="ghost" onClick={() => setShowAdd(true)}>
            + Afegir alies manualment
          </Btn>
        ) : (
          <div className="flex gap-2 items-center flex-wrap">
            <input
              aria-label="Nom alies Last.fm"
              type="text"
              value={newNom}
              onChange={e => setNewNom(e.target.value)}
              placeholder="ex. Böira"
              className="text-sm px-2.5 py-1.5 rounded border border-tq-ink/20 bg-white text-tq-ink focus:outline-none focus:ring-2 focus:ring-tq-yellow"
            />
            <Btn tone="primary" disabled={busy || !newNom.trim()} onClick={add}>
              Afegir
            </Btn>
            <Btn tone="ghost" onClick={() => { setShowAdd(false); setNewNom(''); setErr('') }}>
              Cancel·lar
            </Btn>
            {err && <span className="text-[11px] text-red-700">{err}</span>}
          </div>
        )}
      </div>
    </details>
  )
}
