/**
 * StaffArtistesSenseInstagramPage — /staff/artistes/sense-instagram
 *
 * Inline-edit workflow for filling in `Artista.instagram_url` on
 * approved artists that don't have one yet. Ordered by impact
 * (distinct TopSetmanal rows across all their cançons) so the staff
 * works through the high-leverage ones first.
 *
 * Mirrors the PendentsPage row pattern: each row has its own input
 * state and a single primary action ("Desa"). On success the row
 * removes itself from the list (it no longer matches `instagram=no`).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import {
  Btn,
  EmptyState,
  Input,
  PageHeader,
  Pagination,
  Pill,
  Table,
  TableCard,
  Td,
  Th,
  THead,
  Tr,
} from '../../components/rd/surface'

function useDebounced(value, ms = 250) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function isPlausibleInstagramUrl(value) {
  // Frontend gate: must start with https:// and contain instagram.com.
  // Backend still validates URLField + http(s) scheme via SOCIAL_LINK_FIELDS.
  if (!value) return false
  const v = value.trim()
  return v.startsWith('https://') && v.includes('instagram.com')
}

function googleInstagramSearchUrl(nom) {
  const q = encodeURIComponent(`site:instagram.com "${nom}"`)
  return `https://www.google.com/search?q=${q}`
}

function Row({ a, onSaved }) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const valid = isPlausibleInstagramUrl(url)
  const canSave = !busy && valid

  async function desa(payload) {
    setBusy(true)
    setErr('')
    try {
      await api.patch(`/staff/artistes/${a.pk}/`, payload)
      onSaved(a.pk)
    } catch (e) {
      setErr(e.message || 'Error desant.')
    } finally {
      setBusy(false)
    }
  }

  const nTop = a.n_top || 0
  const nVives = a.n_cancons_vives || 0

  return (
    <Tr>
      <Td>
        <Link
          to={`/staff/artistes/${a.pk}`}
          className="font-semibold underline hover:text-tq-yellow"
        >
          {a.nom}
        </Link>
        {/* Context, not decoration: this artist is here because Meta
            refused their old handle, so the answer is probably a NEW
            account — not "no en té". */}
        {a.instagram_rebutjat_url && (
          <p className="text-[11px] text-red-400">
            Instagram va refusar {a.instagram_rebutjat_url.replace(/^https?:\/\/(www\.)?instagram\.com\//, '@').replace(/\/$/, '')} — busca'n el compte nou
          </p>
        )}
      </Td>
      <Td>
        {nTop > 0 ? (
          // `yellow` (brand) for ≥3 — the "worth chasing first"
          // signal. `gray` for the rest. Pill tones available:
          // ink/yellow/green/red/gray (StaffTable.jsx:99).
          <Pill tone={nTop >= 3 ? 'yellow' : 'gray'}>{nTop}×</Pill>
        ) : (
          <span className="text-white/40">—</span>
        )}
      </Td>
      <Td>
        {nVives > 0 ? (
          <Pill tone="gray">{nVives}</Pill>
        ) : (
          <span className="text-white/40">—</span>
        )}
      </Td>
      <Td>
        <div className="flex flex-col gap-1">
          <Input
            type="url"
            inputMode="url"
            placeholder="https://www.instagram.com/..."
            value={url}
            onChange={e => { setUrl(e.target.value); setErr('') }}
            className="w-80"
          />
          {err && (
            <p className="text-[11px] text-red-400">{err}</p>
          )}
        </div>
      </Td>
      <Td>
        <a
          href={googleInstagramSearchUrl(a.nom)}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-tq-yellow underline hover:text-tq-yellow-deep whitespace-nowrap"
        >
          Cercar a Google ↗
        </a>
      </Td>
      <Td className="text-right">
        <div className="flex justify-end gap-2">
          {/* Third state, same as the YouTube queue: plenty of small
              artists simply have no Instagram, and without this they'd
              come back every single pass. */}
          <Btn
            variant="ghost"
            onClick={() => desa({ instagram_revisat: true })}
            disabled={busy}
          >
            No en té
          </Btn>
          <Btn
            onClick={() => desa({ instagram_url: url.trim() })}
            disabled={!canSave}
          >
            Desa
          </Btn>
        </div>
      </Td>
    </Tr>
  )
}

export default function StaffArtistesSenseInstagramPage() {
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState(null)
  const [q, setQ] = useState('')
  const dq = useDebounced(q)

  function load(p = page, cerca = dq) {
    setData(null)
    const params = new URLSearchParams({
      aprovat: '1',
      instagram: 'pendent',
      include_n_top: '1',
      sort: '-n_top',
      page: String(p),
    })
    if (cerca) params.set('q', cerca)
    api
      .get(`/staff/artistes/?${params}`)
      .then(setData)
      .catch(e => setError(e.message))
  }

  useEffect(() => {
    load(page, dq)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, dq])

  // Reset to page 1 when the search changes so the user doesn't land
  // on an empty page 3.
  useEffect(() => {
    setPage(1)
  }, [dq])

  function onSaved(pk) {
    // Optimistic remove: after the PATCH the row no longer matches
    // `instagram=no`, so it shouldn't sit in the list. Decrement the
    // total so the subtitle stays honest until the next fetch.
    setData(d =>
      d
        ? {
            ...d,
            results: d.results.filter(r => r.pk !== pk),
            total: Math.max(0, (d.total || 0) - 1),
          }
        : d,
    )
  }

  const total = data?.total
  const subtitle = (() => {
    if (total === undefined) return 'Carregant…'
    return `${total} artistes sense revisar. «No en té» també és una resposta: ` +
      `molts artistes menuts no en tenen. Ordenats per cançons al top i, a ` +
      `igualtat, per cançons actives.`
  })()

  return (
    <section>
      <PageHeader title="Artistes sense Instagram" subtitle={subtitle} />
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
      </div>
      {error && <p className="text-sm text-red-300 mb-4">{error}</p>}
      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Artista</Th>
              <Th title="Cançons d'aquest artista que han aparegut al top alguna vegada (distinct TopSetmanal)">Top</Th>
              <Th title="Cançons vives (verificades i actives) on l'artista és principal o col·laborador">Cançons actives</Th>
              <Th>Instagram URL</Th>
              <Th>Cerca</Th>
              <Th></Th>
            </tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <EmptyState>Cap artista pendent d'Instagram. 🎉</EmptyState>
                </td>
              </tr>
            )}
            {data?.results?.map(a => (
              <Row key={a.pk} a={a} onSaved={onSaved} />
            ))}
          </tbody>
        </Table>
        <Pagination meta={data} onPage={setPage} />
      </TableCard>
    </section>
  )
}
