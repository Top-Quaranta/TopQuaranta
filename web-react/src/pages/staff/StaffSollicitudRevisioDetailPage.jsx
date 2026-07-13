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
} from '../../components/rd/surface'

const ESTAT_TONE = {
  pendent: 'yellow',
  revisada: 'blue',
  resolta: 'green',
}
const ESTAT_LABEL = {
  pendent: 'Pendent',
  revisada: 'En revisió',
  resolta: 'Resolta',
}

// Action-only labels — cause / when-to-use lives in
// docs/architecture/staff.md section 5. Tones reflect blast
// radius: cançó (default) < àlbum (warning) < artista (danger).
const MOTIU_TONE = {
  desvincular_canco: 'default',
  desvincular_album: 'warning',
  desvincular_artista: 'danger',
}
const MOTIU_LABEL = {
  desvincular_canco: 'Cançó desvinculada',
  desvincular_album: 'Àlbum desvinculat',
  desvincular_artista: 'Artista desvinculat',
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
      setFeedback({
        tone: 'success',
        msg: 'Has començat a revisar aquesta sol·licitud.',
      })
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
        msg:
          'Cançó tornada al pipeline. El cron la re-ingerirà al pròxim tick i ' +
          "apareixerà al panell habitual de cançons pendents per a la teva " +
          'aprovació o rebuig.',
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
                Començar a revisar
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
            <Pill tone={ESTAT_TONE[data.estat] || 'ink'}>
              {ESTAT_LABEL[data.estat] || data.estat}
            </Pill>
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
                    <Pill tone="green">Tornada al pipeline</Pill>
                  ) : (
                    <Btn onClick={() => setConfirmReb(r)} disabled={busy}>
                      Tornar al pipeline
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
        title="Tornar la cançó al pipeline?"
        body={
          <>
            <p>
              La cançó tornarà a aparèixer al staff queue al pròxim cron
              d'<code>obtenir_novetats</code> (normalment diari). Allà
              podràs aprovar-la o tornar-la a rebutjar al panell habitual
              de cançons pendents.
            </p>
            <p className="mt-2 text-tq-ink/70">
              Aquesta acció <strong>NOMÉS</strong> treu la cançó de la
              blacklist; no l'aprova ni la verifica.
            </p>
          </>
        }
        confirmLabel="Tornar al pipeline"
        severity="warning"
        onConfirm={() => handleReconsiderar(confirmReb.historial_pk)}
        onCancel={() => setConfirmReb(null)}
      />

      <ConfirmDialog
        open={confirmResoldre}
        title="Marcar com resolta"
        body={
          <div className="space-y-2">
            <textarea
              value={nota}
              onChange={e => setNota(e.target.value)}
              placeholder="Nota per al gestor (opcional)…"
              rows={4}
              className="w-full px-3 py-2 rounded-md text-sm border border-gray-300 focus:outline-none focus:ring-2 focus:ring-tq-yellow"
            />
            <p className="text-xs text-tq-ink/70">
              Resoldre tanca aquesta sol·licitud i envia un email al
              gestor amb la nota que escriguis. <strong>NO modifica
              l'estat de verificació de les cançons</strong>; les
              aprovacions o rebuigs es fan al panell habitual de cançons
              pendents.
            </p>
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
