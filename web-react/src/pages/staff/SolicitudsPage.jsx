/**
 * SolicitudsPage — /staff/solicituds
 *
 * UserArtista: users requesting to manage an existing artist profile.
 * Row actions: toggle verified / reject.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import {
  Btn,
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

export default function SolicitudsPage() {
  const [verificat, setVerificat] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(null)

  function load() {
    const params = new URLSearchParams({ verificat, page })
    api.get(`/staff/solicituds/?${params}`).then(setData).catch(() => setData(null))
  }
  useEffect(load, [verificat, page])

  async function doAction(pk, kind) {
    setBusy(pk)
    try {
      if (kind === 'toggle') await api.post(`/staff/solicituds/${pk}/toggle/`)
      else await api.post(`/staff/solicituds/${pk}/rebutjar/`)
      load()
    } finally { setBusy(null) }
  }

  return (
    <section>
      <PageHeader title="Sol·licituds de gestió" subtitle={data ? `${data.total} sol·licituds` : 'Carregant…'} />

      <div className="flex gap-2 mb-3">
        <Select aria-label="Verificat" value={verificat} onChange={e => { setPage(1); setVerificat(e.target.value) }}>
          <option value="">Totes</option>
          <option value="0">No verificades</option>
          <option value="1">Verificades</option>
        </Select>
      </div>

      <TableCard>
        <Table>
          <THead>
            <tr><Th>Artista</Th><Th>Usuari</Th><Th>Estat</Th><Th>Data</Th><Th></Th></tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr><td colSpan={5}><EmptyState>Cap sol·licitud.</EmptyState></td></tr>
            )}
            {data?.results?.map(ua => (
              <Tr key={ua.pk}>
                <Td>
                  <Link to={`/artista/${ua.artista.slug}`} className="underline font-semibold">{ua.artista.nom}</Link>
                </Td>
                <Td>{ua.usuari.email}</Td>
                <Td>
                  <Pill tone={ua.estat === 'aprovat' ? 'green' : ua.estat === 'rebutjat' ? 'gray' : 'yellow'}>{ua.estat}</Pill>
                  {ua.verificat && <Pill tone="green">Verificat</Pill>}
                </Td>
                <Td className="text-xs opacity-70">{ua.created_at?.slice(0, 10)}</Td>
                <Td className="text-right">
                  <div className="flex gap-1 justify-end">
                    <Btn onClick={() => doAction(ua.pk, 'toggle')} disabled={busy === ua.pk}>
                      {ua.verificat ? 'Desaprovar' : 'Aprovar'}
                    </Btn>
                    {ua.estat !== 'rebutjat' && (
                      <Btn tone="danger" onClick={() => doAction(ua.pk, 'rebutjar')} disabled={busy === ua.pk}>
                        Rebutjar
                      </Btn>
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
