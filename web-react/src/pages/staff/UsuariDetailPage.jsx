/**
 * UsuariDetailPage — /staff/usuaris/:pk
 *
 * Single user detail. Exposes two safe mutations (toggle-actiu,
 * reset-2FA). Toggling is_staff stays SSH-only by design.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import {
  Btn,
  PageHeader,
  Pill,
  Table,
  TableCard,
  Td,
  Th,
  THead,
  Tr,
} from '../../components/rd/surface'

export default function UsuariDetailPage() {
  const { pk } = useParams()
  const navigate = useNavigate()
  const [u, setU] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  function load() {
    api.get(`/staff/usuaris/${pk}/`).then(setU).catch(e => setErr(e.message))
  }
  useEffect(load, [pk])

  if (err) return <p className="text-red-300">{err}</p>
  if (!u) return <p className="text-white/70">Carregant…</p>

  async function toggleActiu() {
    if (!confirm(`${u.is_active ? 'Desactivar' : 'Reactivar'} ${u.email}?`)) return
    setBusy(true); setErr('')
    try {
      await api.post(`/staff/usuaris/${pk}/toggle-actiu/`)
      load()
    } catch (e) { setErr(e.payload?.error || e.message) } finally { setBusy(false) }
  }

  async function reset2fa() {
    if (!confirm(`Eliminar el 2FA de ${u.email}?`)) return
    setBusy(true); setErr('')
    try {
      await api.post(`/staff/usuaris/${pk}/reset-2fa/`)
      load()
    } catch (e) { setErr(e.payload?.error || e.message) } finally { setBusy(false) }
  }

  async function enviarResetPassword() {
    if (!confirm(`Enviar email de reset de contrasenya a ${u.email}?`)) return
    setBusy(true); setErr('')
    try {
      await api.post(`/staff/usuaris/${pk}/enviar-reset-password/`)
      alert(`Email enviat a ${u.email}.`)
    } catch (e) { setErr(e.payload?.error || e.message) } finally { setBusy(false) }
  }

  async function esborrar() {
    if (!confirm(`ESBORRAR DEFINITIVAMENT ${u.email}?\n\nAquesta acció és irreversible. Les seves publicacions i propostes s'eliminen en cascada.`)) return
    if (!confirm(`Segur? Escriu "ok" al següent prompt per continuar.`)) return
    const ok = prompt('Escriu "ok" per confirmar:')
    if (ok !== 'ok') return
    setBusy(true); setErr('')
    try {
      await api.post(`/staff/usuaris/${pk}/esborrar/`)
      navigate('/staff/usuaris')
    } catch (e) { setErr(e.payload?.error || e.message) } finally { setBusy(false) }
  }

  async function reenviarVerificacio() {
    if (!confirm(`Reenviar email de verificació a ${u.email}?`)) return
    setBusy(true); setErr('')
    try {
      await api.post(`/staff/usuaris/${pk}/reenviar-verificacio/`)
      alert(`Email de verificació enviat a ${u.email}.`)
    } catch (e) { setErr(e.payload?.error || e.message) } finally { setBusy(false) }
  }

  return (
    <section>
      <PageHeader
        title={u.email}
        subtitle={`pk=${u.pk} · ${u.username}`}
        right={
          <>
            <Btn tone="outline" size="md" onClick={() => navigate('/staff/usuaris')}>Tornar</Btn>
            {!u.is_staff && (
              <Btn tone={u.is_active ? 'danger' : 'primary'} size="md" onClick={toggleActiu} disabled={busy}>
                {u.is_active ? 'Desactivar' : 'Reactivar'}
              </Btn>
            )}
            {u.has_totp && (
              <Btn tone="danger" size="md" onClick={reset2fa} disabled={busy}>Reset 2FA</Btn>
            )}
            <Btn size="md" onClick={enviarResetPassword} disabled={busy}>
              Enviar reset de clau
            </Btn>
            {!u.is_active && (
              <Btn size="md" onClick={reenviarVerificacio} disabled={busy}>
                Reenviar verificació
              </Btn>
            )}
            {!u.is_staff && (
              <Btn tone="danger" size="md" onClick={esborrar} disabled={busy}>
                Esborrar usuari
              </Btn>
            )}
          </>
        }
      />
      {err && <p className="text-red-300 mb-3">{err}</p>}

      <div className="mb-4 flex flex-wrap gap-1">
        {u.is_active ? <Pill tone="green">Actiu</Pill> : <Pill tone="gray">Inactiu</Pill>}
        {u.is_staff && <Pill tone="yellow">Staff</Pill>}
        {u.has_totp && <Pill tone="green">2FA</Pill>}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <TableCard>
          <h2 className="p-3 font-semibold">Propostes d'artistes ({u.propostes.length})</h2>
          <Table>
            <THead><tr><Th>Nom</Th><Th>Estat</Th><Th>Data</Th></tr></THead>
            <tbody>
              {u.propostes.length === 0 && (
                <tr><td colSpan={3} className="px-3 py-4 text-sm opacity-60 text-center">Cap</td></tr>
              )}
              {u.propostes.map(p => (
                <Tr key={p.pk}>
                  <Td>
                    <Link className="underline" to={`/staff/propostes/${p.pk}`}>{p.nom}</Link>
                  </Td>
                  <Td><Pill tone={p.estat === 'aprovat' ? 'green' : p.estat === 'rebutjat' ? 'gray' : 'yellow'}>{p.estat}</Pill></Td>
                  <Td className="text-xs">{p.created_at?.slice(0, 10)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableCard>

        <TableCard>
          <h2 className="p-3 font-semibold">Sol·licituds de gestió ({u.sollicituds.length})</h2>
          <Table>
            <THead><tr><Th>Artista</Th><Th>Estat</Th><Th>Data</Th></tr></THead>
            <tbody>
              {u.sollicituds.length === 0 && (
                <tr><td colSpan={3} className="px-3 py-4 text-sm opacity-60 text-center">Cap</td></tr>
              )}
              {u.sollicituds.map(s => (
                <Tr key={s.pk}>
                  <Td>
                    <Link className="underline" to={`/artista/${s.artista.slug}`}>{s.artista.nom}</Link>
                  </Td>
                  <Td>
                    <Pill tone={s.estat === 'aprovat' ? 'green' : s.estat === 'rebutjat' ? 'gray' : 'yellow'}>{s.estat}</Pill>
                    {s.verificat && <Pill tone="green">Verificat</Pill>}
                  </Td>
                  <Td className="text-xs">{s.created_at?.slice(0, 10)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableCard>

        <TableCard>
          <h2 className="p-3 font-semibold">Audit sobre aquest usuari</h2>
          <Table>
            <THead><tr><Th>Data</Th><Th>Acció</Th><Th>Actor</Th></tr></THead>
            <tbody>
              {u.audit_sobre.length === 0 && (
                <tr><td colSpan={3} className="px-3 py-4 text-sm opacity-60 text-center">Cap acció.</td></tr>
              )}
              {u.audit_sobre.map(a => (
                <Tr key={a.pk}>
                  <Td className="text-xs">{a.created_at?.slice(0, 16).replace('T', ' ')}</Td>
                  <Td><Pill>{a.action}</Pill></Td>
                  <Td className="text-xs">{a.actor_email}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableCard>

        {u.is_staff && (
          <TableCard>
            <h2 className="p-3 font-semibold">Accions fetes per aquest usuari</h2>
            <Table>
              <THead><tr><Th>Data</Th><Th>Acció</Th><Th>Target</Th></tr></THead>
              <tbody>
                {u.audit_per_usuari.length === 0 && (
                  <tr><td colSpan={3} className="px-3 py-4 text-sm opacity-60 text-center">Cap.</td></tr>
                )}
                {u.audit_per_usuari.map(a => (
                  <Tr key={a.pk}>
                    <Td className="text-xs">{a.created_at?.slice(0, 16).replace('T', ' ')}</Td>
                    <Td><Pill>{a.action}</Pill></Td>
                    <Td className="text-xs">{a.target_label}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableCard>
        )}
      </div>
    </section>
  )
}
