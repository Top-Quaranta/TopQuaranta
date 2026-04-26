/**
 * PendentsPage — /staff/pendents
 *
 * The busiest staff flow: auto-discovered artists awaiting approval
 * or discard. Each row exposes inline fields for Deezer ID + location
 * (municipi cascade: territori → comarca → municipi) and two action
 * buttons. Approvals require either a new location input or an
 * existing one; discards delete the row when there are no verified
 * tracks, otherwise just lower pendent_review.
 *
 * The location dropdowns are populated lazily via the existing
 * /api/v1/localitzacio/* endpoints so we don't over-fetch on mount.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
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

function useDebounced(value, ms = 250) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

// LocationCascade is shared with ArtistaEditPage (and anywhere else
// staff needs to pin an ArtistaLocalitat). Kept in a separate module
// so the ALT-manual special case only lives in one place.
import LocationCascade from '../../components/staff/LocationCascade'

function Row({ a, onApproved, onDiscarded }) {
  const [deezerId, setDeezerId] = useState(a.deezer_ids[0] || '')
  const [loc, setLoc] = useState({
    territori: a.localitat?.territori || '',
    comarca: a.localitat?.comarca || '',
    municipi_id: a.localitat?.municipi_id || null,
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const hasExistingLoc = !!a.localitat

  async function aprovar() {
    setBusy(true)
    setErr('')
    try {
      const body = {}
      if (deezerId) body.deezer_id = deezerId
      if (loc.municipi_id) {
        body.municipi_id = loc.municipi_id
      } else if (loc.territori === 'ALT' && loc.manual) {
        // Free-text place outside the curated Municipi list. The
        // backend accepts `manual` as a shortcut that skips the
        // Municipi lookup and stores on ArtistaLocalitat.localitat_manual.
        body.manual = loc.manual
      }
      await api.post(`/staff/pendents/${a.pk}/aprovar/`, body)
      onApproved(a.pk)
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally {
      setBusy(false)
    }
  }

  async function descartar() {
    if (!confirm(`Descartar ${a.nom}?`)) return
    setBusy(true)
    setErr('')
    try {
      await api.post(`/staff/pendents/${a.pk}/descartar/`)
      onDiscarded(a.pk)
    } catch (e) {
      setErr(e.payload?.error || e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Tr>
      <Td>
        {/* Clicking the artist name opens the standard staff edit page
            — useful for fixing the name, Deezer IDs or localitats
            before approval. */}
        <Link
          to={`/staff/artistes/${a.pk}`}
          className="font-semibold underline hover:text-tq-yellow-deep"
        >
          {a.nom}
        </Link>
        <div className="text-xs opacity-60 flex flex-wrap items-center gap-1">
          {/* Drill-down: clicking the verified-track count opens the
              Cançons list pre-scoped to this artist + verificada=1. */}
          {a.nb_verif > 0 ? (
            <Link
              to={`/staff/cancons?artista_pk=${a.pk}&verificada=1`}
              className="underline hover:text-tq-ink"
            >
              {a.nb_verif} cançons verificades
            </Link>
          ) : (
            <span>0 cançons verificades</span>
          )}
          {a.n_propostes > 0 && (
            <>
              <span>·</span>
              <Pill tone="yellow">
                {a.n_propostes} {a.n_propostes === 1 ? 'proposta' : 'propostes'}
              </Pill>
            </>
          )}
          <span>·</span>
          <span>{a.font_descoberta}</span>
          <span>·</span>
          {/* External helpers so staff can cross-check a pendent
              artist against Viasona (Catalan music database) and
              Deezer (our metadata source) without leaving the row. */}
          <a
            href={`https://viasona.cat/cerca?que=${encodeURIComponent(a.nom)}`}
            target="_blank"
            rel="noopener"
            className="underline hover:text-tq-ink"
          >
            Viasona ↗
          </a>
          <span>·</span>
          <a
            href={`https://www.deezer.com/search/${encodeURIComponent(a.nom)}`}
            target="_blank"
            rel="noopener"
            className="underline hover:text-tq-ink"
          >
            Deezer ↗
          </a>
        </div>
        {hasExistingLoc && (
          <div className="text-[11px] text-tq-ink/60 mt-0.5">
            Ja té localitat:{' '}
            {a.localitat.municipi_nom ||
              `${a.localitat.manual} (manual)`}
          </div>
        )}
      </Td>
      <Td>
        <Input
          type="text"
          inputMode="numeric"
          placeholder="Deezer ID"
          value={deezerId}
          onChange={e => setDeezerId(e.target.value)}
          className="w-32"
        />
      </Td>
      <Td>
        {!hasExistingLoc && <LocationCascade value={loc} onChange={setLoc} />}
        {hasExistingLoc && (
          <span className="text-xs opacity-60">(no cal tornar-la a indicar)</span>
        )}
      </Td>
      <Td className="text-xs tabular-nums">
        {a.nb_similars_lastfm > 0 ? (
          <span
            className="font-semibold"
            style={{ color: 'var(--color-tq-yellow-deep)' }}
            title={`Recomanat per ${a.nb_similars_lastfm} artista(es) aprovats nostres a Last.fm`}
          >
            {a.nb_similars_lastfm}×
          </span>
        ) : (
          <span className="opacity-30">—</span>
        )}
      </Td>
      <Td className="text-right">
        {err && <div className="text-[11px] text-red-600 mb-1">{err}</div>}
        <div className="flex gap-1 justify-end">
          <Btn onClick={aprovar} disabled={busy}>
            Aprovar
          </Btn>
          <Btn tone="danger" onClick={descartar} disabled={busy}>
            Descartar
          </Btn>
        </div>
      </Td>
    </Tr>
  )
}

export default function PendentsPage() {
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState(null)
  const [q, setQ] = useState('')
  // Discovery-source filter (`font_descoberta`). Empty = all.
  const [font, setFont] = useState('')
  // Sort key. Empty = backend default; `similars_lastfm` orders by
  // Last.fm-network affinity descending (best for triaging
  // similar-artists discoveries).
  const [sort, setSort] = useState('')
  const dq = useDebounced(q)

  function load(p = page, cerca = dq) {
    setData(null)
    const params = new URLSearchParams({ page: p })
    if (cerca) params.set('q', cerca)
    if (font) params.set('font_descoberta', font)
    if (sort) params.set('sort', sort)
    api
      .get(`/staff/pendents/?${params}`)
      .then(setData)
      .catch(e => setError(e.message))
  }

  useEffect(() => {
    load(page, dq)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, dq, font, sort])

  // Resetting the page back to 1 every time the search changes keeps
  // the results coherent — otherwise a search with few hits would land
  // on an empty "page 3" view.
  useEffect(() => {
    setPage(1)
  }, [dq])

  function onResolved(pk) {
    setData(d =>
      d ? { ...d, results: d.results.filter(r => r.pk !== pk) } : d,
    )
  }

  return (
    <section>
      <PageHeader
        title="Artistes pendents"
        subtitle={
          data ? `${data.total} pendents de revisió` : 'Carregant…'
        }
      />
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Input
          placeholder="Cerca per nom d'artista…"
          value={q}
          onChange={e => setQ(e.target.value)}
          className="min-w-[260px]"
        />
        {q && (
          <button
            type="button"
            onClick={() => setQ('')}
            className="text-xs text-white/70 hover:text-white underline"
          >
            neteja
          </button>
        )}
        <Select value={font} onChange={e => { setPage(1); setFont(e.target.value) }}>
          <option value="">Font: qualsevol</option>
          <option value="lastfm_similar">Last.fm similar</option>
          <option value="proposta_usuari">Proposta d'usuari</option>
          <option value="manual">Manual</option>
          <option value="legacy">Legacy</option>
          <option value="viasona">Viasona</option>
          <option value="collaborador">Col·laborador</option>
          <option value="deezer_contributor">Deezer contributor</option>
        </Select>
        <Select value={sort} onChange={e => { setPage(1); setSort(e.target.value) }}>
          <option value="">Ordre per defecte</option>
          <option value="similars_lastfm">Similars Last.fm ↓</option>
        </Select>
      </div>
      {error && <p className="text-sm text-red-300 mb-4">{error}</p>}
      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Artista</Th>
              <Th>Deezer</Th>
              <Th>Localitat</Th>
              <Th title="Cops que aquest artista apareix com a similar a artist.getSimilar de Last.fm sobre algun artista aprovat nostre">Similars LFM</Th>
              <Th></Th>
            </tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <EmptyState>Cap artista pendent. 🎉</EmptyState>
                </td>
              </tr>
            )}
            {data?.results?.map(a => (
              <Row
                key={a.pk}
                a={a}
                onApproved={onResolved}
                onDiscarded={onResolved}
              />
            ))}
          </tbody>
        </Table>
        <Pagination meta={data} onPage={setPage} />
      </TableCard>
    </section>
  )
}
