/**
 * StaffArtistesPage — /staff/artistes
 *
 * Approved-artist directory with filters (aprovat, deezer, territori,
 * search). Each row links to the edit page. Header has a "Nou artista"
 * button. Multi-select enables bulk-merge: pick a destí, the rest are
 * merged into it (cançons/àlbums/Deezer/HistorialRevisio/localitats).
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import {
  Btn,
  EmptyState,
  Input,
  PageHeader,
  Field,
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
import FilterPanel from '../../components/staff/FilterPanel'

const DEFAULTS = {
  aprovat: '1',
  deezer: '',
  territori: '',
  mb: '',
  // `homonim_sospitos`: '1' restricts to artists with at least one
  // Cançó rejected as `desvincular_artista` AND ≥1 still active.
  // Driven by the dashboard click-through; also exposed in the panel.
  homonim_sospitos: '',
  instagram: '',
  // Last.fm alias state — '' (qualsevol) / 'pendents' / 'confirmats' /
  // 'rebutjats'. Lets staff process the candidate queue produced by
  // `detectar_lastfm_aliases` without leaving the artistes list.
  lastfm_alias: '',
  sort: '',  // backend default = alphabetical
}

const TERRITORIS = [
  ['', 'Tots els territoris'],
  ['CAT', 'Catalunya'],
  ['VAL', 'País Valencià'],
  ['BAL', 'Illes Balears'],
  ['AND', 'Andorra'],
  ['CNO', 'Catalunya del Nord'],
  ['FRA', 'Franja de Ponent'],
  ['ALG', "L'Alguer"],
  ['PPCC', 'Països Catalans'],
  ['ALT', 'Altres'],
]

export default function StaffArtistesPage() {
  const navigate = useNavigate()
  const [urlParams] = useSearchParams()
  const [q, setQ] = useState(urlParams.get('q') || '')
  const [applied, setApplied] = useState({
    aprovat:          urlParams.get('aprovat')          ?? DEFAULTS.aprovat,
    deezer:           urlParams.get('deezer')           ?? DEFAULTS.deezer,
    territori:        urlParams.get('territori')        ?? DEFAULTS.territori,
    mb:               urlParams.get('mb')               ?? DEFAULTS.mb,
    homonim_sospitos: urlParams.get('homonim_sospitos') ?? DEFAULTS.homonim_sospitos,
    instagram:        urlParams.get('instagram')        ?? DEFAULTS.instagram,
    lastfm_alias:     urlParams.get('lastfm_alias')     ?? DEFAULTS.lastfm_alias,
    sort:             urlParams.get('sort')             ?? DEFAULTS.sort,
  })
  const {
    aprovat,
    deezer,
    territori,
    mb,
    homonim_sospitos,
    instagram,
    lastfm_alias,
    sort,
  } = applied
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)

  // Merge state. `sel` holds {pk → {pk, nom}} to keep names visible even
  // after the user paginates away.
  const [sel, setSel] = useState({})
  const [targetPk, setTargetPk] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    const params = new URLSearchParams({
      q, aprovat, deezer, territori, mb, homonim_sospitos, instagram, lastfm_alias, sort, page,
    })
    api.get(`/staff/artistes/?${params}`).then(setData).catch(() => setData(null))
  }, [q, aprovat, deezer, territori, mb, homonim_sospitos, instagram, lastfm_alias, sort, page])

  function toggleSel(a) {
    setSel(prev => {
      const next = { ...prev }
      if (next[a.pk]) {
        delete next[a.pk]
        if (targetPk === a.pk) setTargetPk(null)
      } else {
        next[a.pk] = { pk: a.pk, nom: a.nom }
      }
      return next
    })
  }

  const selList = Object.values(sel)
  const canMerge = selList.length >= 2 && targetPk != null

  async function fusionar() {
    if (!canMerge) return
    const target = sel[targetPk]
    const sources = selList.filter(x => x.pk !== targetPk)
    const msgConf = `Fusionar ${sources.length} artista(es) dins "${target.nom}"?\n\n` +
      sources.map(s => `· ${s.nom} (#${s.pk})`).join('\n') +
      `\n\nAquesta acció és irreversible.`
    if (!confirm(msgConf)) return
    setBusy(true); setMsg('')
    try {
      const out = await api.post('/staff/artistes/fusionar/', {
        target_pk: target.pk,
        source_pks: sources.map(s => s.pk),
      })
      setMsg(`Fet. ${out.fusionats} artistes fusionats dins "${out.target_nom}".`)
      setSel({}); setTargetPk(null)
      // Refresh the list.
      const params = new URLSearchParams({ q, aprovat, deezer, territori, mb, homonim_sospitos, page })
      api.get(`/staff/artistes/?${params}`).then(setData)
    } catch (e) {
      setMsg(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  return (
    <section>
      <PageHeader
        title="Artistes"
        subtitle={data ? `${data.total} artistes` : 'Carregant…'}
        right={
          <Btn tone="primary" size="md" onClick={() => navigate('/staff/artistes/crear')}>
            + Nou artista
          </Btn>
        }
      />

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Input
          placeholder="Cerca per nom…"
          value={q}
          onChange={e => { setPage(1); setQ(e.target.value) }}
          className="flex-1 min-w-[14rem]"
        />
        <FilterPanel
          applied={applied}
          defaults={DEFAULTS}
          onApply={next => { setApplied(next); setPage(1) }}
        >
          {(p, setP) => (
            <>
              <Field label="Estat d'aprovació">
                <Select aria-label="Estat d'aprovació" value={p.aprovat} onChange={e => setP({ aprovat: e.target.value })}>
                  <option value="1">Aprovats</option>
                  <option value="0">No aprovats</option>
                  <option value="">Tots</option>
                </Select>
              </Field>
              <Field label="Deezer">
                <Select aria-label="Deezer" value={p.deezer} onChange={e => setP({ deezer: e.target.value })}>
                  <option value="">Qualsevol</option>
                  <option value="si">Té Deezer</option>
                  <option value="no">Sense Deezer</option>
                </Select>
              </Field>
              <Field label="Territori">
                <Select aria-label="Territori" value={p.territori} onChange={e => setP({ territori: e.target.value })}>
                  {TERRITORIS.map(([c, l]) => (
                    <option key={c} value={c}>{l}</option>
                  ))}
                </Select>
              </Field>
              <Field label="MusicBrainz">
                <Select aria-label="MusicBrainz" value={p.mb} onChange={e => setP({ mb: e.target.value })}>
                  <option value="">Qualsevol</option>
                  <option value="amb_mbid">Amb MBID</option>
                  <option value="sense_mbid">Sense MBID (qualsevol)</option>
                  <option value="provat_sense_mbid">Provat sense MBID</option>
                  <option value="mai_provat">Mai provat</option>
                  <option value="bloquejat">Auto-match bloquejat</option>
                  <option value="dissolt">Dissolts</option>
                </Select>
              </Field>
              <Field label="Instagram">
                <Select aria-label="Instagram" value={p.instagram} onChange={e => setP({ instagram: e.target.value })}>
                  <option value="">Qualsevol</option>
                  <option value="si">Té Instagram</option>
                  <option value="no">Sense Instagram</option>
                </Select>
              </Field>
              <Field label="Aliases Last.fm">
                <Select
                  aria-label="Aliases Last.fm"
                  value={p.lastfm_alias}
                  onChange={e => setP({ lastfm_alias: e.target.value })}
                >
                  <option value="">Qualsevol</option>
                  <option value="pendents">Té candidats per revisar</option>
                  <option value="confirmats">Té aliases confirmats</option>
                  <option value="rebutjats">Té candidats rebutjats</option>
                </Select>
              </Field>
              <Field label="Ordenació">
                <Select aria-label="Ordenació" value={p.sort} onChange={e => setP({ sort: e.target.value })}>
                  <option value="">Alfabètic (A→Z)</option>
                  <option value="cancons_tops_desc">Cançons al top ↓ (més populars)</option>
                </Select>
              </Field>
              <label className="flex items-center gap-2 text-xs font-semibold text-tq-ink/80 mt-1">
                <input
                  type="checkbox"
                  checked={p.homonim_sospitos === '1'}
                  onChange={e => setP({ homonim_sospitos: e.target.checked ? '1' : '' })}
                />
                Només homonímia Deezer sospitosa
              </label>
            </>
          )}
        </FilterPanel>
      </div>

      {selList.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-3 p-2 bg-tq-yellow/90 text-tq-ink rounded">
          <span className="text-sm font-semibold">
            {selList.length} seleccionats
          </span>
          <Select aria-label="Destí de la fusió" value={targetPk ?? ''} onChange={e => setTargetPk(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Destí de la fusió…</option>
            {selList.map(s => (
              <option key={s.pk} value={s.pk}>{s.nom} (#{s.pk})</option>
            ))}
          </Select>
          <Btn tone="danger" onClick={fusionar} disabled={!canMerge || busy}>
            Fusionar dins del destí
          </Btn>
          <Btn tone="secondary" onClick={() => { setSel({}); setTargetPk(null) }} disabled={busy}>
            Netejar
          </Btn>
          <span className="text-xs opacity-80">
            El destí manté el PK. Cançons, àlbums, Deezer, localitats, UserArtista i HistorialRevisio es traspassen.
          </span>
        </div>
      )}

      {msg && <p className="text-sm text-white/80 mb-3">{msg}</p>}

      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th className="w-8"></Th>
              <Th>Nom</Th>
              {sort === 'cancons_tops_desc' && <Th title="Cançons distintes que han aparegut al top 40 (qualsevol territori, qualsevol setmana)">Top 40</Th>}
              <Th>Territoris</Th>
              <Th>Localitat</Th>
              <Th>Deezer</Th>
              <Th>IG</Th>
              <Th>MB</Th>
              <Th title="Cops que aquest artista apareix com a similar a artist.getSimilar de Last.fm sobre algun aprovat">LFM ~</Th>
              <Th>Estat</Th>
              <Th></Th>
            </tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr><td colSpan={sort === 'cancons_tops_desc' ? 11 : 10}><EmptyState>Cap artista.</EmptyState></td></tr>
            )}
            {data?.results?.map(a => (
              <Tr key={a.pk} onClick={() => navigate(`/staff/artistes/${a.pk}`)}>
                <Td onClick={e => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={!!sel[a.pk]}
                    onChange={() => toggleSel(a)}
                    aria-label={`Seleccionar ${a.nom}`}
                  />
                </Td>
                <Td>
                  <div className="font-semibold">
                    {a.nom}
                    {a.te_homonims && (
                      <span
                        className="ml-1 text-[10px] font-semibold text-amber-700"
                        title="Hi ha un altre artista amb el mateix nom (ignorant accents i puntuació). Compte: possible homònim (cas Crim)."
                      >
                        ⚠ homònim
                      </span>
                    )}
                  </div>
                  {a.genere && <div className="text-xs opacity-60">{a.genere}</div>}
                </Td>
                {sort === 'cancons_tops_desc' && (
                  <Td className="text-xs font-semibold tabular-nums">
                    {a.n_cancons_tops ?? '—'}
                  </Td>
                )}
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {a.territoris.map(t => <Pill key={t}>{t}</Pill>)}
                  </div>
                </Td>
                <Td className="text-xs">
                  {a.localitat ? (a.localitat.municipi_nom || a.localitat.manual) : <span className="opacity-60">—</span>}
                </Td>
                <Td className="text-xs">{a.deezer_ids.length ? a.deezer_ids.join(', ') : <span className="opacity-60">—</span>}</Td>
                <Td onClick={e => e.stopPropagation()}>
                  {a.instagram_url ? (
                    <a
                      href={a.instagram_url}
                      target="_blank"
                      rel="noopener"
                      className="text-xs underline opacity-80 hover:opacity-100"
                      title={a.instagram_url}
                    >
                      ↗
                    </a>
                  ) : (
                    <span className="opacity-60 text-xs">—</span>
                  )}
                </Td>
                <Td>
                  {a.musicbrainz_id ? (
                    <Pill tone="green">MBID</Pill>
                  ) : a.mb_last_sync ? (
                    <Pill tone="gray">Sense MBID</Pill>
                  ) : (
                    <span className="opacity-60 text-xs">—</span>
                  )}
                  {a.mb_end_date && (
                    <Pill tone="red">Dissolt {a.mb_end_date.slice(0, 4)}</Pill>
                  )}
                </Td>
                <Td className="text-xs tabular-nums">
                  {a.nb_similars_lastfm > 0 ? (
                    <span
                      className="font-semibold"
                      style={{ color: 'var(--color-tq-warning-deep)' }}
                      title={`Recomanat per ${a.nb_similars_lastfm} artista(es) aprovats nostres`}
                    >
                      {a.nb_similars_lastfm}×
                    </span>
                  ) : (
                    <span className="opacity-60">—</span>
                  )}
                </Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {a.aprovat && <Pill tone="green">Aprovat</Pill>}
                    {!a.aprovat && a.pendent_review && <Pill tone="yellow">Pendent</Pill>}
                    {!a.aprovat && !a.pendent_review && <Pill tone="gray">Descartat</Pill>}
                    {a.lastfm_aliases_pendents > 0 && (
                      <Pill tone="yellow">
                        {a.lastfm_aliases_pendents} alies a revisar
                      </Pill>
                    )}
                    {a.lastfm_aliases_confirmats > 0 && (
                      <Pill tone="green">
                        +{a.lastfm_aliases_confirmats} alies
                      </Pill>
                    )}
                  </div>
                </Td>
                <Td className="text-right">
                  <Link
                    to={`/artista/${a.slug}`}
                    onClick={e => e.stopPropagation()}
                    className="text-xs underline opacity-70 hover:opacity-100"
                  >
                    perfil públic
                  </Link>
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
