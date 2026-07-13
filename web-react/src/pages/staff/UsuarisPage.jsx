/**
 * UsuarisPage — /staff/usuaris
 *
 * Unified staff surface: every registered user, with filters for
 * active state, staff flag, and directory visibility. Each row shows
 * both account fields (email, username, 2FA, last login) and profile
 * fields (nom públic, rol, localitat, publicacions) and links to the
 * detail page where mutations live.
 *
 * "Mostrar/Ocultar directori" runs inline via the existing
 * `/staff/directori-usuaris/<id>/toggle/` endpoint.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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

export default function UsuarisPage() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [estat, setEstat] = useState('')
  const [rol, setRol] = useState('')
  const [directori, setDirectori] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(null)

  function load() {
    const params = new URLSearchParams({ q, estat, rol, directori, page })
    api.get(`/staff/usuaris/?${params}`).then(setData).catch(() => setData(null))
  }
  useEffect(load, [q, estat, rol, directori, page])

  async function toggleDirectori(e, usuari_id) {
    e.stopPropagation()
    setBusy(usuari_id)
    try {
      await api.post(`/staff/directori-usuaris/${usuari_id}/toggle/`)
      load()
    } finally {
      setBusy(null)
    }
  }

  return (
    <section>
      <PageHeader title="Usuaris" subtitle={data ? `${data.total} usuaris` : 'Carregant…'} />

      <div className="flex flex-wrap gap-2 mb-3">
        <Input aria-label="Cerca" placeholder="Cerca email / username / nom públic…" value={q} onChange={e => { setPage(1); setQ(e.target.value) }} />
        <Select aria-label="Estat" value={estat} onChange={e => { setPage(1); setEstat(e.target.value) }}>
          <option value="">Estat: tots</option>
          <option value="actius">Actius</option>
          <option value="inactius">Inactius</option>
        </Select>
        <Select aria-label="Rol musical" value={rol} onChange={e => { setPage(1); setRol(e.target.value) }}>
          <option value="">Rol: tots</option>
          <option value="staff">Staff</option>
          <option value="usuari">Usuari</option>
        </Select>
        <Select aria-label="Visibilitat al directori" value={directori} onChange={e => { setPage(1); setDirectori(e.target.value) }}>
          <option value="">Directori: tots</option>
          <option value="1">Al directori</option>
          <option value="0">Ocult</option>
        </Select>
      </div>

      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Usuari</Th>
              <Th>Perfil públic</Th>
              <Th>Localitat</Th>
              <Th>Estat</Th>
              <Th>Propostes</Th>
              <Th>Publicacions</Th>
              <Th>Directori</Th>
              <Th></Th>
            </tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr><td colSpan={8}><EmptyState>Cap usuari.</EmptyState></td></tr>
            )}
            {data?.results?.map(u => (
              <Tr key={u.pk} onClick={() => navigate(`/staff/usuaris/${u.pk}`)}>
                <Td>
                  <div className="font-semibold">{u.email}</div>
                  <div className="text-xs opacity-60">
                    {u.username} · registrat {u.date_joined?.slice(0, 10)}
                  </div>
                </Td>
                <Td>
                  {u.nom_public ? (
                    <span>{u.nom_public}</span>
                  ) : (
                    <span className="opacity-60">—</span>
                  )}
                  {u.rol_musical && (
                    <Pill tone="ink">{u.rol_musical}</Pill>
                  )}
                </Td>
                <Td className="text-xs">{u.localitat || <span className="opacity-60">—</span>}</Td>
                <Td>
                  {u.is_active ? <Pill tone="green">Actiu</Pill> : <Pill tone="gray">Inactiu</Pill>}
                  {u.is_staff && <Pill tone="yellow">Staff</Pill>}
                  {u.has_totp && <Pill tone="green">2FA</Pill>}
                  {u.obert_colaboracions && <Pill tone="yellow">Obert</Pill>}
                </Td>
                <Td>{u.n_propostes}</Td>
                <Td>{u.n_publicacions}</Td>
                <Td>
                  {u.visible_directori ? <Pill tone="green">Visible</Pill> : <Pill tone="gray">Ocult</Pill>}
                </Td>
                <Td className="text-right">
                  <Btn
                    tone={u.visible_directori ? 'danger' : 'primary'}
                    onClick={e => toggleDirectori(e, u.pk)}
                    disabled={busy === u.pk}
                  >
                    {u.visible_directori ? 'Ocultar' : 'Mostrar'}
                  </Btn>
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
