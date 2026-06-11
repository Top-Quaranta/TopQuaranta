/**
 * StaffCanconsPage — /staff/cancons
 *
 * Track moderation. Bulk select + approve/reject. Filters for
 * verificada state, ml_classe, whisper, and free-text search.
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import {
  Btn,
  EmptyState,
  Input,
  PageHeader,
  Pagination,
  Pill,
  Select,
  Table,
  TableCard,
  Td,
  Th,
  THead,
  Tr,
} from '../../components/staff/StaffTable'
import { Field } from '../../components/staff/StaffTable'
import FilterPanel from '../../components/staff/FilterPanel'

// Mirror of music.constants.MOTIUS_REBUIG (label/value pairs).
// Action-only labels — cause / when-to-use lives in
// docs/architecture/staff.md section 5 and must NOT be duplicated
// here. Order: cançó (safest) first, artista (most destructive)
// last.
const MOTIUS = [
  ['desvincular_canco',   'Desvincular la cançó'],
  ['desvincular_album',   "Desvincular l'àlbum"],
  ['desvincular_artista', "Desvincular l'artista"],
]

// Default filter values — also used by the FilterPanel "Restablir"
// button and to compute the "active filters" count badge.
const DEFAULTS = {
  verificada: '0',
  ml_classe: '',
  whisper: '',
  deezer: '',
  mb: '',
  preview: '',
  recent: '',
  sort: '-ml_confianca',
}

export default function StaffCanconsPage() {
  const navigate = useNavigate()
  // Seed filters from query string so deep links like
  // `/staff/cancons?artista_pk=123&verificada=1` work as shareable
  // URLs (pendents row → verified tracks, for example).
  const [urlParams, setUrlParams] = useSearchParams()
  const [q, setQ] = useState(urlParams.get('q') || '')
  const [applied, setApplied] = useState({
    verificada: urlParams.get('verificada') ?? DEFAULTS.verificada,
    ml_classe:  urlParams.get('ml_classe')  ?? DEFAULTS.ml_classe,
    whisper:    urlParams.get('whisper')    ?? DEFAULTS.whisper,
    deezer:     urlParams.get('deezer')     ?? DEFAULTS.deezer,
    mb:         urlParams.get('mb')         ?? DEFAULTS.mb,
    preview:    urlParams.get('preview')    ?? DEFAULTS.preview,
    recent:     urlParams.get('recent')     ?? DEFAULTS.recent,
    sort:       urlParams.get('sort')       ?? DEFAULTS.sort,
  })
  const { verificada, ml_classe: mlClasse, whisper, deezer, mb, preview, recent, sort } = applied
  const artistaPk = urlParams.get('artista_pk') || ''
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [sel, setSel] = useState(new Set())
  const [motiu, setMotiu] = useState('desvincular_canco')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  function load() {
    const params = new URLSearchParams({
      q, verificada, ml_classe: mlClasse, whisper, deezer, mb, preview, recent, sort, page,
    })
    if (artistaPk) params.set('artista_pk', artistaPk)
    api.get(`/staff/cancons/?${params}`).then(setData).catch(() => setData(null))
  }

  useEffect(load, [q, verificada, mlClasse, whisper, deezer, mb, preview, recent, sort, page, artistaPk])

  const allSelected = data?.results?.length && data.results.every(r => sel.has(r.pk))

  function toggle(pk) {
    setSel(s => {
      const n = new Set(s)
      if (n.has(pk)) n.delete(pk)
      else n.add(pk)
      return n
    })
  }
  function toggleAll() {
    if (!data) return
    setSel(s => {
      const n = new Set(s)
      const allHere = data.results.every(r => n.has(r.pk))
      data.results.forEach(r => (allHere ? n.delete(r.pk) : n.add(r.pk)))
      return n
    })
  }

  async function act(action) {
    if (sel.size === 0) {
      setMsg('Cap cançó seleccionada.')
      return
    }
    setBusy(true)
    setMsg('')
    try {
      const out = await api.post('/staff/cancons/accio/', {
        action,
        ids: [...sel],
        motiu,
      })
      setMsg(out.msg || `${out.n || sel.size} cançons processades.`)
      setSel(new Set())
      load()
    } catch (e) {
      setMsg(e.payload?.error || e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <PageHeader
        title="Cançons"
        subtitle={
          <>
            {data ? `${data.total} cançons` : 'Carregant…'}
            {artistaPk && data?.results?.[0]?.artista && (
              <> · filtrant per <strong>{data.results[0].artista.nom}</strong>
                {' '}
                <button
                  type="button"
                  onClick={() => {
                    const p = new URLSearchParams(urlParams)
                    p.delete('artista_pk')
                    setUrlParams(p)
                  }}
                  className="underline ml-1 hover:text-tq-yellow"
                >
                  treure filtre
                </button>
              </>
            )}
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Input
          placeholder="Cerca cançó o artista…"
          value={q}
          onChange={e => { setPage(1); setQ(e.target.value) }}
          className="flex-1 min-w-[14rem]"
        />
        {/* Quick chip — most common moderation flow is "spot what
            was released this week", so we surface it next to the
            search box rather than burying it inside the panel. */}
        <button
          type="button"
          onClick={() => {
            setApplied(prev => ({
              ...prev,
              recent: prev.recent === '7' ? '' : '7',
              sort: '-data_llancament',
            }))
            setPage(1)
          }}
          className={`text-xs px-3 py-1.5 rounded border ${
            recent === '7'
              ? 'bg-tq-ink text-tq-yellow border-tq-ink'
              : 'bg-white text-tq-ink border-tq-ink/20 hover:bg-tq-yellow/10'
          }`}
          title="Llançades en els últims 7 dies"
        >
          Últims 7 dies {recent === '7' ? '✓' : ''}
        </button>
        <FilterPanel
          applied={applied}
          defaults={DEFAULTS}
          onApply={next => { setApplied(next); setPage(1) }}
        >
          {(p, setP) => (
            <>
              <Field label="Estat de verificació">
                <Select aria-label="Verificació" value={p.verificada} onChange={e => setP({ verificada: e.target.value })}>
                  <option value="0">No verificades</option>
                  <option value="1">Verificades</option>
                  <option value="">Totes</option>
                </Select>
              </Field>
              <Field label="Classe ML">
                <Select aria-label="Classe ML" value={p.ml_classe} onChange={e => setP({ ml_classe: e.target.value })}>
                  <option value="">Totes</option>
                  <option value="A">Classe A</option>
                  <option value="B">Classe B</option>
                  <option value="C">Classe C</option>
                </Select>
              </Field>
              <Field label="Whisper LID">
                <Select aria-label="Whisper LID" value={p.whisper} onChange={e => setP({ whisper: e.target.value })}>
                  <option value="">Qualsevol</option>
                  <option value="ca">Català</option>
                  <option value="no_ca">No-català</option>
                  <option value="pendent">Pendent</option>
                </Select>
              </Field>
              <Field label="Preview Deezer">
                <Select aria-label="Preview" value={p.preview} onChange={e => setP({ preview: e.target.value })}>
                  <option value="">Qualsevol</option>
                  <option value="si">Té preview</option>
                  <option value="no">Sense preview</option>
                </Select>
              </Field>
              <Field label="Deezer ID">
                <Select aria-label="Deezer" value={p.deezer} onChange={e => setP({ deezer: e.target.value })}>
                  <option value="">Qualsevol</option>
                  <option value="si">Amb Deezer</option>
                  <option value="no">Sense Deezer</option>
                </Select>
              </Field>
              <Field label="MusicBrainz">
                <Select aria-label="MusicBrainz" value={p.mb} onChange={e => setP({ mb: e.target.value })}>
                  <option value="">Qualsevol</option>
                  <option value="confirmat">Confirmat ✓</option>
                  <option value="no_confirmat">No confirmat ✗</option>
                  <option value="desconegut">Desconegut ?</option>
                  <option value="artista_amb_mbid">Artista té MBID (cançó no)</option>
                  <option value="sense_cobertura">Sense cobertura</option>
                  <option value="cat">Lletra cat</option>
                  <option value="artista_dissolt">Artista dissolt</option>
                </Select>
              </Field>
              <Field label="Llançament recent">
                <Select aria-label="Recents" value={p.recent} onChange={e => setP({ recent: e.target.value })}>
                  <option value="">Qualsevol data</option>
                  <option value="7">Últims 7 dies</option>
                  <option value="30">Últims 30 dies</option>
                  <option value="90">Últims 90 dies</option>
                </Select>
              </Field>
              <Field label="Ordenació">
                <Select aria-label="Ordenació" value={p.sort} onChange={e => setP({ sort: e.target.value })}>
                  <option value="-ml_confianca">ML conf. ↓</option>
                  <option value="ml_confianca">ML conf. ↑</option>
                  <option value="-data_llancament">Data ↓ (més recents)</option>
                  <option value="data_llancament">Data ↑ (més antigues)</option>
                  <option value="nom">Nom A-Z</option>
                  <option value="-nom">Nom Z-A</option>
                  <option value="artista">Artista A-Z</option>
                  <option value="-artista">Artista Z-A</option>
                </Select>
              </Field>
            </>
          )}
        </FilterPanel>
      </div>

      {sel.size > 0 && (
        <div className="flex flex-wrap gap-2 mb-3 p-2 bg-tq-yellow/90 text-tq-ink rounded">
          <span className="text-sm font-semibold">{sel.size} seleccionades</span>
          <Select aria-label="Motiu" value={motiu} onChange={e => setMotiu(e.target.value)}>
            {MOTIUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          <Btn onClick={() => act('aprovar')} disabled={busy}>Aprovar</Btn>
          <Btn tone="danger" onClick={() => act('rebutjar')} disabled={busy}>Rebutjar</Btn>
          <Btn tone="secondary" onClick={() => setSel(new Set())} disabled={busy}>Netejar</Btn>
        </div>
      )}

      {msg && <p className="text-sm text-white/80 mb-3">{msg}</p>}

      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th className="w-8"><input type="checkbox" aria-label="Selecciona-ho tot" checked={!!allSelected} onChange={toggleAll} /></Th>
              <Th>Cançó</Th>
              <Th>Artista</Th>
              <Th>Àlbum</Th>
              <Th>ML</Th>
              <Th>Whisper</Th>
              <Th>MB</Th>
              <Th>Estat</Th>
              <Th>Preescolta</Th>
            </tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr><td colSpan={9}><EmptyState>Cap cançó.</EmptyState></td></tr>
            )}
            {data?.results?.map(c => (
              <Tr key={c.pk} onClick={() => navigate(`/staff/cancons/${c.pk}`)}>
                <Td className="w-8" onClick={e => e.stopPropagation()}>
                  <input type="checkbox" aria-label={`Selecciona la cançó ${c.nom}`} checked={sel.has(c.pk)} onChange={() => toggle(c.pk)} />
                </Td>
                <Td>
                  <div className="font-semibold">{c.nom}</div>
                  {c.isrc && <div className="text-[11px] opacity-60">ISRC {c.isrc}</div>}
                </Td>
                <Td>
                  <div>
                    {c.artista.nom}
                    {c.artista.te_homonims && (
                      <span
                        className="ml-1 text-[10px] font-semibold text-amber-700"
                        title="Hi ha un altre artista amb el mateix nom (ignorant accents i puntuació). Compte: possible homònim (cas Crim)."
                      >
                        ⚠ homònim
                      </span>
                    )}
                  </div>
                  {/* Spotify canonical artist name when it differs from
                      Deezer's, plus the dispersion badge. Discreet on
                      purpose: only surfaces when the data is there,
                      otherwise no visual noise. See ADR-0012. */}
                  {c.spotify?.artist_name && c.spotify.artist_name !== c.artista.nom && (
                    <div className="text-[10px] opacity-60" title="Nom canonic a Spotify (post enrichment)">
                      Sp: {c.spotify.artist_name}
                    </div>
                  )}
                  {c.artista.spotify_dispersio > 1 && (
                    <div
                      className="text-[10px] font-semibold text-amber-700"
                      title={`Aquest artista te ${c.artista.spotify_dispersio} identitats Spotify distintes a les seves cancons enriquides. Possible barreja Deezer.`}
                    >
                      possible barreja: {c.artista.spotify_dispersio} artistes Spotify
                    </div>
                  )}
                  {c.artista.mb_end_date && (
                    <div className="text-[10px] font-semibold text-red-600" title={`MusicBrainz: dissolt ${c.artista.mb_end_date}`}>
                      ⚠ dissolt {c.artista.mb_end_date.slice(0, 4)}
                    </div>
                  )}
                </Td>
                <Td className="text-xs opacity-70">{c.album?.nom || '—'}</Td>
                <Td>
                  {c.ml_classe && <Pill tone={c.ml_classe === 'A' ? 'green' : c.ml_classe === 'C' ? 'red' : 'yellow'}>{c.ml_classe}</Pill>}
                  {c.ml_confianca != null && <span className="text-[11px] ml-1 opacity-60">{Math.round(c.ml_confianca * 100)}%</span>}
                </Td>
                <Td>
                  {c.whisper_lang ? <Pill tone={c.whisper_lang === 'ca' ? 'green' : 'red'}>{c.whisper_lang}</Pill> : <span className="opacity-60 text-xs">—</span>}
                </Td>
                <Td>
                  {c.mbrainz_confirmed === true && <Pill tone="green">✓</Pill>}
                  {c.mbrainz_confirmed === false && <Pill tone="red">✗</Pill>}
                  {c.mbrainz_confirmed == null && <span className="opacity-60 text-xs">—</span>}
                  {c.mb_lyrics_language === 'cat' && (
                    <span className="ml-1 text-[10px] font-semibold text-emerald-700" title="MusicBrainz Work.language = cat">cat</span>
                  )}
                </Td>
                <Td>
                  {c.verificada ? <Pill tone="green">Verificada</Pill> : <Pill tone="gray">Pendent</Pill>}
                  {!c.activa && <Pill tone="red">Inactiva</Pill>}
                </Td>
                <Td className="text-right" onClick={e => e.stopPropagation()}>
                  <div className="flex flex-col items-end gap-0.5">
                    {c.deezer_id ? (
                      <a
                        href={`https://www.deezer.com/track/${c.deezer_id}`}
                        target="_blank"
                        rel="noopener"
                        className="text-xs underline text-tq-ink/70 hover:text-tq-ink whitespace-nowrap"
                        title="Escoltar a Deezer"
                      >
                        ▶ Deezer
                      </a>
                    ) : (
                      !c.spotify?.spotify_id && <span className="text-[11px] opacity-60">—</span>
                    )}
                    {c.spotify?.spotify_id && (
                      <a
                        href={`https://open.spotify.com/track/${c.spotify.spotify_id}`}
                        target="_blank"
                        rel="noopener"
                        className="text-xs underline text-tq-ink/70 hover:text-tq-ink whitespace-nowrap"
                        title="Escoltar a Spotify"
                      >
                        ▶ Spotify
                      </a>
                    )}
                  </div>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
        <Pagination meta={data} onPage={setPage} />
      </TableCard>
    </section>
  )
}
