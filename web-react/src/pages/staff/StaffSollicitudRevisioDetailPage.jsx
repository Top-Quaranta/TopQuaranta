/**
 * StaffSollicitudRevisioDetailPage — /staff/sollicituds-revisio/:pk
 *
 * Workbench detail for one SolicitudRevisio: header with metadata
 * + actions; two tables (Pendents, Rebutjades). The Reconsiderar
 * button per rebutjada row uses ConfirmDialog to make the cron
 * implication explicit. Resoldre opens a modal with a free-text
 * note.
 */
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../../lib/api'
import { Badge, ConfirmDialog } from '../../components/ui'
import Alert from '../../components/ui/Alert'
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
} from '../../components/staff/StaffTable'

const ESTAT_TONE = {
  pendent: 'yellow',
  revisada: 'blue',
  resolta: 'green',
}

const MOTIU_TONE = {
  no_catala: 'default',
  album_incorrecte: 'warning',
  artista_incorrecte: 'warning',
  no_musica: 'danger',
}
const MOTIU_LABEL = {
  no_catala: 'No és en català',
  album_incorrecte: 'Àlbum incorrecte',
  artista_incorrecte: 'Artista incorrecte',
  no_musica: 'No és música',
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`
}

export default function StaffSollicitudRevisioDetailPage() {
  const { pk } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [confirmReb, setConfirmReb] = useState(null) // row to reconsider
  const [confirmResoldre, setConfirmResoldre] = useState(false)
  const [nota, setNota] = useState('')
  const [feedback, setFeedback] = useState(null)

  function reload() {
    setError(null)
    api
      .get(`/staff/sollicituds-revisio/${pk}/`)
      .then(setData)
      .catch(e => setError(e.message || 'Error'))
  }

  useEffect(reload, [pk])

  if (error) return <Alert tone="danger">{error}</Alert>
  if (!data)
    return <div className="h-24 mt-6 bg-white/10 rounded animate-pulse" />

  async function handleMarcarEnRevisio() {
    setBusy(true)
    try {
      await api.post(`/staff/sollicituds-revisio/${pk}/marcar-en-revisio/`)
      setFeedback({ tone: 'success', msg: 'Marcat com en revisió.' })
      reload()
    } catch (e) {
      setFeedback({
        tone: 'danger',
        msg: e.payload?.error || e.message || 'Error',
      })
    } finally {
      setBusy(false)
    }
  }

  async function handleResoldre() {
    setBusy(true)
    try {
      await api.post(`/staff/sollicituds-revisio/${pk}/resoldre/`, { nota })
      setFeedback({
        tone: 'success',
        msg: 'Sol·licitud marcada com resolta. El gestor rebrà un email.',
      })
      setConfirmResoldre(false)
      setNota('')
      reload()
    } catch (e) {
      setFeedback({
        tone: 'danger',
        msg: e.payload?.error || e.message || 'Error',
      })
    } finally {
      setBusy(false)
    }
  }

  async function handleReconsiderar(historial_pk) {
    setBusy(true)
    try {
      await api.post(
        `/staff/sollicituds-revisio/${pk}/reconsiderar-rebutjada/`,
        { historial_pk }
      )
      setFeedback({
        tone: 'success',
        msg: 'Rebutjada reconsiderada. El cron la re-ingerirà al pròxim tick.',
      })
      setConfirmReb(null)
      reload()
    } catch (e) {
      setFeedback({
        tone: 'danger',
        msg: e.payload?.error || e.message || 'Error',
      })
    } finally {
      setBusy(false)
    }
  }

  const resolta = data.estat === 'resolta'
  const pendent = data.estat === 'pendent'

  return (
    <section className="max-w-6xl mx-auto">
      <PageHeader
        title={`Sol·licitud #${data.pk} — ${data.artista.nom}`}
        subtitle={
          <span>
            <Link
              to={`/artista/${data.artista.slug}`}
              className="underline text-tq-yellow"
            >
              Veure pàgina pública
            </Link>{' '}
            ·{' '}
            <Link
              to="/staff/sollicituds-revisio/"
              className="underline opacity-80"
            >
              ← Llista
            </Link>
          </span>
        }
        right={
          <>
            {pendent && (
              <Btn onClick={handleMarcarEnRevisio} disabled={busy}>
                Marcar com en revisió
              </Btn>
            )}
            {!resolta && (
              <Btn
                tone="primary"
                onClick={() => setConfirmResoldre(true)}
                disabled={busy}
              >
                Marcar com resolta
              </Btn>
            )}
            <Pill tone={ESTAT_TONE[data.estat] || 'ink'}>{data.estat}</Pill>
          </>
        }
      />

      <div className="bg-white/5 border border-white/10 rounded-lg p-4 text-sm text-white/80 mb-4 space-y-1">
        <p>
          <strong className="text-white">Gestor:</strong>{' '}
          {data.gestor.username} ({data.gestor.email})
        </p>
        <p>
          <strong className="text-white">Creada:</strong>{' '}
          {data.created_at && fmtDate(data.created_at)}
        </p>
        {resolta && (
          <>
            <p>
              <strong className="text-white">Resolta:</strong>{' '}
              {fmtDate(data.resolt_at)} per{' '}
              <em>{data.resolt_per?.username || '—'}</em>
            </p>
            {data.nota_resolucio && (
              <div className="mt-2">
                <strong className="text-white">Nota del staff:</strong>
                <p className="mt-1 whitespace-pre-wrap text-white/90">
                  {data.nota_resolucio}
                </p>
              </div>
            )}
          </>
        )}
      </div>

      {feedback && (
        <div className="mb-4">
          <Alert tone={feedback.tone}>{feedback.msg}</Alert>
        </div>
      )}

      {/* ── Pendents ── */}
      <h2 className="text-lg font-semibold text-white mt-6 mb-2">
        Pendents ({data.pendents.length})
      </h2>
      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Cançó</Th>
              <Th>Àlbum</Th>
              <Th>Data llançament</Th>
              <Th>Estat</Th>
              <Th></Th>
            </tr>
          </THead>
          <tbody>
            {data.pendents.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="p-4 text-center text-tq-ink/60 text-sm"
                >
                  Cap cançó pendent en aquesta sol·licitud.
                </td>
              </tr>
            )}
            {data.pendents.map(c =>
              c.missing ? (
                <Tr
                  key={`miss-${c.pk}`}
                  className="opacity-40 italic"
                >
                  <Td colSpan={5} className="text-sm">
                    Cançó #{c.pk} esborrada del sistema.
                  </Td>
                </Tr>
              ) : (
                <Tr key={c.pk}>
                  <Td>{c.nom}</Td>
                  <Td className="opacity-70">{c.album_nom || '—'}</Td>
                  <Td className="opacity-70">{fmtDate(c.data_llancament)}</Td>
                  <Td>
                    <Pill tone={c.verificada ? 'green' : 'yellow'}>
                      {c.verificada ? 'verificada' : 'no verificada'}
                    </Pill>
                  </Td>
                  <Td className="text-right">
                    <Link to={`/staff/cancons/${c.pk}`}>
                      <Btn>Obrir a admin</Btn>
                    </Link>
                  </Td>
                </Tr>
              )
            )}
          </tbody>
        </Table>
      </TableCard>

      {/* ── Rebutjades ── */}
      <h2 className="text-lg font-semibold text-white mt-6 mb-2">
        Rebutjades ({data.rebutjades.length})
      </h2>
      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Cançó</Th>
              <Th>Àlbum</Th>
              <Th>Motiu original</Th>
              <Th>ISRC · Deezer</Th>
              <Th></Th>
            </tr>
          </THead>
          <tbody>
            {data.rebutjades.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="p-4 text-center text-tq-ink/60 text-sm"
                >
                  Cap rebutjada en aquesta sol·licitud.
                </td>
              </tr>
            )}
            {data.rebutjades.map(r => (
              <Tr
                key={`r-${r.historial_pk}`}
                className={!r.historial_present ? 'opacity-40' : ''}
              >
                <Td>{r.nom}</Td>
                <Td className="opacity-70">{r.album_nom || '—'}</Td>
                <Td>
                  <Badge variant={MOTIU_TONE[r.motiu] || 'default'}>
                    {MOTIU_LABEL[r.motiu] || r.motiu}
                  </Badge>
                </Td>
                <Td className="text-xs opacity-70">
                  {r.isrc || '—'} · {r.deezer_id || '—'}
                </Td>
                <Td className="text-right">
                  {!r.historial_present ? (
                    <span
                      className="text-xs italic opacity-70"
                      title="HistorialRevisio podat — només queda el snapshot."
                    >
                      Snapshot només
                    </span>
                  ) : r.reconsiderada ? (
                    <Pill tone="green">Reconsiderada</Pill>
                  ) : (
                    <Btn onClick={() => setConfirmReb(r)} disabled={busy}>
                      Reconsiderar
                    </Btn>
                  )}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </TableCard>

      {/* ── Modals ── */}
      <ConfirmDialog
        open={!!confirmReb}
        title="Reconsiderar rebutjada"
        body={
          <>
            Aquesta cançó tornarà a aparèixer al pipeline al pròxim cron
            d'<code>obtenir_novetats</code>. El gestor no en serà
            notificat explícitament; quan torni, podràs verificar-la al
            admin habitual.
          </>
        }
        confirmLabel="Reconsiderar"
        severity="warning"
        onConfirm={() => handleReconsiderar(confirmReb.historial_pk)}
        onCancel={() => setConfirmReb(null)}
      />

      <ConfirmDialog
        open={confirmResoldre}
        title="Marcar com resolta"
        body={
          <div className="space-y-2">
            <p>
              El gestor rebrà un email amb el resum + la teva nota.
              Aquesta acció no es pot desfer.
            </p>
            <textarea
              value={nota}
              onChange={e => setNota(e.target.value)}
              placeholder="Nota per al gestor (opcional)…"
              rows={4}
              className="w-full px-3 py-2 rounded-md text-sm border border-gray-300 focus:outline-none focus:ring-2 focus:ring-tq-yellow"
            />
          </div>
        }
        confirmLabel="Marcar com resolta"
        severity="danger"
        requireCheckbox
        checkboxLabel="Entenc que aquesta acció notifica el gestor i no es pot desfer."
        onConfirm={handleResoldre}
        onCancel={() => {
          setConfirmResoldre(false)
          setNota('')
        }}
      />
    </section>
  )
}
