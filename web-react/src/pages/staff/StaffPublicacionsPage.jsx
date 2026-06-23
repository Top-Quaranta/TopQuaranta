/**
 * StaffPublicacionsPage — /staff/publicacions
 *
 * Moderation queue for user-authored publications. Filter by estat
 * (default: pendent); row expands to show full body + publicar /
 * rebutjar / despublicar actions with an optional staff note.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import Markdown from '../../components/Markdown'
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

function estatTone(e) {
  return (
    {
      esborrany: 'gray',
      pendent: 'yellow',
      publicat: 'green',
      rebutjat: 'red',
    }[e] || 'ink'
  )
}

export default function StaffPublicacionsPage() {
  const [q, setQ] = useState('')
  const [estat, setEstat] = useState('pendent')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [notes, setNotes] = useState({})
  const [busy, setBusy] = useState(null)

  function load() {
    const params = new URLSearchParams({ q, estat, page })
    api.get(`/staff/publicacions/?${params}`).then(setData).catch(() => setData(null))
  }
  useEffect(load, [q, estat, page])

  async function decidir(pub, action) {
    setBusy(pub.pk)
    try {
      await api.post(`/staff/publicacions/${pub.pk}/decidir/`, {
        action,
        notes_staff: notes[pub.pk] ?? pub.notes_staff ?? '',
      })
      load()
    } finally {
      setBusy(null)
    }
  }

  return (
    <section>
      <PageHeader
        title="Publicacions"
        subtitle={data ? `${data.total} entrades` : 'Carregant…'}
      />

      <div className="flex flex-wrap gap-2 mb-3">
        <Input aria-label="Cerca" placeholder="Cerca títol, cos o autor…" value={q} onChange={e => { setPage(1); setQ(e.target.value) }} />
        <Select aria-label="Estat" value={estat} onChange={e => { setPage(1); setEstat(e.target.value) }}>
          <option value="">Totes</option>
          {(data?.estat_choices || [
            ['esborrany', 'Esborrany'],
            ['pendent', 'Pendent'],
            ['publicat', 'Publicat'],
            ['rebutjat', 'Rebutjat'],
          ]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </Select>
      </div>

      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Data</Th>
              <Th>Autor</Th>
              <Th>Títol</Th>
              <Th>Visibilitat</Th>
              <Th>Estat</Th>
              <Th></Th>
            </tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr><td colSpan={6}><EmptyState>Cap publicació en aquest estat.</EmptyState></td></tr>
            )}
            {data?.results?.map(pub => (
              <>
                <Tr key={pub.pk} onClick={() => setExpanded(expanded === pub.pk ? null : pub.pk)}>
                  <Td className="text-xs whitespace-nowrap">{pub.created_at?.slice(0, 16).replace('T', ' ')}</Td>
                  <Td className="text-xs">
                    {pub.autor.nom_public}
                    {pub.autor.is_staff && <span className="ml-1 opacity-60">(staff)</span>}
                  </Td>
                  <Td className="font-semibold">{pub.titol}</Td>
                  <Td><Pill tone={pub.visibilitat === 'publica' ? 'yellow' : 'ink'}>{pub.visibilitat}</Pill></Td>
                  <Td><Pill tone={estatTone(pub.estat)}>{pub.estat}</Pill></Td>
                  <Td className="text-right" onClick={e => e.stopPropagation()}>
                    <Link to={`/comunitat/${pub.pk}`} className="text-xs underline opacity-70 hover:opacity-100">veure</Link>
                  </Td>
                </Tr>
                {expanded === pub.pk && (
                  <tr className="bg-tq-ink/5">
                    <td colSpan={6} className="p-4">
                      <div className="grid lg:grid-cols-[1fr_280px] gap-4">
                        <div>
                          <p className="text-[10px] uppercase tracking-wide opacity-60 mb-1">Cos</p>
                          <div className="text-sm bg-white text-tq-ink rounded p-3">
                            <Markdown>{pub.cos}</Markdown>
                          </div>
                        </div>
                        <div className="flex flex-col gap-2">
                          <label className="text-[10px] uppercase tracking-wide opacity-60">Notes staff (visibles a l'autor si es rebutja)</label>
                          <textarea
                            rows={4}
                            value={notes[pub.pk] ?? pub.notes_staff ?? ''}
                            onChange={e => setNotes(n => ({ ...n, [pub.pk]: e.target.value }))}
                            className="px-2 py-1.5 rounded border border-tq-ink/20 text-sm resize-y bg-white text-tq-ink"
                          />
                          {pub.estat !== 'publicat' && (
                            <Btn onClick={() => decidir(pub, 'publicar')} disabled={busy === pub.pk}>Publicar</Btn>
                          )}
                          {pub.estat !== 'rebutjat' && (
                            <Btn tone="danger" onClick={() => decidir(pub, 'rebutjar')} disabled={busy === pub.pk}>Rebutjar</Btn>
                          )}
                          {pub.estat === 'publicat' && (
                            <Btn tone="secondary" onClick={() => decidir(pub, 'despublicar')} disabled={busy === pub.pk}>Despublicar</Btn>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </Table>
        <Pagination meta={data} onPage={setPage} />
      </TableCard>
    </section>
  )
}
