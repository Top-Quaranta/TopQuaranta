/**
 * ChannelView — shared house-style template for a single distribution
 * channel (slice 1 of the distribution-views redistribution).
 *
 * Pulls a simple channel (Mastodon / Bluesky / Telegram) out of the
 * monolithic /staff/social cockpit into its own page. The template
 * paints from CHANNEL_DESCRIPTORS[canal] into fixed slots: header
 * (name + effective state + pause toggle), auth/credentials, recent
 * publications, diagnostics. Channel-specific config slots can be
 * added to the descriptor later without touching this file.
 *
 * Data comes from the two existing cockpit endpoints (`/staff/social/`
 * for config + credentials + the SocialPost list, and
 * `/staff/social/estat-canals/` for the honest effective state + last
 * send). Recent publications reuse that shared list filtered
 * client-side by platform; the unified, server-paginated publications
 * table lands in slice 2 and this slot will point at it.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import {
  Btn,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Pill,
  Table,
  TableCard,
  Td,
  Th,
  THead,
  Tr,
} from '../../../components/staff/StaffTable'
import { CHANNEL_DESCRIPTORS } from './channelDescriptors'

const EFECTIU = {
  actiu: { tone: 'green', label: 'Actiu' },
  pausat_global: { tone: 'gray', label: 'Pausat pel mestre' },
  pausat_canal: { tone: 'red', label: 'Pausat (canal)' },
}
const STATUS = {
  pendent: { tone: 'yellow', label: 'Pendent' },
  publicat: { tone: 'green', label: 'Publicat' },
  error: { tone: 'red', label: 'Error' },
  omes: { tone: 'gray', label: 'Omès' },
}

export default function ChannelView({ canal }) {
  const desc = CHANNEL_DESCRIPTORS[canal]
  const [data, setData] = useState(null)
  const [estat, setEstat] = useState(null)
  const [busy, setBusy] = useState(false)
  const [output, setOutput] = useState('')
  // Credentials draft — keyed by field name, never pre-filled with the
  // existing secret (the payload only carries masked values).
  const [draft, setDraft] = useState({})

  const reload = () =>
    Promise.all([
      api.get('/staff/social/'),
      api.get('/staff/social/estat-canals/').catch(() => null),
    ])
      .then(([d, e]) => {
        setData(d)
        setEstat(e)
      })
      .catch(() => setData(null))
  useEffect(() => {
    reload()
  }, [])

  const rows = useMemo(() => {
    if (!data?.results || !desc) return []
    const set = new Set(desc.platforms)
    return data.results.filter((p) => set.has(p.platform))
  }, [data, desc])

  if (!desc) {
    return (
      <section className="space-y-6">
        <PageHeader
          title="Canal desconegut"
          subtitle={`«${canal}» no és un canal gestionable.`}
        />
        <TableCard>
          <EmptyState>
            Torna a{' '}
            <Link className="underline" to="/staff/social">
              Distribució
            </Link>
            .
          </EmptyState>
        </TableCard>
      </section>
    )
  }
  if (!data) {
    return (
      <section className="space-y-6">
        <PageHeader title={`Distribució · ${desc.nom}`} subtitle="Carregant…" />
      </section>
    )
  }

  const cfg = data.config || {}
  const creds = data[desc.payloadKey] || { configured: false }
  const st = estat?.canals?.[desc.key]
  const efectiu = st?.efectiu || (cfg[desc.switchField] ? 'actiu' : 'pausat_canal')
  const ef = EFECTIU[efectiu] || { tone: 'gray', label: efectiu }
  const canalActiu = !!cfg[desc.switchField]

  async function toggle() {
    setBusy(true)
    try {
      await api.post('/staff/social/toggle/', { channel: desc.key })
      await reload()
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    const missing = desc.auth.fields.filter(
      (f) => f.required && !(draft[f.name] || '').trim()
    )
    if (missing.length) {
      alert(`Cal: ${missing.map((f) => f.label).join(', ')}.`)
      return
    }
    setBusy(true)
    try {
      const body = {}
      desc.auth.fields.forEach((f) => {
        body[f.name] = (draft[f.name] || '').trim()
      })
      await api.post(desc.auth.saveEndpoint, body)
      setDraft({})
      await reload()
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function test() {
    setBusy(true)
    setOutput('')
    try {
      const res = await api.post(desc.auth.testEndpoint)
      setOutput(JSON.stringify(res, null, 2))
    } catch (e) {
      setOutput(`Error: ${e.payload?.error || e.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function clear() {
    if (!confirm(desc.auth.clearConfirm)) return
    setBusy(true)
    try {
      await api.post(desc.auth.clearEndpoint)
      await reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader
        title={`Distribució · ${desc.nom}`}
        subtitle={`Canal independent · mestre ${
          cfg.distribucio_activa ? 'actiu' : 'pausat'
        }`}
        right={
          <>
            <Pill tone={ef.tone}>{ef.label}</Pill>
            <Btn
              tone={canalActiu ? 'danger' : 'primary'}
              size="md"
              disabled={busy}
              onClick={toggle}
            >
              {canalActiu ? 'Pausar canal' : 'Activar canal'}
            </Btn>
          </>
        }
      />
      <p className="-mt-2 text-sm text-white/70">
        <Link
          className="underline decoration-dotted hover:decoration-solid"
          to="/staff/social"
        >
          ← Tornar a Distribució
        </Link>
      </p>

      {/* ── Auth / credentials ──────────────────────────────────── */}
      <TableCard className="p-4 space-y-3">
        <h2 className="text-base font-bold font-display">Credencials</h2>
        {creds.configured ? (
          <p className="text-sm">{desc.auth.summary(creds)}</p>
        ) : (
          <p className="text-sm text-tq-ink/75">{desc.auth.help}</p>
        )}
        <div className="flex flex-wrap gap-2">
          {creds.configured && (
            <Btn tone="secondary" disabled={busy} onClick={test}>
              Provar
            </Btn>
          )}
          {creds.configured && (
            <Btn tone="danger" disabled={busy} onClick={clear}>
              Esborrar
            </Btn>
          )}
        </div>
        <details>
          <summary className="text-xs cursor-pointer font-semibold text-tq-ink/70">
            {creds.configured ? 'Substituir credencials…' : 'Afegir credencials…'}
          </summary>
          <div className="mt-3 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {desc.auth.fields.map((f) => (
              <Field key={f.name} label={f.label}>
                <Input
                  type={f.type || 'text'}
                  autoComplete="off"
                  placeholder={f.placeholder}
                  value={draft[f.name] || ''}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, [f.name]: e.target.value }))
                  }
                />
              </Field>
            ))}
          </div>
          <div className="mt-3">
            <Btn tone="primary" disabled={busy} onClick={save}>
              Desar
            </Btn>
          </div>
        </details>
        {output && (
          <pre className="bg-tq-ink text-tq-yellow text-xs p-3 rounded overflow-x-auto whitespace-pre-wrap">
            {output}
          </pre>
        )}
      </TableCard>

      {/* ── Recent publications ─────────────────────────────────── */}
      <div>
        <h2 className="mb-2 text-base font-bold text-white font-display">
          Publicacions recents
        </h2>
        <p className="mb-2 text-sm text-white/70">
          Últimes files d'aquest canal (de la llista compartida; la taula unificada
          amb filtres i paginació arriba a la llesca següent).
        </p>
        <TableCard>
          <Table>
            <THead>
              <Tr>
                <Th>Data</Th>
                <Th>Setmana</Th>
                <Th>Tipus</Th>
                <Th>Territori</Th>
                <Th>Estat</Th>
              </Tr>
            </THead>
            <tbody>
              {rows.map((p) => {
                const s = STATUS[p.status] || { tone: 'gray', label: p.status }
                return (
                  <Tr key={p.pk}>
                    <Td className="whitespace-nowrap font-mono text-xs">
                      {p.published_at
                        ? p.published_at.slice(0, 16).replace('T', ' ')
                        : p.created_at?.slice(0, 10) || '—'}
                    </Td>
                    <Td className="whitespace-nowrap">Setmana {p.project_week}</Td>
                    <Td className="text-xs">{p.tipus}</Td>
                    <Td>{p.territori_label}</Td>
                    <Td>
                      <Pill tone={s.tone}>{s.label}</Pill>
                    </Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
          {rows.length === 0 && (
            <EmptyState>Cap publicació d'aquest canal encara.</EmptyState>
          )}
        </TableCard>
      </div>

      {/* ── Diagnostics ─────────────────────────────────────────── */}
      {/* Slot reserved on purpose: slice 1 leaves it empty. Channel
          health checks (e.g. the known Bluesky VAL failure) land in a
          later slice. */}
      <div>
        <h2 className="mb-2 text-base font-bold text-white font-display">Diagnòstics</h2>
        <TableCard>
          <EmptyState>
            Sense diagnòstics actius. Espai reservat per a avisos del canal a les
            llesques següents.
          </EmptyState>
        </TableCard>
      </div>
    </section>
  )
}
