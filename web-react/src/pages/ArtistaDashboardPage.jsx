/**
 * ArtistaDashboardPage — /compte/artista/:slug/
 *
 * Sprint Portal Artista Ampliat (2026-05-20). Single page with three
 * hash-routed tabs:
 *
 *   #estat   (default) — qualitat dashboard: 9 indicators + score.
 *   #editar  — extended editor: text fields, image, Deezer IDs,
 *              Last.fm aliases, localitats.
 *   #cancons — unverified tracks + "demanar revisió" ping (7d cooldown).
 *
 * Permission: every endpoint runs `_gestor_check` server-side. We
 * still bounce unauthenticated visitors to /compte/accedir to avoid
 * a flash of 403 content; non-managers see a friendly explainer
 * after the first GET 403s.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'

import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { artistaUrl } from '../lib/urls'
import { Badge, Card, ConfirmDialog, Tabs } from '../components/ui'
import Alert from '../components/ui/Alert'

const TABS = [
  { key: 'estat', label: 'Estat' },
  { key: 'editar', label: 'Editar' },
  { key: 'cancons', label: 'Cançons' },
]

const SEVERITY_TONE = { success: 'success', warning: 'warning', danger: 'danger' }

// Educational microcopy attached to indicators whose state depends on
// an asynchronous backend pipeline. Keys match `indicator.key` from
// `/qualitat/`. Shown beneath `indicator.message` in italic gray so it
// reads as a hint, not as the actual error.
const INDICATOR_HELP = {
  perfil_intern: (
    <>
      <strong>Sobre el gènere:</strong> tu omples el camp lliure
      «Gènere musical» a la pestanya Editar; un classificador intern
      el normalitza diàriament a una forma canònica
      («pop-rock»&nbsp;→&nbsp;«pop», per exemple). Aquest indicador
      considera complet el camp <em>només quan el classificador ha
      executat</em>, així que pots veure'l en groc fins al següent
      cicle (≤24&nbsp;h).
    </>
  ),
  mb_cancons_mapejades: (
    <>
      <strong>Procés asíncron:</strong> el sync de MusicBrainz s'executa
      cada 15&nbsp;min i emparella cançons via ISRC o títol fuzzy.
      Una cançó nova pot trigar fins a una hora a aparèixer mapejada.
    </>
  ),
  lastfm_senyal: (
    <>
      <strong>Procés asíncron:</strong> el senyal Last.fm es recull a
      diari. Una cançó tot just verificada apareixerà sense senyal
      fins a la nit següent.
    </>
  ),
}

// ───────────────────────── shared helpers ────────────────────────


function useArtista(slug) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    return api
      .get(`/compte/artista/${slug}/editar/`)
      .then(d => {
        setData(d)
        return d
      })
      .catch(e => {
        setError(e)
        throw e
      })
      .finally(() => setLoading(false))
  }, [slug])

  useEffect(() => {
    // reload() flips setLoading(true) synchronously; that's intended
    // (we DO want a loading skeleton before the API resolves), and
    // it's the same pattern used across the SPA's data-fetching pages.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload().catch(() => {})
  }, [reload])

  return { data, setData, error, loading, reload }
}


// ───────────────────────── Tab: Estat ────────────────────────────


function IndicatorRow({ ind, onCta }) {
  return (
    <Card>
      <div className="p-4 flex items-start gap-3">
        <Badge variant={SEVERITY_TONE[ind.severity] || 'default'}>
          {ind.severity === 'success'
            ? '✓'
            : ind.severity === 'warning'
            ? '!'
            : '✕'}
        </Badge>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm">{ind.label}</p>
          <p className="text-sm text-tq-ink/70 mt-0.5">{ind.message}</p>
          {INDICATOR_HELP[ind.key] && (
            <p className="text-xs text-tq-ink/50 mt-1 italic">
              {INDICATOR_HELP[ind.key]}
            </p>
          )}
          {ind.cta && (
            <button
              type="button"
              onClick={() => onCta(ind.cta.href)}
              className="text-xs font-semibold text-tq-yellow-deep mt-2 hover:underline"
            >
              {ind.cta.label} →
            </button>
          )}
        </div>
      </div>
    </Card>
  )
}

const ESTAT_TONE_SR = { pendent: 'warning', revisada: 'default', resolta: 'success' }
const ESTAT_LABEL_SR = {
  pendent: 'Pendent',
  revisada: 'En revisió',
  resolta: 'Resolta',
}

function SollicitudResumCard({ slug, refreshKey }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    api
      .get(`/compte/artista/${slug}/sollicituds/`)
      .then(setData)
      .catch(() => setData(null))
  }, [slug, refreshKey])

  if (!data?.ultima) return null
  const u = data.ultima
  const fmt = iso => {
    if (!iso) return ''
    const d = new Date(iso)
    return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`
  }
  return (
    <Card>
      <div className="p-4 space-y-2">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-semibold">Última sol·licitud de revisió:</span>
          <span>{fmt(u.created_at)}</span>
          <Badge variant={ESTAT_TONE_SR[u.estat] || 'default'}>
            {ESTAT_LABEL_SR[u.estat] || u.estat}
          </Badge>
        </div>
        <p className="text-xs text-tq-ink/70">
          {u.n_pendents} pendent{u.n_pendents === 1 ? '' : 's'} +{' '}
          {u.n_rebutjades} rebutjada{u.n_rebutjades === 1 ? '' : 's'}
          {data.n_total > 1 && ` · ${data.n_total} sol·licituds en total`}
        </p>
        {u.estat === 'resolta' && (
          <div className="text-xs text-tq-ink/70">
            Resolta el {fmt(u.resolt_at)}.
            {u.nota_resolucio && (
              <span className="block mt-1 italic text-tq-ink/80">
                «{u.nota_resolucio}»
              </span>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

function EstatTab({ slug, onSwitchTab, sollicitudRefreshKey }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // Local memory only (per spec) — collapsed by default for the
  // success block. Resets on tab unmount, which is fine: the user's
  // attention should land on the alerts each time they open the tab.
  const [showSuccess, setShowSuccess] = useState(false)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true)
    api
      .get(`/compte/artista/${slug}/qualitat/`)
      .then(setData)
      .catch(e => setError(e.message || 'Error'))
      .finally(() => setLoading(false))
  }, [slug])

  if (loading) {
    return (
      <div className="space-y-3 mt-6">
        <div className="h-20 bg-white/10 rounded animate-pulse" />
        <div className="h-16 bg-white/10 rounded animate-pulse" />
      </div>
    )
  }
  if (error) return <Alert tone="danger">{error}</Alert>
  if (!data) return null

  const { score, n_alerts, indicators } = data
  const success = indicators.filter(i => i.severity === 'success')
  const issues = indicators.filter(i => i.severity !== 'success')
  // Show the collapsible "N indicadors superats" footer only when
  // there's a mix of states — pure-green or pure-red lists render
  // everything inline.
  const showCollapsible = success.length > 0 && issues.length > 0

  function handleCta(href) {
    if (!href) return
    if (href.startsWith('#')) {
      window.history.replaceState(null, '', href)
      onSwitchTab?.('editar', href)
    } else {
      window.open(href, '_blank', 'noopener noreferrer')
    }
  }

  return (
    <div className="space-y-4 mt-6">
      <Card accent={score === 100 ? 'green' : score >= 60 ? 'yellow' : 'red'}>
        <div className="p-5 flex items-center gap-5">
          <div className="text-5xl font-bold font-display">{score}%</div>
          <div className="text-sm text-tq-ink/70">
            {score === 100 ? (
              <span>Perfil net. Cap incidència detectada.</span>
            ) : (
              <span>
                {n_alerts} alert{n_alerts === 1 ? 'a' : 'es'} pendents. Mira
                els indicadors per veure què cal millorar.
              </span>
            )}
          </div>
        </div>
      </Card>

      {/* Default view: only non-success rows (or the full list when
          everything's either green or red). */}
      <ul className="space-y-2">
        {(showCollapsible ? issues : indicators).map(ind => (
          <li key={ind.key}>
            <IndicatorRow ind={ind} onCta={handleCta} />
          </li>
        ))}
      </ul>

      {showCollapsible && (
        <div>
          <button
            type="button"
            onClick={() => setShowSuccess(v => !v)}
            className="text-xs font-semibold text-white/70 hover:text-white"
          >
            {showSuccess ? '▾' : '▸'} {success.length} indicador
            {success.length === 1 ? '' : 's'} superat
            {success.length === 1 ? '' : 's'}{' '}
            {showSuccess ? '(amaga)' : '(mostra)'}
          </button>
          {showSuccess && (
            <ul className="space-y-2 mt-3">
              {success.map(ind => (
                <li key={ind.key}>
                  <IndicatorRow ind={ind} onCta={handleCta} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <SollicitudResumCard slug={slug} refreshKey={sollicitudRefreshKey} />
    </div>
  )
}


// ───────────────────────── Tab: Editar ───────────────────────────


const inputClass =
  'w-full mt-1 px-3 py-2 rounded-md bg-white text-tq-ink text-sm border border-gray-300 ' +
  'focus:outline-none focus:ring-2 focus:ring-tq-yellow'

function FieldError({ msg }) {
  if (!msg) return null
  return <p className="text-xs text-red-600 mt-1">{msg}</p>
}

function ImageUploader({ artistaPk, current, onChange }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('fitxer', file)
      fd.append('kind', 'artista')
      fd.append('artista_pk', String(artistaPk))
      const { url } = await api.post('/upload/imatge/', fd)
      onChange(url)
    } catch (ex) {
      setErr(ex.payload?.error || ex.message || 'Error en pujar')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-start gap-4">
      <div className="w-24 h-24 rounded-lg overflow-hidden bg-gray-100 flex items-center justify-center text-xs text-gray-500">
        {current ? (
          <img src={current} alt="" className="w-full h-full object-cover" />
        ) : (
          'Sense imatge'
        )}
      </div>
      <div className="flex-1">
        <label className="inline-block">
          <span className="px-3 py-1.5 rounded-md bg-tq-yellow text-tq-ink text-sm font-semibold cursor-pointer hover:bg-tq-yellow-deep hover:text-white">
            {busy ? 'Pujant…' : 'Pujar nova imatge'}
          </span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={handleFile}
            disabled={busy}
            className="hidden"
          />
        </label>
        <p className="text-xs text-gray-500 mt-1">
          Quadrada, mínim 400×400. Es retallarà a 800×800 WebP.
        </p>
        {err && <p className="text-xs text-red-600 mt-1">{err}</p>}
      </div>
    </div>
  )
}

function DeezerSection({ slug, items, onChange }) {
  const [adding, setAdding] = useState(false)
  const [newId, setNewId] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [err, setErr] = useState(null)

  async function handleAdd(e) {
    e.preventDefault()
    setErr(null)
    try {
      await api.post(`/compte/artista/${slug}/deezer-ids/`, {
        deezer_id: parseInt(newId, 10),
      })
      setNewId('')
      setAdding(false)
      onChange()
    } catch (ex) {
      setErr(ex.payload?.error || ex.message || 'Error')
    }
  }

  async function handleDelete(dzId) {
    setErr(null)
    try {
      await api.delete(`/compte/artista/${slug}/deezer-ids/${dzId}/`)
      onChange()
    } catch (ex) {
      setErr(ex.payload?.error || ex.message || 'Error')
    }
  }

  return (
    <section id="deezer-ids" className="space-y-3">
      <h3 className="font-semibold text-sm">Deezer IDs</h3>
      <ul className="space-y-1">
        {items.map(d => (
          <li
            key={d.pk}
            className="flex items-center gap-3 text-sm bg-gray-50 px-3 py-2 rounded"
          >
            <span className="font-mono">{d.deezer_id}</span>
            {d.principal && <Badge variant="yellow">principal</Badge>}
            <button
              type="button"
              onClick={() => setConfirmDelete(d)}
              className="ml-auto text-xs text-red-600 hover:underline"
            >
              Esborrar
            </button>
          </li>
        ))}
      </ul>
      {adding ? (
        <form onSubmit={handleAdd} className="flex gap-2 items-center">
          <input
            type="number"
            value={newId}
            onChange={e => setNewId(e.target.value)}
            placeholder="Deezer ID numèric"
            className={inputClass + ' flex-1 mt-0'}
            autoFocus
          />
          <button
            type="submit"
            className="px-3 py-2 bg-tq-yellow text-tq-ink rounded-md text-sm font-semibold"
          >
            Afegir
          </button>
          <button
            type="button"
            onClick={() => {
              setAdding(false)
              setErr(null)
            }}
            className="text-sm text-gray-500"
          >
            Cancel·lar
          </button>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="text-xs font-semibold text-tq-yellow-deep hover:underline"
        >
          + Afegir Deezer ID
        </button>
      )}
      {err && <p className="text-xs text-red-600">{err}</p>}
      <ConfirmDialog
        open={!!confirmDelete}
        title="Esborrar Deezer ID"
        body={
          <>
            Esborraràs el Deezer ID <strong>{confirmDelete?.deezer_id}</strong>.
            Si era principal, hauràs de definir-ne un altre per a continuar
            ingestint cançons.
          </>
        }
        confirmLabel="Esborrar"
        severity="danger"
        requireCheckbox
        checkboxLabel="Entenc que pot interrompre la ingestió de cançons."
        onConfirm={async () => {
          await handleDelete(confirmDelete.deezer_id)
          setConfirmDelete(null)
        }}
        onCancel={() => setConfirmDelete(null)}
      />
    </section>
  )
}

function LastfmAliasSection({ slug, items, onChange }) {
  const [adding, setAdding] = useState(false)
  const [newNom, setNewNom] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [err, setErr] = useState(null)

  async function handleAdd(e) {
    e.preventDefault()
    setErr(null)
    try {
      await api.post(`/compte/artista/${slug}/lastfm-aliases/`, {
        nom: newNom,
      })
      setNewNom('')
      setAdding(false)
      onChange()
    } catch (ex) {
      setErr(ex.payload?.error || ex.message || 'Error')
    }
  }

  async function handlePromote(aliasId) {
    setErr(null)
    try {
      await api.post(
        `/compte/artista/${slug}/lastfm-aliases/${aliasId}/prioritari/`
      )
      onChange()
    } catch (ex) {
      setErr(ex.payload?.error || ex.message || 'Error')
    }
  }

  async function handleDelete(aliasId) {
    setErr(null)
    try {
      await api.delete(`/compte/artista/${slug}/lastfm-aliases/${aliasId}/`)
      onChange()
    } catch (ex) {
      setErr(ex.payload?.error || ex.message || 'Error')
    }
  }

  return (
    <section id="lastfm-aliases" className="space-y-3">
      <h3 className="font-semibold text-sm">Last.fm aliases</h3>
      <p className="text-xs text-gray-500">
        El <em>prioritari</em> és el nom canònic que apareix al públic;
        la resta d'aliases es continuen sumant al senyal de scrobbles.
      </p>
      <ul className="space-y-1">
        {items.map(al => (
          <li
            key={al.pk}
            className="flex items-center gap-3 text-sm bg-gray-50 px-3 py-2 rounded"
          >
            <span>{al.nom}</span>
            {al.prioritari ? (
              <Badge variant="yellow">prioritari</Badge>
            ) : al.confirmat ? (
              <Badge variant="success">confirmat</Badge>
            ) : (
              <Badge variant="warning">pendent</Badge>
            )}
            <div className="ml-auto flex gap-3 text-xs">
              {!al.prioritari && al.confirmat && (
                <button
                  type="button"
                  onClick={() => handlePromote(al.pk)}
                  className="font-semibold text-tq-yellow-deep hover:underline"
                >
                  Marcar prioritari
                </button>
              )}
              <button
                type="button"
                onClick={() => setConfirmDelete(al)}
                className="text-red-600 hover:underline"
              >
                Esborrar
              </button>
            </div>
          </li>
        ))}
      </ul>
      {adding ? (
        <form onSubmit={handleAdd} className="flex gap-2 items-center">
          <input
            type="text"
            value={newNom}
            onChange={e => setNewNom(e.target.value)}
            placeholder="Nom alternatiu (ex. Böira)"
            className={inputClass + ' flex-1 mt-0'}
            autoFocus
          />
          <button
            type="submit"
            className="px-3 py-2 bg-tq-yellow text-tq-ink rounded-md text-sm font-semibold"
          >
            Afegir
          </button>
          <button
            type="button"
            onClick={() => {
              setAdding(false)
              setErr(null)
            }}
            className="text-sm text-gray-500"
          >
            Cancel·lar
          </button>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="text-xs font-semibold text-tq-yellow-deep hover:underline"
        >
          + Afegir alias
        </button>
      )}
      {err && <p className="text-xs text-red-600">{err}</p>}
      <ConfirmDialog
        open={!!confirmDelete}
        title="Esborrar alias"
        body={
          <>
            Esborraràs l'alias <strong>{confirmDelete?.nom}</strong>.
            Si era el prioritari de l'únic alias confirmat, l'artista
            es quedarà sense nom canònic a Last.fm fins que n'afegeixis
            un altre.
          </>
        }
        confirmLabel="Esborrar"
        severity="warning"
        onConfirm={async () => {
          await handleDelete(confirmDelete.pk)
          setConfirmDelete(null)
        }}
        onCancel={() => setConfirmDelete(null)}
      />
    </section>
  )
}

function LocalitatSection({ slug, items, onChange }) {
  const [adding, setAdding] = useState(false)
  const [municipiPk, setMunicipiPk] = useState('')
  const [manual, setManual] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [err, setErr] = useState(null)

  async function handleAdd(e) {
    e.preventDefault()
    setErr(null)
    const payload = municipiPk
      ? { municipi_pk: parseInt(municipiPk, 10) }
      : { manual }
    try {
      await api.post(`/compte/artista/${slug}/localitats/`, payload)
      setMunicipiPk('')
      setManual('')
      setAdding(false)
      onChange()
    } catch (ex) {
      setErr(ex.payload?.error || ex.message || 'Error')
    }
  }

  async function handleDelete(locId) {
    setErr(null)
    try {
      await api.delete(`/compte/artista/${slug}/localitats/${locId}/`)
      onChange()
    } catch (ex) {
      setErr(ex.payload?.error || ex.message || 'Error')
    }
  }

  return (
    <section id="localitats" className="space-y-3">
      <h3 className="font-semibold text-sm">Localitats</h3>
      <ul className="space-y-1">
        {items.map(loc => (
          <li
            key={loc.pk}
            className="flex items-center gap-3 text-sm bg-gray-50 px-3 py-2 rounded"
          >
            <span>{loc.nom}</span>
            {loc.territori && <Badge variant="default">{loc.territori}</Badge>}
            {loc.comarca && (
              <span className="text-xs text-gray-500">{loc.comarca}</span>
            )}
            <button
              type="button"
              onClick={() => setConfirmDelete(loc)}
              className="ml-auto text-xs text-red-600 hover:underline"
            >
              Esborrar
            </button>
          </li>
        ))}
      </ul>
      {adding ? (
        <form onSubmit={handleAdd} className="space-y-2">
          <input
            type="number"
            value={municipiPk}
            onChange={e => setMunicipiPk(e.target.value)}
            placeholder="Municipi PK (de la BD)"
            className={inputClass + ' mt-0'}
          />
          <div className="text-xs text-gray-500">o</div>
          <input
            type="text"
            value={manual}
            onChange={e => setManual(e.target.value)}
            placeholder="Localitat manual (fora dels PPCC)"
            className={inputClass + ' mt-0'}
          />
          <div className="flex gap-2">
            <button
              type="submit"
              className="px-3 py-2 bg-tq-yellow text-tq-ink rounded-md text-sm font-semibold"
            >
              Afegir
            </button>
            <button
              type="button"
              onClick={() => {
                setAdding(false)
                setErr(null)
              }}
              className="text-sm text-gray-500"
            >
              Cancel·lar
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="text-xs font-semibold text-tq-yellow-deep hover:underline"
        >
          + Afegir localitat
        </button>
      )}
      {err && <p className="text-xs text-red-600">{err}</p>}
      <ConfirmDialog
        open={!!confirmDelete}
        title="Esborrar localitat"
        body={
          <>
            Esborraràs <strong>{confirmDelete?.nom}</strong>. Els territoris
            de l'artista es recalcularan automàticament.
          </>
        }
        confirmLabel="Esborrar"
        severity="warning"
        onConfirm={async () => {
          await handleDelete(confirmDelete.pk)
          setConfirmDelete(null)
        }}
        onCancel={() => setConfirmDelete(null)}
      />
    </section>
  )
}

function EditarTab({ slug, data, onReload }) {
  const [edits, setEdits] = useState({
    bio: data.bio,
    genere: data.genere,
    percentatge_femeni: data.percentatge_femeni,
    imatge_url: data.imatge_url,
    ...data.social,
  })
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState({})
  const [saved, setSaved] = useState(null)

  function set(field, value) {
    setEdits(s => ({ ...s, [field]: value }))
    setSaved(null)
  }

  function diff() {
    const out = {}
    for (const [k, v] of Object.entries(edits)) {
      const original =
        k in data ? data[k] : (data.social?.[k] ?? '')
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
      const res = await api.patch(`/compte/artista/${slug}/editar/`, payload)
      setEdits({
        bio: res.bio,
        genere: res.genere,
        percentatge_femeni: res.percentatge_femeni,
        imatge_url: res.imatge_url,
        ...res.social,
      })
      setSaved({
        tone: 'success',
        msg: res.canviats?.length
          ? `Desat. Camps actualitzats: ${res.canviats.join(', ')}.`
          : 'Sense canvis.',
      })
      onReload?.()
    } catch (err) {
      if (err.payload?.errors) setErrors(err.payload.errors)
      else setSaved({ tone: 'danger', msg: err.message || 'Error en desar.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6 mt-6">
      <form onSubmit={handleSubmit} className="space-y-6">
        <fieldset id="imatge" className="bg-white text-tq-ink rounded-lg p-5 space-y-4">
          <legend className="font-semibold bg-white px-2">Imatge</legend>
          <ImageUploader
            artistaPk={data.pk}
            current={edits.imatge_url}
            onChange={url => set('imatge_url', url)}
          />
          <FieldError msg={errors.imatge_url} />
        </fieldset>

        <fieldset className="bg-white text-tq-ink rounded-lg p-5 space-y-4">
          <legend className="font-semibold bg-white px-2">Sobre l'artista</legend>

          <label id="bio" className="block text-xs font-semibold">
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

          <label id="genere" className="block text-xs font-semibold">
            Gènere musical
            <input
              type="text"
              value={edits.genere || ''}
              onChange={e => set('genere', e.target.value)}
              className={inputClass + ' font-normal'}
              placeholder="ex. pop, indie, hip-hop…"
            />
            <FieldError msg={errors.genere} />
            <p className="text-[11px] text-gray-500 mt-1">
              Camp lliure. Un classificador intern el normalitzarà a un
              gènere canònic en el següent cicle (24&nbsp;h).
            </p>
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
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <FieldError msg={errors.percentatge_femeni} />
          </label>
        </fieldset>

        <fieldset id="socials" className="bg-white text-tq-ink rounded-lg p-5">
          <legend className="font-semibold bg-white px-2">
            Xarxes i enllaços
          </legend>
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
        </div>
      </form>

      {/* M2M sections live outside the form so their own POST/DELETE
          calls don't interact with the main PATCH. */}
      <div className="bg-white text-tq-ink rounded-lg p-5 space-y-6">
        <DeezerSection
          slug={slug}
          items={data.deezer_ids}
          onChange={onReload}
        />
        <hr className="border-gray-200" />
        <LastfmAliasSection
          slug={slug}
          items={data.lastfm_aliases}
          onChange={onReload}
        />
        <hr className="border-gray-200" />
        <LocalitatSection
          slug={slug}
          items={data.localitats}
          onChange={onReload}
        />
      </div>
    </div>
  )
}


// ───────────────────────── Tab: Cançons ──────────────────────────


// Motiu → Badge tone. Maps the four reject reasons documented in
// `HistorialRevisio.MOTIUS`. `no_catala` is the most common (~languaje
// drift) and reads as neutral; `album_incorrecte` and `artista_
// incorrecte` flag profile collisions and warrant a warning; `no_musica`
// is rare and is shown danger because it usually means a podcast that
// slipped through ingestion. Keep this table in sync with backend.
const MOTIU_TONE = {
  no_catala: 'default',
  album_incorrecte: 'warning',
  artista_incorrecte: 'warning',
  no_musica: 'danger',
}
const MOTIU_LABEL = {
  no_catala: 'No és en català',
  album_incorrecte: 'Àlbum incorrecte',
  artista_incorrecte: 'Artista incorrecte',
  no_musica: 'No és música',
}

function CanconsTab({ slug, onSollicitudCreated }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // Sprint Workflow Sol·licituds E.1: multi-select with one global
  // "Demanar revisió" button at the tab header. Each section keeps
  // its own Set so the user can toggle independently, but a single
  // POST bundles both lists in one SolicitudRevisio.
  const [selectedPendents, setSelectedPendents] = useState(() => new Set())
  const [selectedRebutjades, setSelectedRebutjades] = useState(() => new Set())
  const [confirmPing, setConfirmPing] = useState(false)
  const [feedback, setFeedback] = useState(null)

  function reload() {
    setLoading(true)
    api
      .get(`/compte/artista/${slug}/cancons-pendents/`)
      .then(d => {
        setData(d)
        setSelectedPendents(new Set())
        setSelectedRebutjades(new Set())
      })
      .catch(e => setError(e.message || 'Error'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug])

  if (loading) return <div className="h-24 mt-6 bg-white/10 rounded animate-pulse" />
  if (error) return <Alert tone="danger">{error}</Alert>
  if (!data) return null

  const pendents = data.pendents || data.results || []
  const rebutjades = data.rebutjades || []
  const verificades = data.verificades || []
  const nVerificadesTotal = data.n_verificades_total ?? verificades.length

  const cooldownActive = !!(
    data.cooldown_until && new Date(data.cooldown_until) > new Date()
  )
  const fmtDate = iso => {
    if (!iso) return ''
    const d = new Date(iso)
    return `${String(d.getDate()).padStart(2, '0')}/${String(
      d.getMonth() + 1
    ).padStart(2, '0')}/${d.getFullYear()}`
  }

  const togglePendent = pk =>
    setSelectedPendents(prev => {
      const next = new Set(prev)
      next.has(pk) ? next.delete(pk) : next.add(pk)
      return next
    })
  const toggleRebutjada = pk =>
    setSelectedRebutjades(prev => {
      const next = new Set(prev)
      next.has(pk) ? next.delete(pk) : next.add(pk)
      return next
    })
  const allPendentsSelected =
    pendents.length > 0 && selectedPendents.size === pendents.length
  const allRebutjadesSelected =
    rebutjades.length > 0 && selectedRebutjades.size === rebutjades.length
  const toggleAllPendents = () =>
    setSelectedPendents(
      allPendentsSelected ? new Set() : new Set(pendents.map(c => c.pk))
    )
  const toggleAllRebutjades = () =>
    setSelectedRebutjades(
      allRebutjadesSelected ? new Set() : new Set(rebutjades.map(r => r.pk))
    )

  const totalSelected = selectedPendents.size + selectedRebutjades.size

  async function handlePing() {
    setFeedback(null)
    const body = {
      include_canco_ids: Array.from(selectedPendents),
      include_rebutjada_historial_pks: Array.from(selectedRebutjades),
    }
    try {
      const res = await api.post(
        `/compte/artista/${slug}/cancons-pendents/ping-staff/`,
        body
      )
      setFeedback({
        tone: 'success',
        msg:
          `S'ha enviat la sol·licitud #${res.sollicitud_pk} al staff. ` +
          'Et notificarem per email quan algú l\'hagi processada. ' +
          'Mentrestant, no cal que facis res; el staff revisarà les ' +
          'cançons i decidirà quines s\'aproven o es tornen al pipeline. ' +
          `Pròxima sol·licitud disponible el ${fmtDate(res.next_ping_at)}.`,
      })
      onSollicitudCreated?.()
      reload()
    } catch (ex) {
      setFeedback({
        tone: 'danger',
        msg: ex.payload?.error || ex.message || 'Error',
      })
    } finally {
      setConfirmPing(false)
    }
  }

  // Empty-state when no list has rows.
  if (
    pendents.length === 0 &&
    rebutjades.length === 0 &&
    verificades.length === 0
  ) {
    return (
      <div className="space-y-4 mt-6">
        {feedback && <Alert tone={feedback.tone}>{feedback.msg}</Alert>}
        <Card>
          <div className="p-6 text-center text-tq-ink/70">
            Cap cançó al sistema encara.
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6 mt-6">
      {feedback && <Alert tone={feedback.tone}>{feedback.msg}</Alert>}

      {/* ── Global action bar ── */}
      <Card>
        <div className="p-4 flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold">
              {totalSelected === 0
                ? 'Selecciona cançons amb els checkboxes per a demanar revisió.'
                : `${totalSelected} cançó/ns seleccionada${totalSelected === 1 ? '' : 'es'}: ` +
                  `${selectedPendents.size} pendent${selectedPendents.size === 1 ? '' : 's'} + ` +
                  `${selectedRebutjades.size} rebutjada${selectedRebutjades.size === 1 ? '' : 's'}`}
            </p>
            {cooldownActive && (
              <p className="text-xs text-tq-ink/60 mt-1">
                Cooldown actiu fins el {fmtDate(data.cooldown_until)} — pots
                fer una nova sol·licitud cada 7&nbsp;dies.
              </p>
            )}
          </div>
          <button
            type="button"
            disabled={totalSelected === 0 || cooldownActive}
            onClick={() => setConfirmPing(true)}
            title={
              cooldownActive
                ? `Pròxima sol·licitud disponible el ${fmtDate(data.cooldown_until)}`
                : ''
            }
            className="px-4 py-2 bg-tq-yellow text-tq-ink rounded-md text-sm font-semibold disabled:opacity-50"
          >
            Demanar revisió ({selectedPendents.size} pendents + {selectedRebutjades.size} rebutjades)
          </button>
        </div>
      </Card>

      {/* ── Pendents de verificar ── */}
      <details open className="group">
        <summary className="cursor-pointer list-none flex items-center gap-3 mb-2 select-none">
          <span className="text-white/60 text-xs transition-transform group-open:rotate-90">
            ▸
          </span>
          <h3 className="text-sm font-semibold text-white">
            Pendents de verificar ({pendents.length})
          </h3>
          {pendents.length > 0 && (
            <label
              className="ml-auto inline-flex items-center gap-2 text-xs text-white/70 cursor-pointer"
              onClick={e => e.stopPropagation()}
            >
              <input
                type="checkbox"
                checked={allPendentsSelected}
                onChange={toggleAllPendents}
              />
              <span>
                Totes ({selectedPendents.size}/{pendents.length})
              </span>
            </label>
          )}
        </summary>
        <Card>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-tq-ink/60">
              <tr>
                <th className="p-3 w-8"></th>
                <th className="p-3">Cançó</th>
                <th className="p-3">Àlbum</th>
                <th className="p-3">Data</th>
                <th className="p-3">Estat</th>
              </tr>
            </thead>
            <tbody>
              {pendents.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-tq-ink/60">
                    Cap cançó pendent.
                  </td>
                </tr>
              ) : (
                pendents.map(c => (
                  <tr key={c.pk} className="border-t border-gray-100">
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={selectedPendents.has(c.pk)}
                        onChange={() => togglePendent(c.pk)}
                        aria-label={`Seleccionar ${c.nom}`}
                      />
                    </td>
                    <td className="p-3">{c.nom}</td>
                    <td className="p-3 text-tq-ink/70">{c.album_nom || '—'}</td>
                    <td className="p-3 text-tq-ink/70">
                      {fmtDate(c.data_llancament)}
                    </td>
                    <td className="p-3">
                      <Badge variant="warning">no verificada</Badge>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      </details>

      {/* ── Rebutjades recents ── */}
      <details className="group">
        <summary className="cursor-pointer list-none flex items-center gap-3 mb-2 select-none">
          <span className="text-white/60 text-xs transition-transform group-open:rotate-90">
            ▸
          </span>
          <h3 className="text-sm font-semibold text-white">
            Rebutjades recents ({rebutjades.length})
          </h3>
          {rebutjades.length > 0 && (
            <label
              className="ml-auto inline-flex items-center gap-2 text-xs text-white/70 cursor-pointer"
              onClick={e => e.stopPropagation()}
            >
              <input
                type="checkbox"
                checked={allRebutjadesSelected}
                onChange={toggleAllRebutjades}
              />
              <span>
                Totes ({selectedRebutjades.size}/{rebutjades.length})
              </span>
            </label>
          )}
        </summary>
        <Card>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-tq-ink/60">
              <tr>
                <th className="p-3 w-8"></th>
                <th className="p-3">Cançó</th>
                <th className="p-3">Àlbum</th>
                <th className="p-3">Data rebuig</th>
                <th className="p-3">Motiu</th>
              </tr>
            </thead>
            <tbody>
              {rebutjades.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-tq-ink/60">
                    Cap rebuig recent.
                  </td>
                </tr>
              ) : (
                rebutjades.map(r => (
                  <tr key={r.pk} className="border-t border-gray-100">
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={selectedRebutjades.has(r.pk)}
                        onChange={() => toggleRebutjada(r.pk)}
                        aria-label={`Seleccionar ${r.canco_nom}`}
                      />
                    </td>
                    <td className="p-3">{r.canco_nom}</td>
                    <td className="p-3 text-tq-ink/70">{r.album_nom || '—'}</td>
                    <td className="p-3 text-tq-ink/70">
                      {fmtDate(r.data_rebuig)}
                    </td>
                    <td className="p-3">
                      <Badge variant={MOTIU_TONE[r.motiu] || 'default'}>
                        {MOTIU_LABEL[r.motiu] || r.motiu}
                      </Badge>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      </details>

      {/* ── Verificades (informatiu, sense acció) ──
          Native `<details>` per consistència amb altres collapsibles
          del SPA (TopBreakdownPanel, LastfmPanel, StaffSocialPage,
          ArtistaEditPage). Tancat per defecte: és la secció més
          llarga i menys actionable. */}
      <details className="group">
        <summary className="cursor-pointer list-none flex items-center gap-3 mb-2 select-none">
          <span className="text-white/60 text-xs transition-transform group-open:rotate-90">
            ▸
          </span>
          <h3 className="text-sm font-semibold text-white">
            Verificades ({nVerificadesTotal})
          </h3>
          {nVerificadesTotal > verificades.length && (
            <span className="text-xs text-white/60">
              · mostrant les {verificades.length} més recents
            </span>
          )}
        </summary>
        <Card>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-tq-ink/60">
              <tr>
                <th className="p-3">Cançó</th>
                <th className="p-3">Àlbum</th>
                <th className="p-3">Data</th>
                <th className="p-3">Estat</th>
              </tr>
            </thead>
            <tbody>
              {verificades.length === 0 ? (
                <tr>
                  <td colSpan={4} className="p-6 text-center text-tq-ink/60">
                    Cap cançó verificada encara.
                  </td>
                </tr>
              ) : (
                verificades.map(c => (
                  <tr key={c.pk} className="border-t border-gray-100">
                    <td className="p-3">{c.nom}</td>
                    <td className="p-3 text-tq-ink/70">{c.album_nom || '—'}</td>
                    <td className="p-3 text-tq-ink/70">
                      {fmtDate(c.data_llancament)}
                    </td>
                    <td className="p-3">
                      <Badge variant="success">verificada</Badge>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      </details>

      <ConfirmDialog
        open={confirmPing}
        title="Demanar revisió al staff"
        body={
          <>
            S'enviarà una sol·licitud al staff per a revisar les cançons
            seleccionades (<strong>{selectedPendents.size}</strong> pendents +{' '}
            <strong>{selectedRebutjades.size}</strong> rebutjades). Rebràs un
            email quan estigui resolta. Pots fer una nova sol·licitud cada
            7&nbsp;dies.
          </>
        }
        confirmLabel="Enviar"
        severity="warning"
        onConfirm={handlePing}
        onCancel={() => setConfirmPing(false)}
      />
    </div>
  )
}


// ───────────────────────── Page ──────────────────────────────────


export default function ArtistaDashboardPage() {
  const { slug } = useParams()
  const { profile, loading: authLoading } = useAuth()
  const { data, error, loading, reload } = useArtista(slug)
  const [tab, setTab] = useState('estat')
  // Bump on every successful "demanar revisió" so the EstatTab card
  // resum re-fetches /sollicituds/ and reflects the new pendent.
  const [sollicitudRefreshKey, setSollicitudRefreshKey] = useState(0)

  // Hash → tab on mount and on hashchange.
  useEffect(() => {
    const sync = () => {
      const key = (window.location.hash || '').replace(/^#/, '')
      if (TABS.some(t => t.key === key)) setTab(key)
      else setTab('estat')
    }
    sync()
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])

  if (authLoading) return null
  if (!profile)
    return (
      <Navigate to={`/compte/accedir?next=/compte/artista/${slug}/`} replace />
    )

  if (loading) {
    return (
      <section className="max-w-6xl mx-auto py-10 space-y-3">
        <div className="h-8 bg-white/10 rounded w-1/2 animate-pulse" />
        <div className="h-48 bg-white/10 rounded animate-pulse" />
      </section>
    )
  }

  if (error?.status === 403) {
    return (
      <section className="max-w-6xl mx-auto py-10 text-white">
        <Alert tone="danger">
          No ets gestor verificat d'aquest artista. Demana la gestió des
          de la seua pàgina pública o contacta amb staff.
        </Alert>
        <p className="mt-4">
          <Link to="/compte" className="text-tq-yellow underline">
            ← Torna al teu compte
          </Link>
        </p>
      </section>
    )
  }
  if (error) {
    return (
      <section className="max-w-6xl mx-auto py-10 text-white">
        <Alert tone="danger">{error.message || 'Error'}</Alert>
      </section>
    )
  }
  if (!data) return null

  return (
    <section className="max-w-6xl mx-auto py-8 text-white">
      <header className="mb-4">
        <p className="text-[10px] uppercase tracking-widest text-white/60">
          <Link to="/compte" className="hover:text-white">
            Compte
          </Link>{' '}
          ›{' '}
          <Link to={artistaUrl(data.slug)} className="hover:text-white">
            Artista
          </Link>{' '}
          › Gestió
        </p>
        <h1 className="text-2xl font-bold font-display mt-1">{data.nom}</h1>
        <p className="mt-1">
          <Link
            to={artistaUrl(data.slug)}
            className="text-tq-yellow underline text-sm"
          >
            Veure la pàgina pública →
          </Link>
        </p>
      </header>

      <Tabs
        tabs={TABS}
        activeKey={tab}
        onChange={k => {
          window.history.replaceState(null, '', `#${k}`)
          setTab(k)
        }}
      />

      {tab === 'estat' && (
        <EstatTab
          slug={slug}
          sollicitudRefreshKey={sollicitudRefreshKey}
          onSwitchTab={(key, hash) => {
            window.history.replaceState(null, '', hash || `#${key}`)
            setTab(key)
          }}
        />
      )}
      {tab === 'editar' && (
        <EditarTab slug={slug} data={data} onReload={reload} />
      )}
      {tab === 'cancons' && (
        <CanconsTab
          slug={slug}
          onSollicitudCreated={() => setSollicitudRefreshKey(k => k + 1)}
        />
      )}
    </section>
  )
}
