/**
 * StaffSollicitudsRevisioPage — /staff/sollicituds-revisio
 *
 * Workbench landing for the new Sprint Workflow Sol·licituds. Lists
 * SolicitudRevisio rows with filters (estat, artista_pk) and pagination
 * (20). Default filter = `estat=pendent` so the staff sees the queue
 * immediately.
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

const ESTAT_TONE = {
  pendent: 'yellow',
  revisada: 'blue',
  resolta: 'green',
}

function fmtRelative(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 60) return 'ara mateix'
  if (diff < 3600) return `fa ${Math.floor(diff / 60)} min`
  if (diff < 86400) return `fa ${Math.floor(diff / 3600)} h`
  const days = Math.floor(diff / 86400)
  if (days < 30) return `fa ${days} dia${days === 1 ? '' : 's'}`
  return d.toLocaleDateString('ca-ES')
}

export default function StaffSollicitudsRevisioPage() {
  const [estat, setEstat] = useState('pendent')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setData(null)
    setError(null)
    const params = new URLSearchParams({ estat, page })
    api
      .get(`/staff/sollicituds-revisio/?${params}`)
      .then(setData)
      .catch(e => setError(e.message || 'Error'))
  }, [estat, page])

  return (
    <section className="max-w-6xl mx-auto">
      <PageHeader
        title="Sol·licituds de revisió"
        subtitle={
          data
            ? `${data.total} sol·licitud${data.total === 1 ? '' : 's'} en aquest filtre · ${data.n_pendents_total} pendent${data.n_pendents_total === 1 ? '' : 's'} en total`
            : 'Carregant…'
        }
      />

      <div className="flex gap-2 mb-3">
        <Select
          aria-label="Estat"
          value={estat}
          onChange={e => {
            setPage(1)
            setEstat(e.target.value)
          }}
        >
          <option value="pendent">Pendent</option>
          <option value="revisada">En revisió</option>
          <option value="resolta">Resolta</option>
          <option value="totes">Totes</option>
        </Select>
      </div>

      {error && (
        <div className="bg-red-900/30 text-red-200 px-4 py-2 rounded mb-3 text-sm">
          {error}
        </div>
      )}

      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Artista</Th>
              <Th>Gestor</Th>
              <Th>Pendents</Th>
              <Th>Rebutjades</Th>
              <Th>Creada</Th>
              <Th>Estat</Th>
              <Th></Th>
            </tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr>
                <td colSpan={7}>
                  <EmptyState>
                    {estat === 'pendent'
                      ? 'Cap sol·licitud pendent. Quan un gestor en demani una, apareixerà aquí.'
                      : 'Cap sol·licitud amb aquest filtre.'}
                  </EmptyState>
                </td>
              </tr>
            )}
            {data?.results?.map(s => (
              <Tr key={s.pk}>
                <Td>
                  <Link
                    to={`/artista/${s.artista.slug}`}
                    className="underline font-semibold"
                  >
                    {s.artista.nom}
                  </Link>
                </Td>
                <Td>
                  <span className="text-sm">{s.gestor.username}</span>
                  <span className="block text-xs opacity-60">
                    {s.gestor.email}
                  </span>
                </Td>
                <Td className="tabular-nums">{s.n_pendents}</Td>
                <Td className="tabular-nums">{s.n_rebutjades}</Td>
                <Td className="text-xs opacity-70" title={s.created_at}>
                  {fmtRelative(s.created_at)}
                </Td>
                <Td>
                  <Pill tone={ESTAT_TONE[s.estat] || 'ink'}>{s.estat}</Pill>
                </Td>
                <Td className="text-right">
                  <Link to={`/staff/sollicituds-revisio/${s.pk}/`}>
                    <Btn>Obrir →</Btn>
                  </Link>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
        <Pagination
          meta={
            data
              ? {
                  // Pagination expects {page, num_pages, total,
                  // has_previous, has_next}. Our endpoint emits a
                  // subset; derive the rest from page/n_pages.
                  page: data.page,
                  num_pages: data.n_pages,
                  total: data.total,
                  has_previous: data.page > 1,
                  has_next: data.page < data.n_pages,
                }
              : null
          }
          onPage={setPage}
        />
      </TableCard>
    </section>
  )
}
