/**
 * FeedbackPage — /staff/feedback
 *
 * Inbox of user-filed corrections. Each entry keeps the URL the
 * reporter was on plus a typed target (artista/album/canço + pk +
 * slug) so staff can jump straight to the related edit page.
 *
 * Actions per entry:
 *   - Jump to the related edit page (if target_pk is known)
 *   - Mark resolved / reopen, with optional staff notes
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
} from '../../components/staff/StaffTable'

function targetEditPath(t) {
  if (!t.target_pk) return null
  switch (t.target_type) {
    case 'artista': return `/staff/artistes/${t.target_pk}`
    case 'album':   return `/staff/albums/${t.target_pk}`
    case 'canco':   return `/staff/cancons/${t.target_pk}`
    default:        return null
  }
}

function publicPath(t) {
  if (!t.target_slug) return t.url
  switch (t.target_type) {
    case 'artista': return `/artista/${t.target_slug}`
    case 'album':   return `/album/${t.target_slug}`
    case 'canco':   return `/canco/${t.target_slug}`
    default:        return t.url
  }
}

export default function FeedbackPage() {
  const [q, setQ] = useState('')
  const [resolt, setResolt] = useState('0')
  const [targetType, setTargetType] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [notes, setNotes] = useState({})

  function load() {
    const params = new URLSearchParams({ q, resolt, target_type: targetType, page })
    api.get(`/staff/feedback/?${params}`).then(setData).catch(() => setData(null))
  }
  useEffect(load, [q, resolt, targetType, page])

  async function toggle(fb) {
    setBusy(fb.pk)
    try {
      await api.post(`/staff/feedback/${fb.pk}/resolve/`, {
        resolt: !fb.resolt,
        notes_staff: notes[fb.pk] ?? fb.notes_staff,
      })
      load()
    } finally {
      setBusy(null)
    }
  }

  return (
    <section>
      <PageHeader title="Feedback d'usuaris" subtitle={data ? `${data.total} entrades` : 'Carregant…'} />

      <div className="flex flex-wrap gap-2 mb-3">
        <Input aria-label="Cerca" placeholder="Cerca…" value={q} onChange={e => { setPage(1); setQ(e.target.value) }} />
        <Select aria-label="Estat (resolt / pendent)" value={resolt} onChange={e => { setPage(1); setResolt(e.target.value) }}>
          <option value="0">Pendents</option>
          <option value="1">Resoltes</option>
          <option value="">Totes</option>
        </Select>
        <Select aria-label="Tipus de target" value={targetType} onChange={e => { setPage(1); setTargetType(e.target.value) }}>
          <option value="">Qualsevol target</option>
          <option value="artista">Artista</option>
          <option value="album">Àlbum</option>
          <option value="canco">Cançó</option>
          <option value="altres">Altres</option>
        </Select>
      </div>

      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Data</Th>
              <Th>Usuari</Th>
              <Th>Target</Th>
              <Th>Missatge</Th>
              <Th>Estat</Th>
              <Th></Th>
            </tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr><td colSpan={6}><EmptyState>Cap feedback.</EmptyState></td></tr>
            )}
            {data?.results?.map(fb => (
              <>
                <Tr key={fb.pk} onClick={() => setExpanded(expanded === fb.pk ? null : fb.pk)}>
                  <Td className="text-xs whitespace-nowrap">
                    {fb.created_at?.slice(0, 16).replace('T', ' ')}
                  </Td>
                  <Td className="text-xs">{fb.usuari.email}</Td>
                  <Td>
                    <Pill>{fb.target_type}</Pill>
                    <div className="text-xs mt-1">
                      {fb.target_label || <span className="opacity-70">(sense nom)</span>}
                    </div>
                  </Td>
                  <Td className="text-sm max-w-md">
                    <p className="line-clamp-2">{fb.missatge}</p>
                  </Td>
                  <Td>
                    {fb.resolt ? <Pill tone="green">Resolta</Pill> : <Pill tone="yellow">Pendent</Pill>}
                  </Td>
                  <Td className="text-right" onClick={e => e.stopPropagation()}>
                    {targetEditPath(fb) && (
                      <Link
                        to={targetEditPath(fb)}
                        className="text-xs underline mr-2 opacity-80 hover:opacity-100"
                      >
                        Editar
                      </Link>
                    )}
                    <Link
                      to={publicPath(fb)}
                      className="text-xs underline opacity-60 hover:opacity-100"
                    >
                      ↗ pàgina
                    </Link>
                  </Td>
                </Tr>
                {expanded === fb.pk && (
                  <tr className="bg-tq-ink/5">
                    <td colSpan={6} className="p-4">
                      <div className="grid md:grid-cols-[1fr_240px] gap-4">
                        <div>
                          <p className="text-[10px] uppercase tracking-wide opacity-60 mb-1">Missatge complet</p>
                          <p className="text-sm whitespace-pre-wrap">{fb.missatge}</p>
                          <p className="text-[11px] opacity-60 mt-3">
                            URL original: <code className="opacity-80 break-all">{fb.url}</code>
                          </p>
                        </div>
                        <div className="flex flex-col gap-2">
                          <label className="text-[10px] uppercase tracking-wide opacity-60">
                            Notes staff
                          </label>
                          <textarea
                            rows={4}
                            value={notes[fb.pk] ?? fb.notes_staff ?? ''}
                            onChange={e => setNotes(n => ({ ...n, [fb.pk]: e.target.value }))}
                            className="px-2 py-1.5 rounded border border-tq-ink/20 text-sm resize-y bg-white text-tq-ink"
                            placeholder="Notes internes opcionals…"
                          />
                          <Btn
                            tone={fb.resolt ? 'secondary' : 'primary'}
                            onClick={() => toggle(fb)}
                            disabled={busy === fb.pk}
                          >
                            {fb.resolt ? 'Reobrir' : 'Marcar com a resolta'}
                          </Btn>
                          {fb.resolt && fb.resolt_per && (
                            <p className="text-[11px] opacity-60">
                              Resolta per {fb.resolt_per.email}
                              {fb.resolt_at && ` el ${fb.resolt_at.slice(0, 10)}`}
                            </p>
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
