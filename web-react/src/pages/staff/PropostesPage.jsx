/**
 * PropostesPage — /staff/propostes
 *
 * User-submitted proposals for new artists. Filter by estat. Each
 * row links to the detail page where staff can accept/reject.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import {
  EmptyState,
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

export default function PropostesPage() {
  const navigate = useNavigate()
  const [estat, setEstat] = useState('pendent')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)

  useEffect(() => {
    const params = new URLSearchParams({ estat, page })
    api.get(`/staff/propostes/?${params}`).then(setData).catch(() => setData(null))
  }, [estat, page])

  return (
    <section>
      <PageHeader title="Propostes d'artistes" subtitle={data ? `${data.total} propostes` : 'Carregant…'} />

      <div className="flex gap-2 mb-3">
        <Select aria-label="Estat" value={estat} onChange={e => { setPage(1); setEstat(e.target.value) }}>
          <option value="pendent">Pendents</option>
          <option value="aprovat">Aprovades</option>
          <option value="rebutjat">Rebutjades</option>
          <option value="">Totes</option>
        </Select>
      </div>

      <TableCard>
        <Table>
          <THead>
            <tr><Th>Artista</Th><Th>Proposant</Th><Th>Estat</Th><Th>Data</Th></tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr><td colSpan={4}><EmptyState>Cap proposta.</EmptyState></td></tr>
            )}
            {data?.results?.map(p => (
              <Tr key={p.pk} onClick={() => navigate(`/staff/propostes/${p.pk}`)}>
                <Td className="font-semibold">{p.nom}</Td>
                <Td>{p.usuari.email}</Td>
                <Td>
                  <Pill tone={p.estat === 'aprovat' ? 'green' : p.estat === 'rebutjat' ? 'gray' : 'yellow'}>{p.estat}</Pill>
                </Td>
                <Td className="text-xs opacity-70">{p.created_at?.slice(0, 10)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
        <Pagination meta={data} onPage={setPage} />
      </TableCard>
    </section>
  )
}
