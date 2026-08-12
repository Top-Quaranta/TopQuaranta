/**
 * StaffArtistesSenseYoutubePage — /staff/artistes/sense-youtube
 *
 * Human decision on ONE official YouTube channel per artist. Clone of
 * the sense-instagram workflow, with one difference that matters: the
 * answer has THREE outcomes, not two.
 *
 *   · a channel id      → we measure that lane too
 *   · "no en té"        → reviewed and done; Malalts genuinely has none
 *                         and must not sit in this queue forever
 *   · untouched         → still pending
 *
 * Why a person and not a heuristic: probing "Malalts" automatically
 * returns a padel channel and an events company, and "Montenegro" or
 * "Guerra" are worse. A wrong channel doesn't look wrong downstream —
 * it looks like a song with suspiciously many plays.
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

/** Anything the backend knows how to resolve: an id, a /channel/ URL or
 *  a handle. YouTube stopped showing the `UC…` id anywhere in its UI, so
 *  demanding it made this queue unusable — the handle is what you can
 *  actually copy out of the address bar. The backend resolves it for one
 *  quota unit and answers 400 if it can't. */
export function esCanalPlausible(value) {
  if (!value) return false
  const v = value.trim()
  return (
    /^UC[\w-]{20,30}$/.test(v) ||
    /youtube\.com\/channel\/UC[\w-]{20,30}/i.test(v) ||
    /@[\w.-]+/.test(v)
  )
}

function cercaYoutubeUrl(nom) {
  // Channel-scoped search: the operator lands on candidate channels
  // rather than on individual videos.
  const q = encodeURIComponent(nom)
  return `https://www.youtube.com/results?search_query=${q}&sp=EgIQAg%253D%253D`
}

function Row({ a, onDone }) {
  const [val, setVal] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const canSave = !busy && esCanalPlausible(val)

  async function desa(payload) {
    setBusy(true)
    setErr('')
    try {
      await api.patch(`/staff/artistes/${a.pk}/`, payload)
      onDone(a.pk)
    } catch (e) {
      setErr(e.message || 'Error desant.')
    } finally {
      setBusy(false)
    }
  }

  const nTop = a.n_top || 0

  return (
    <Tr>
      <Td>
        <Link
          to={`/staff/artistes/${a.pk}`}
          className="font-semibold underline hover:text-tq-yellow"
        >
          {a.nom}
        </Link>
        {a.youtube_url && (
          <a
            href={a.youtube_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-[11px] text-tq-yellow underline"
          >
            enllaç de MusicBrainz ↗
          </a>
        )}
      </Td>
      <Td>
        {/* Three states, because an empty cell reads as "has none" when it
            almost always means "discovery hasn't got here yet" — ~90
            artists a day out of 520. */}
        {a.youtube_channel_id ? (
          <Pill tone="green">Trobat</Pill>
        ) : a.youtube_provat ? (
          <Pill tone="gray">No en té</Pill>
        ) : (
          <span className="text-white/40" title="El cron encara no hi ha arribat">
            pendent
          </span>
        )}
      </Td>
      <Td>
        {nTop > 0 ? (
          <Pill tone={nTop >= 3 ? 'yellow' : 'gray'}>{nTop}×</Pill>
        ) : (
          <span className="text-white/40">—</span>
        )}
      </Td>
      <Td>
        <div className="flex flex-col gap-1">
          <Input
            placeholder="youtube.com/@nom, o l'id UC…"
            value={val}
            onChange={e => {
              setVal(e.target.value)
              setErr('')
            }}
            className="w-80"
          />
          {val && !esCanalPlausible(val) && (
            <p className="text-[11px] text-white/50">
              Enganxa l'enllaç del canal (youtube.com/@nom) o el seu id UC…
            </p>
          )}
          {err && <p className="text-[11px] text-red-400">{err}</p>}
        </div>
      </Td>
      <Td>
        <a
          href={cercaYoutubeUrl(a.nom)}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-tq-yellow underline hover:text-tq-yellow-deep whitespace-nowrap"
        >
          Cercar a YouTube ↗
        </a>
      </Td>
      <Td className="text-right">
        <div className="flex justify-end gap-2">
          <Btn
            variant="ghost"
            onClick={() =>
              desa({ youtube_canal_oficial: '', youtube_canal_revisat: true })
            }
            disabled={busy}
          >
            No en té
          </Btn>
          <Btn
            onClick={() =>
              desa({
                youtube_canal_oficial: val.trim(),
                youtube_canal_revisat: true,
              })
            }
            disabled={!canSave}
          >
            Desa
          </Btn>
        </div>
      </Td>
    </Tr>
  )
}

export default function StaffArtistesSenseYoutubePage() {
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState(null)
  const [q, setQ] = useState('')
  const dq = useDebounced(q)

  function load(p = page, cerca = dq) {
    setData(null)
    const params = new URLSearchParams({
      aprovat: '1',
      youtube: 'pendent',
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

  useEffect(() => {
    setPage(1)
  }, [dq])

  function onDone(pk) {
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
  const subtitle =
    total === undefined
      ? 'Carregant…'
      : `${total} artistes sense revisar. Ací va el canal PROPI de l'artista ` +
        `(el dels videoclips), no el «- Topic» / «- Tema», que ja el trobem sols. ` +
        `«No en té» també és una resposta vàlida i final.`

  return (
    <section>
      <PageHeader title="Canal oficial de YouTube" subtitle={subtitle} />
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Input
          placeholder="Cerca per nom d'artista…"
          value={q}
          onChange={e => setQ(e.target.value)}
          className="w-72"
        />
      </div>
      {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
      {data && data.results.length === 0 && (
        <EmptyState>Cap artista pendent de revisar.</EmptyState>
      )}
      {data && data.results.length > 0 && (
        <TableCard>
          <Table>
            <THead>
              <Tr>
                <Th>Artista</Th>
                <Th title="El canal automàtic de YouTube Music; el trobem sols">
                  Art Track
                </Th>
                <Th>Al top</Th>
                <Th>Canal oficial</Th>
                <Th></Th>
                <Th></Th>
              </Tr>
            </THead>
            <tbody>
              {data.results.map(a => (
                <Row key={a.pk} a={a} onDone={onDone} />
              ))}
            </tbody>
          </Table>
        </TableCard>
      )}
      {data && (
        <Pagination
          page={page}
          total={data.total}
          pageSize={data.page_size}
          onChange={setPage}
        />
      )}
    </section>
  )
}
