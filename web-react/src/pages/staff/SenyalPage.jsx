/**
 * SenyalPage — /staff/senyal
 *
 * Raw daily Last.fm signal (playcount + listeners). Filterable by
 * date and "mena" (errors / corrections / confirmed). Each row with
 * corregit=True can be "accepted" — future drifts are silenced.
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
  Select,
  Table,
  TableCard,
  Td,
  Th,
  THead,
  Tr,
} from '../../components/rd/surface'

export default function SenyalPage() {
  const [q, setQ] = useState('')
  const [data, setData] = useState('')
  const [mena, setMena] = useState('')
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState(null)
  const [busy, setBusy] = useState(null)

  function load() {
    const params = new URLSearchParams({ q, data, mena, page })
    api.get(`/staff/senyal/?${params}`).then(setRows).catch(() => setRows(null))
  }
  useEffect(load, [q, data, mena, page])

  async function acceptar(cancoPk) {
    setBusy(cancoPk)
    try {
      await api.post(`/staff/senyal/${cancoPk}/acceptar-correccio/`)
      load()
    } finally { setBusy(null) }
  }

  return (
    <section>
      <PageHeader title="Senyal diari" subtitle={rows ? `${rows.total} rows` : 'Carregant…'} />

      <div className="flex flex-wrap gap-2 mb-3">
        <Input aria-label="Cerca" placeholder="Cerca…" value={q} onChange={e => { setPage(1); setQ(e.target.value) }} />
        <Input aria-label="Data" type="date" value={data} onChange={e => { setPage(1); setData(e.target.value) }} />
        <Select aria-label="Mena de senyal" value={mena} onChange={e => { setPage(1); setMena(e.target.value) }}>
          <option value="">Tots</option>
          <option value="errors">Errors</option>
          <option value="correccions">Correccions</option>
          <option value="confirmats">Confirmats</option>
        </Select>
      </div>

      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Data</Th>
              <Th>Cançó</Th>
              <Th>Artista</Th>
              <Th>Plays</Th>
              <Th>Listeners</Th>
              <Th>Estat</Th>
              <Th></Th>
            </tr>
          </THead>
          <tbody>
            {rows?.results?.length === 0 && (
              <tr><td colSpan={7}><EmptyState>Cap dada.</EmptyState></td></tr>
            )}
            {rows?.results?.map(r => (
              <Tr key={r.pk}>
                <Td className="text-xs">{r.data}</Td>
                <Td>
                  {r.canco_pk ? (
                    <Link
                      to={`/staff/cancons/${r.canco_pk}`}
                      className="underline hover:text-tq-yellow-deep"
                    >
                      {r.canco_nom}
                    </Link>
                  ) : r.canco_nom}
                </Td>
                <Td>
                  {r.artista_pk ? (
                    <Link
                      to={`/staff/artistes/${r.artista_pk}`}
                      className="underline hover:text-tq-yellow-deep"
                    >
                      {r.artista_nom}
                    </Link>
                  ) : r.artista_nom}
                </Td>
                <Td className="text-xs">{r.lastfm_playcount?.toLocaleString()}</Td>
                <Td className="text-xs">{r.lastfm_listeners?.toLocaleString()}</Td>
                <Td>
                  {r.error && <Pill tone="red">Error</Pill>}
                  {r.corregit && <Pill tone="yellow">Corregit</Pill>}
                  {r.lastfm_confirmed && <Pill tone="green">Confirmat</Pill>}
                </Td>
                <Td className="text-right">
                  {r.corregit && !r.lastfm_confirmed && (
                    <Btn onClick={() => acceptar(r.canco_pk)} disabled={busy === r.canco_pk}>
                      Acceptar correcció
                    </Btn>
                  )}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
        <Pagination meta={rows} onPage={setPage} />
      </TableCard>
    </section>
  )
}
