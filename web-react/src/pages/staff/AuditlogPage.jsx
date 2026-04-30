/**
 * AuditlogPage — /staff/auditlog
 *
 * Read-only view of StaffAuditLog: every destructive staff action.
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
} from '../../components/staff/StaffTable'

export default function AuditlogPage() {
  const [q, setQ] = useState('')
  const [actor, setActor] = useState('')
  const [action, setAction] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)

  useEffect(() => {
    const params = new URLSearchParams({ q, actor, action, page })
    api.get(`/staff/auditlog/?${params}`).then(setData).catch(() => setData(null))
  }, [q, actor, action, page])

  return (
    <section>
      <PageHeader title="Auditoria staff" subtitle={data ? `${data.total} accions` : 'Carregant…'} />

      <div className="flex flex-wrap gap-2 mb-3">
        <Input aria-label="Cerca" placeholder="Cerca etiqueta target…" value={q} onChange={e => { setPage(1); setQ(e.target.value) }} />
        <Input aria-label="Actor (email)" placeholder="Actor email…" value={actor} onChange={e => { setPage(1); setActor(e.target.value) }} />
        <Select aria-label="Acció" value={action} onChange={e => { setPage(1); setAction(e.target.value) }}>
          <option value="">Tots els tipus</option>
          {data?.action_choices?.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
        </Select>
      </div>

      <TableCard>
        <Table>
          <THead>
            <tr><Th>Data</Th><Th>Actor</Th><Th>Acció</Th><Th>Target</Th><Th>Extra</Th></tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr><td colSpan={5}><EmptyState>Cap acció registrada.</EmptyState></td></tr>
            )}
            {data?.results?.map(r => (
              <Tr key={r.pk}>
                <Td className="text-xs whitespace-nowrap">{r.created_at?.slice(0, 16).replace('T', ' ')}</Td>
                <Td className="text-xs">{r.actor_email}</Td>
                <Td><Pill>{r.action}</Pill></Td>
                <Td className="text-xs">{r.target_label} <span className="opacity-70">({r.target_type}#{r.target_id})</span></Td>
                <Td className="text-[11px] max-w-md">
                  {r.metadata && Object.keys(r.metadata).length > 0 && (
                    <code className="opacity-70 break-all">{JSON.stringify(r.metadata)}</code>
                  )}
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
