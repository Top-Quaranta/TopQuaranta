/**
 * MissatgesPage — /comunitat/missatges
 *
 * Inbox view: list of conversations (grouped by "altre usuari") with
 * unread counters. Clicking one expands the thread inline. Replies and
 * net-new messages share the composer at the bottom.
 */
import { useState } from 'react'
import { Link, useSearchParams, Navigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import useApi from '../hooks/useApi'

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('ca', { day: 'numeric', month: 'short' }) +
    ' · ' + d.toLocaleTimeString('ca', { hour: '2-digit', minute: '2-digit' })
}

function Conversa({ c, active, onOpen }) {
  const last = c.darrer_missatge
  return (
    <button
      type="button"
      onClick={() => onOpen(c.altre.pk)}
      className={
        'w-full text-left px-3 py-3 border-b border-white/10 flex items-center gap-3 ' +
        (active ? 'bg-white/10' : 'hover:bg-white/5')
      }
    >
      {c.altre.imatge_url ? (
        <img src={c.altre.imatge_url} alt="" className="w-10 h-10 rounded-full object-cover" />
      ) : (
        <div className="w-10 h-10 rounded-full bg-tq-yellow/20 flex items-center justify-center text-tq-yellow font-bold">
          {(c.altre.nom_public || c.altre.username || '?')[0].toUpperCase()}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <div className="font-semibold text-sm truncate">
            {c.altre.nom_public || c.altre.username}
          </div>
          <div className="text-[10px] text-white/50 shrink-0">
            {fmtDate(last.created_at)}
          </div>
        </div>
        <div className="text-xs text-white/60 truncate">
          {last.meu && <span className="opacity-60">Tu: </span>}
          {last.cos}
        </div>
      </div>
      {c.no_llegits > 0 && (
        <span className="text-[11px] font-bold bg-tq-yellow text-tq-ink rounded-full px-2 py-0.5">
          {c.no_llegits}
        </span>
      )}
    </button>
  )
}

function Thread({ altrePk, onSent }) {
  const { data, error: loadErr, reload } = useApi(`/missatges/amb/${altrePk}/`)
  const [assumpte, setAssumpte] = useState('')
  const [cos, setCos] = useState('')
  const [busy, setBusy] = useState(false)
  const [sendErr, setSendErr] = useState('')

  async function enviar(e) {
    e.preventDefault()
    if (!cos.trim()) return
    setBusy(true); setSendErr('')
    try {
      await api.post('/missatges/nou/', {
        destinatari_pk: altrePk,
        assumpte: assumpte.trim(),
        cos,
      })
      setCos(''); setAssumpte('')
      reload()
      onSent?.()
    } catch (e) {
      setSendErr(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  const err = sendErr || loadErr
  if (err && !data) return <p className="text-red-300 p-4">{err}</p>
  if (!data) return <p className="text-white/60 p-4">Carregant…</p>

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-white/10 px-4 py-3 flex items-center gap-3">
        {data.altre.imatge_url ? (
          <img src={data.altre.imatge_url} alt="" className="w-9 h-9 rounded-full object-cover" />
        ) : (
          <div className="w-9 h-9 rounded-full bg-tq-yellow/20 flex items-center justify-center text-tq-yellow font-bold">
            {(data.altre.nom_public || data.altre.username || '?')[0].toUpperCase()}
          </div>
        )}
        <div className="font-semibold">
          {data.altre.nom_public || data.altre.username}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {data.missatges.length === 0 && (
          <p className="text-center text-white/50 text-sm">Cap missatge encara. Escriu el primer!</p>
        )}
        {data.missatges.map(m => (
          <div key={m.pk} className={'flex ' + (m.meu ? 'justify-end' : 'justify-start')}>
            <div className={
              'max-w-[80%] rounded-xl px-3 py-2 text-sm ' +
              (m.meu ? 'bg-tq-yellow text-tq-ink' : 'bg-white/10 text-white')
            }>
              {m.assumpte && (
                <div className="font-semibold text-[11px] uppercase tracking-wide opacity-70 mb-1">
                  {m.assumpte}
                </div>
              )}
              <div className="whitespace-pre-wrap">{m.cos}</div>
              <div className="text-[10px] opacity-60 mt-1">{fmtDate(m.created_at)}</div>
            </div>
          </div>
        ))}
      </div>
      <form onSubmit={enviar} className="border-t border-white/10 p-3 flex flex-col gap-2">
        <input
          type="text"
          value={assumpte}
          onChange={e => setAssumpte(e.target.value)}
          placeholder="Assumpte (opcional)"
          maxLength={200}
          className="px-3 py-2 rounded bg-white/5 border border-white/10 text-sm"
        />
        <div className="flex gap-2">
          <textarea
            value={cos}
            onChange={e => setCos(e.target.value)}
            placeholder="Escriu un missatge…"
            rows={2}
            maxLength={10000}
            className="flex-1 px-3 py-2 rounded bg-white/5 border border-white/10 text-sm resize-y"
          />
          <button
            type="submit"
            disabled={busy || !cos.trim()}
            className="px-4 bg-tq-yellow text-tq-ink rounded font-semibold text-sm disabled:opacity-50"
          >
            Enviar
          </button>
        </div>
      </form>
    </div>
  )
}

export default function MissatgesPage() {
  const { profile, loading } = useAuth()
  const [params, setParams] = useSearchParams()
  const { data: inbox, error: err, reload: loadInbox } = useApi(
    profile && !loading ? '/missatges/' : null,
  )

  const altrePk = params.get('amb')

  if (loading) return null
  if (!profile) return <Navigate to="/compte/accedir?next=/comunitat/missatges" replace />

  function openConversa(pk) {
    setParams({ amb: String(pk) })
    // Unread → 0 on open. Wait for the read-mark POST to land before
    // refetching the inbox so the count drops cleanly.
    setTimeout(loadInbox, 300)
  }

  return (
    <section className="max-w-5xl mx-auto text-white">
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-2xl font-bold">Missatges</h1>
        {inbox?.no_llegits_total > 0 && (
          <span className="bg-tq-yellow text-tq-ink text-xs font-bold rounded-full px-2 py-0.5">
            {inbox.no_llegits_total} nous
          </span>
        )}
      </div>
      {err && <p className="text-red-300 mb-3 text-sm">{err}</p>}
      <div className="grid md:grid-cols-[300px_1fr] gap-0 border border-white/10 rounded-lg overflow-hidden min-h-[500px] bg-tq-ink">
        <div className="border-r border-white/10 overflow-y-auto">
          {!inbox && <p className="p-4 text-white/60 text-sm">Carregant…</p>}
          {inbox?.results?.length === 0 && (
            <div className="p-6 text-center text-white/60 text-sm">
              Cap conversa. Escriu a algú des del seu <Link to="/comunitat/directori" className="underline">perfil al directori</Link>.
            </div>
          )}
          {inbox?.results?.map(c => (
            <Conversa
              key={c.altre.pk}
              c={c}
              active={String(c.altre.pk) === altrePk}
              onOpen={openConversa}
            />
          ))}
        </div>
        <div>
          {altrePk ? (
            <Thread altrePk={altrePk} onSent={loadInbox} />
          ) : (
            <div className="flex items-center justify-center h-full text-white/60 text-sm p-6 text-center">
              Tria una conversa o inicia'n una des del directori.
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
