/**
 * HistorialPage — /staff/historial
 *
 * Read-only log of approve/reject decisions.
 */
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import {
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

export default function HistorialPage() {
  const [q, setQ] = useState('')
  const [decisio, setDecisio] = useState('')
  const [motiu, setMotiu] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)

  useEffect(() => {
    const params = new URLSearchParams({ q, decisio, motiu, page })
    api.get(`/staff/historial/?${params}`).then(setData).catch(() => setData(null))
  }, [q, decisio, motiu, page])

  return (
    <section>
      <PageHeader title="Historial de decisions" subtitle={data ? `${data.total} entrades` : 'Carregant…'} />

      <div className="flex flex-wrap gap-2 mb-3">
        <Input aria-label="Cerca" placeholder="Cerca…" value={q} onChange={e => { setPage(1); setQ(e.target.value) }} />
        <Select aria-label="Decisió" value={decisio} onChange={e => { setPage(1); setDecisio(e.target.value) }}>
          <option value="">Decisió: totes</option>
          <option value="aprovada">Aprovades</option>
          <option value="rebutjada">Rebutjades</option>
        </Select>
        <Select aria-label="Motiu" value={motiu} onChange={e => { setPage(1); setMotiu(e.target.value) }}>
          <option value="">Motiu: qualsevol</option>
          {/* MOTIUS_REBUIG arrives as [value, label] tuples. */}
          {data?.motius?.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </Select>
      </div>

      <TableCard>
        <Table>
          <THead>
            <tr><Th>Data</Th><Th>Cançó</Th><Th>Artista</Th><Th>Decisió</Th><Th>Motiu</Th></tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr><td colSpan={5}><EmptyState>Cap entrada.</EmptyState></td></tr>
            )}
            {data?.results?.map(h => (
              <Tr key={h.pk}>
                <Td className="text-xs">{h.created_at?.slice(0, 16).replace('T', ' ')}</Td>
                <Td>{h.canco_nom}</Td>
                <Td>{h.artista_nom}</Td>
                <Td>
                  <Pill tone={h.decisio === 'aprovada' ? 'green' : 'gray'}>{h.decisio}</Pill>
                </Td>
                <Td className="text-xs">{h.motiu}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
        <Pagination meta={data} onPage={setPage} />
      </TableCard>
    </section>
  )
}
