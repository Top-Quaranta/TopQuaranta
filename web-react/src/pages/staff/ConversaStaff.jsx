/**
 * ConversaStaff — comments on a sol·licitud = the DM thread between the
 * requester and the TopQuaranta `admin` inbox. Staff write as
 * TopQuaranta; the user gets the usual «nou missatge» mail and answers
 * from /compte/missatges, which lands back here.
 */
import { useEffect, useState } from 'react'

import { api } from '../../lib/api'
import { Btn, TableCard, Textarea } from '../../components/rd/surface'

export default function ConversaStaff({ usuariPk, assumpte }) {
  const [msgs, setMsgs] = useState(null)
  const [cos, setCos] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  function reload() {
    api
      .get(`/staff/usuaris/${usuariPk}/conversa/`)
      .then(d => setMsgs(d.missatges))
      .catch(e => setErr(e.message))
  }
  useEffect(() => {
    if (usuariPk) reload()
  }, [usuariPk])

  if (!usuariPk) return null

  async function enviar(e) {
    e.preventDefault()
    setBusy(true)
    setErr('')
    try {
      await api.post(`/staff/usuaris/${usuariPk}/conversa/`, { cos, assumpte })
      setCos('')
      reload()
    } catch (e2) {
      setErr(e2.payload?.error || e2.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <TableCard className="p-4 mt-6">
      <h2 className="font-semibold mb-1">Comentaris amb l'usuari</h2>
      <p className="text-xs opacity-70 mb-3">
        S'envien com a TopQuaranta als seus missatges (rep un correu) i les
        respostes apareixen ací.
      </p>
      {msgs?.length === 0 && (
        <p className="text-sm opacity-60 mb-3">Encara no hi ha cap missatge.</p>
      )}
      <ul className="space-y-2 mb-3">
        {(msgs || []).map(m => (
          <li
            key={m.pk}
            className={`text-sm rounded p-2 ${m.meu ? 'bg-tq-yellow/15 ml-8' : 'bg-tq-ink/5 mr-8'}`}
          >
            <div className="text-xs opacity-60 mb-1">
              {m.meu ? 'TopQuaranta' : m.remitent?.username} ·{' '}
              {m.created_at?.slice(0, 16).replace('T', ' ')}
              {m.assumpte && <> · {m.assumpte}</>}
            </div>
            <p className="whitespace-pre-wrap">{m.cos}</p>
          </li>
        ))}
      </ul>
      <form onSubmit={enviar} className="flex flex-col gap-2">
        <Textarea
          value={cos}
          onChange={e => setCos(e.target.value)}
          placeholder="Escriu un comentari per a l'usuari…"
          aria-label="Comentari per a l'usuari"
        />
        {err && <p className="text-red-600 text-sm">{err}</p>}
        <div>
          <Btn type="submit" disabled={busy || !cos.trim()}>
            Enviar
          </Btn>
        </div>
      </form>
    </TableCard>
  )
}
