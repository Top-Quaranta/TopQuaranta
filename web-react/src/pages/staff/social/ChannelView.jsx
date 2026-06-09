/**
 * ChannelView — shared house-style template for a single distribution
 * channel. Paints from CHANNEL_DESCRIPTORS[canal] so changing a section
 * or adding a channel is a descriptor edit, not a view edit.
 *
 * Sections (llesca 3), all descriptor-driven:
 *   - Header: name + effective state + pause toggle.
 *   - Section 1 (section1): on-demand surface — newsletter only.
 *   - Section 2 (kpis): per-channel KPI strip; missing data → honest
 *     dash, never a fake 0.
 *   - Credentials: only channels with an `auth` block.
 *   - Section 3 (control): what the channel publishes, read-only (derived
 *     from code; not editable this slice).
 *   - Section 4 (analytics): the shared PublicacionsTable scoped to this
 *     channel + an honest note on metric availability.
 *   - Diagnostics: reserved slot.
 *
 * Data: `/staff/social/` (config + credentials), `/staff/social/estat-
 * canals/` (effective state + last send), `/staff/analytics/summary/`
 * (KPI values).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import {
  Btn,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Pill,
  TableCard,
} from '../../../components/staff/StaffTable'
import { CHANNEL_DESCRIPTORS } from './channelDescriptors'
import MatriuCanalToggles from './MatriuCanalToggles'
import PublicacionsTable from './PublicacionsTable'
import NewsletterSection from './NewsletterSection'
import InstagramSection from './InstagramSection'

const EFECTIU = {
  actiu: { tone: 'green', label: 'Actiu' },
  pausat_global: { tone: 'gray', label: 'Pausat pel mestre' },
  pausat_canal: { tone: 'red', label: 'Pausat (canal)' },
}

function fmtDate(iso) {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d)) return null
  return d.toLocaleDateString('ca', { day: '2-digit', month: '2-digit' })
}

// Resolve a KPI value from the analytics summary + estat-canals. Returns
// `null` when there's genuinely no data (→ the strip shows a dash).
function kpiValue(key, desc, summary, st) {
  if (key === 'enviaments') {
    const set = new Set(desc.platforms)
    const total = (summary?.social || [])
      .filter((r) => set.has(r.channel))
      .reduce((a, r) => a + (r.total || 0), 0)
    const sub = st?.ultim_enviament ? `últim ${fmtDate(st.ultim_enviament)}` : null
    return { value: total, sub }
  }
  if (key === 'subscriptors') {
    const v = summary?.newsletter_audience
    return { value: v == null ? null : v }
  }
  if (key === 'seguidors') {
    const lp = (summary?.social_metrics?.latest_platform || []).find(
      (p) => p.platform === desc.key && (p.metric === 'followers' || p.metric === 'members')
    )
    return { value: lp ? lp.valor : null }
  }
  return { value: null } // abast etc. → declared missing
}

function KpiStrip({ desc, summary, st }) {
  const entries = Object.entries(desc.kpis).filter(([, v]) => v)
  return (
    <div>
      <h2 className="mb-2 text-base font-bold text-white font-display">KPIs</h2>
      <TableCard className="p-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {entries.map(([key, meta]) => {
            const { value, sub } = kpiValue(key, desc, summary, st)
            const show = meta.status === 'exists' && value != null
            return (
              <div key={key} className="p-3 border border-tq-ink/10 rounded-md">
                <p className="text-[10px] uppercase tracking-widest text-tq-ink/60">
                  {meta.label}
                </p>
                <p className="text-xl font-bold text-tq-ink mt-0.5">
                  {show ? value : <span className="text-tq-ink/40">—</span>}
                </p>
                {show && sub ? (
                  <p className="text-[10px] text-tq-ink/60">{sub}</p>
                ) : (
                  !show && (
                    <p className="text-[10px] text-tq-ink/40">
                      {meta.status === 'missing' ? 'no disponible' : 'sense dada'}
                    </p>
                  )
                )}
              </div>
            )
          })}
        </div>
      </TableCard>
    </div>
  )
}

function ControlSection({ desc }) {
  return (
    <div>
      <h2 className="mb-2 text-base font-bold text-white font-display">
        Què publica
      </h2>
      <TableCard className="p-4 space-y-2">
        <MatriuCanalToggles canal={desc.key} />
        <p className="text-[11px] text-tq-ink/60">
          {desc.control.nota}. Desmarcar atura la distribució d'eixe tipus per
          aquest canal.
        </p>
      </TableCard>
    </div>
  )
}

export default function ChannelView({ canal }) {
  const desc = CHANNEL_DESCRIPTORS[canal]
  const [data, setData] = useState(null)
  const [estat, setEstat] = useState(null)
  const [summary, setSummary] = useState(null)
  const [busy, setBusy] = useState(false)
  const [output, setOutput] = useState('')
  // Credentials draft — keyed by field name, never pre-filled with the
  // existing secret (the payload only carries masked values).
  const [draft, setDraft] = useState({})

  const reload = () =>
    Promise.all([
      api.get('/staff/social/'),
      api.get('/staff/social/estat-canals/').catch(() => null),
      api.get('/staff/analytics/summary/?days=90').catch(() => null),
    ])
      .then(([d, e, s]) => {
        setData(d)
        setEstat(e)
        setSummary(s)
      })
      .catch(() => setData(null))
  useEffect(() => {
    reload()
  }, [])

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
  const creds = (desc.payloadKey && data[desc.payloadKey]) || { configured: false }
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

  const analyticsMissing = desc.analytics?.status === 'missing'

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

      {/* ── Section 1 — on-demand surface (newsletter only) ──────── */}
      {desc.section1?.kind === 'newsletter' && <NewsletterSection />}
      {desc.section1?.kind === 'instagram' && <InstagramSection />}

      {/* ── Section 2 — KPIs ────────────────────────────────────── */}
      {desc.kpis && <KpiStrip desc={desc} summary={summary} st={st} />}

      {/* ── Credentials (channels with an auth block) ───────────── */}
      {desc.auth && (
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
      )}

      {/* ── Section 3 — Control (read-only) ─────────────────────── */}
      {desc.control && <ControlSection desc={desc} />}

      {/* ── Section 4 — Publications + analytics ─────────────────── */}
      <div>
        <h2 className="mb-2 text-base font-bold text-white font-display">
          Publicacions i analítica
        </h2>
        <p className="mb-2 text-sm text-white/70">
          {analyticsMissing
            ? 'Sense recollida de mètriques d\'engagement per a aquest canal (—). Files de la taula compartida, filtrades pel canal.'
            : `Mètriques per post disponibles: ${(desc.analytics?.available || []).join(
                ', '
              )}. Files de la taula compartida, filtrades pel canal.`}
        </p>
        <PublicacionsTable params={{ canal: desc.key }} />
      </div>

      {/* ── Diagnostics ─────────────────────────────────────────── */}
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
