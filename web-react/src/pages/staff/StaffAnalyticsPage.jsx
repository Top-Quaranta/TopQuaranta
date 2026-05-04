/**
 * StaffAnalyticsPage — `/staff/analytics` ethical aggregate dashboard.
 *
 * Five tabs over a single payload from
 * `GET /api/v1/staff/analytics/summary/?days=N`:
 *
 *   1. Resum     — KPI tiles + week-over-week deltas + top insight strip
 *   2. Pipeline  — daily series for verificades / pendents / cobertura / etc.
 *   3. Social    — per-platform follower history + top engagement posts
 *   4. Web       — pageview leaderboard + UTM source/campaign breakdown
 *   5. Cohorts   — registres / propostes / feedback / publicacions over time
 *
 * No PII surfaces here — every number on screen is an aggregate count
 * across a (data, clau, dim) tuple. The CSV export at the top right
 * downloads exactly what's on screen, plain text, no extra payload.
 *
 * Window selector (7d / 30d / 90d / 365d) re-fetches the summary;
 * everything else is derived client-side from that one payload so
 * tab-switches are instant.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../../lib/api'
import { PageHeader, Pill, TableCard } from '../../components/staff/StaffTable'

// ── Brand-aware palette. Sourced from `editorial.jsx::TERR_COLORS`
//    plus a neutral set for non-territory series (platforms, etc.).
const TERR_COLORS = {
  PPCC: '#427c42', CAT: '#c99b0c', VAL: '#cf3339', BAL: '#0047ba',
  AND:  '#7c3aed', CNO: '#0891b2', FRA: '#ea580c', ALG: '#db2777',
  ALT:  '#6b7280',
}
const PLATFORM_COLORS = {
  instagram: '#e1306c',
  instagram_feed: '#e1306c',
  instagram_story: '#fcaf45',
  mastodon: '#6364ff',
  bluesky: '#1083fe',
  telegram: '#229ed9',
  newsletter: '#facc15',
}
const SERIES_COLORS = ['#facc15', '#0a0a0a', '#427c42', '#7c3aed', '#cf3339',
                       '#0891b2', '#ea580c', '#db2777', '#0047ba', '#6b7280']

const TABS = [
  { id: 'resum',    label: 'Resum'     },
  { id: 'pipeline', label: 'Pipeline'  },
  { id: 'social',   label: 'Social'    },
  { id: 'web',      label: 'Web'       },
  { id: 'cohorts',  label: 'Cohorts'   },
]

const WINDOWS = [
  { id: 7,   label: '7d'  },
  { id: 30,  label: '30d' },
  { id: 90,  label: '90d' },
  { id: 365, label: '1a'  },
]

// ── Small UI primitives ────────────────────────────────────────────

function Card({ title, hint, children, right, className = '' }) {
  return (
    <section className={'bg-white text-tq-ink rounded shadow-sm p-4 ' + className}>
      {(title || right) && (
        <header className="flex items-baseline justify-between gap-2 mb-3">
          <div>
            {title && <h3 className="font-semibold text-sm">{title}</h3>}
            {hint && <p className="text-xs text-tq-ink/60">{hint}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  )
}

function Kpi({ label, value, delta, hint, tone = 'ink' }) {
  const deltaColor =
    delta == null
      ? 'text-tq-ink/50'
      : delta > 0
        ? 'text-emerald-700'
        : delta < 0
          ? 'text-rose-700'
          : 'text-tq-ink/50'
  const deltaTxt =
    delta == null
      ? '—'
      : (delta > 0 ? '▲ +' : delta < 0 ? '▼ ' : '· ') + Math.abs(delta).toLocaleString('ca-ES')
  return (
    <Card>
      <p className="text-[11px] uppercase tracking-widest text-tq-ink/60">{label}</p>
      <p className="text-3xl font-bold tabular-nums leading-tight mt-1">
        {value == null ? '—' : Number(value).toLocaleString('ca-ES')}
      </p>
      <p className={'text-xs mt-1 ' + deltaColor}>{deltaTxt}</p>
      {hint && <p className="text-[11px] text-tq-ink/50 mt-1">{hint}</p>}
    </Card>
  )
}

// ── Data helpers ───────────────────────────────────────────────────

/** Sum a series within an [from, to] window (inclusive). */
function sumSeries(series, from, to) {
  if (!series) return 0
  return series.reduce((acc, p) => {
    if ((!from || p.data >= from) && (!to || p.data <= to)) {
      return acc + (Number(p.valor) || 0)
    }
    return acc
  }, 0)
}

/** Latest value of a gauge series. */
function lastValue(series) {
  if (!series || !series.length) return null
  return Number(series[series.length - 1].valor) || 0
}

/** Build CSV string from a list of {key, value} rows. */
function rowsToCsv(headers, rows) {
  const escape = (v) => {
    const s = String(v ?? '')
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [
    headers.join(';'),
    ...rows.map(r => headers.map(h => escape(r[h])).join(';')),
  ].join('\n')
}

function downloadCsv(filename, csv) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ── Tab views ──────────────────────────────────────────────────────

function ResumTab({ data }) {
  const events = data.events || {}
  const pipeline = data.pipeline || {}
  const half = Math.floor(data.window.days / 2)
  // First-half vs second-half split for week-over-week deltas.
  const today = data.window.until
  const split = (() => {
    const d = new Date(today)
    d.setDate(d.getDate() - half)
    return d.toISOString().slice(0, 10)
  })()

  const sumNow = (clau) => sumSeries(events[clau], split, null)
  const sumPrev = (clau) => sumSeries(events[clau], data.window.since, split)
  const delta = (clau) => sumNow(clau) - sumPrev(clau)

  const insights = useMemo(() => {
    const out = []
    const pageviews = sumNow('pageview')
    const pageviews_prev = sumPrev('pageview')
    if (pageviews_prev > 0) {
      const pct = Math.round(((pageviews - pageviews_prev) / pageviews_prev) * 100)
      if (Math.abs(pct) >= 10) {
        out.push({
          tone: pct > 0 ? 'good' : 'warn',
          text: `Pageviews ${pct > 0 ? 'creixen' : 'baixen'} un ${Math.abs(pct)} % respecte la quinzena anterior.`,
        })
      }
    }
    if (data.feedback?.length) {
      const top = data.feedback[0]
      out.push({
        tone: 'info',
        text: `El feedback més actiu és sobre ${top.target} (${top.total} reports).`,
      })
    }
    const verif_series = pipeline.cancons_verificades || []
    if (verif_series.length >= 2) {
      const first = verif_series[0]?.valor
      const last = verif_series[verif_series.length - 1]?.valor
      if (first && last && last > first) {
        out.push({
          tone: 'good',
          text: `S'han verificat ${(last - first).toLocaleString('ca-ES')} cançons noves al període.`,
        })
      }
    }
    const top_post = data.social_metrics?.top_posts?.[0]
    if (top_post) {
      out.push({
        tone: 'info',
        text: `Top post: ${top_post.platform} · ${top_post.tipus}${top_post.territori ? ` · ${top_post.territori}` : ''} — ${top_post.likes} likes / ${top_post.shares} shares / ${top_post.reach} reach.`,
      })
    }
    return out.slice(0, 4)
  }, [data, pipeline, half])

  return (
    <div className="space-y-4">
      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Pageviews"      value={sumSeries(events.pageview)} delta={delta('pageview')}  hint={`${data.window.days} dies`} />
        <Kpi label="Registres"      value={sumSeries(events.registre_complet)} delta={delta('registre_complet')} />
        <Kpi label="Propostes"      value={sumSeries(events.proposta_crear)} delta={delta('proposta_crear')} />
        <Kpi label="Feedback"       value={sumSeries(events.feedback_crear)} delta={delta('feedback_crear')} />
        <Kpi label="UTM landings"   value={sumSeries(events.utm_landing)} delta={delta('utm_landing')} />
        <Kpi label="Publicacions"   value={sumSeries(events.social_publicat)} delta={delta('social_publicat')} />
        <Kpi label="Cançons verif." value={lastValue(pipeline.cancons_verificades)} hint="snapshot avui" />
        <Kpi label="Artistes apr."  value={lastValue(pipeline.artistes_aprovats)} hint="snapshot avui" />
      </div>

      {/* Insights strip */}
      <Card title="Insights" hint="Senyals automàtics extrets dels darrers dies">
        {insights.length === 0 ? (
          <p className="text-sm text-tq-ink/60">Encara no hi ha prou dades per a destacar res.</p>
        ) : (
          <ul className="space-y-1.5">
            {insights.map((it, i) => (
              <li key={i} className="text-sm flex items-start gap-2">
                <span className={
                  'mt-1 inline-block w-1.5 h-1.5 rounded-full ' +
                  (it.tone === 'good' ? 'bg-emerald-600' : it.tone === 'warn' ? 'bg-rose-600' : 'bg-amber-500')
                } />
                <span>{it.text}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Pageview + registre joint chart */}
      <Card title="Activitat diària" hint="Pageviews i registres complets">
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={mergeSeries(events, ['pageview', 'registre_complet'])}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="data" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="pageview"        name="Pageviews" stroke="#0a0a0a" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="registre_complet" name="Registres" stroke="#facc15" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  )
}

function PipelineTab({ data }) {
  const pipeline = data.pipeline || {}
  const territoris = data.territoris || []

  return (
    <div className="space-y-4">
      <Card title="Estat del catàleg" hint="Cançons verificades vs pendents al llarg del temps">
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={mergeSeries(pipeline, ['cancons_verificades', 'cancons_pendents', 'cancons_rebutjades_acumulades'])}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="data" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="cancons_verificades"          name="Verificades" stroke="#427c42" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="cancons_pendents"             name="Pendents"    stroke="#facc15" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="cancons_rebutjades_acumulades" name="Rebutjades"  stroke="#cf3339" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Cobertura de metadades" hint="% del pool actiu enriquit per cada font">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={mergeSeries(pipeline, ['cobertura_whisper', 'cobertura_mb'])}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="data" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} />
              <Tooltip formatter={(v) => `${v} %`} />
              <Legend />
              <Line type="monotone" dataKey="cobertura_whisper" name="Whisper LID" stroke="#0a0a0a" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="cobertura_mb"      name="MusicBrainz" stroke="#7c3aed" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Distribució per territori" hint="Cançons verificades, snapshot més recent">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={territoris} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="codi" width={50} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="valor">
                {territoris.map((t, i) => (
                  <Cell key={i} fill={TERR_COLORS[t.codi] || '#0a0a0a'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card title="Comunitat" hint="Snapshot diari d'usuaris i directori">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={mergeSeries(pipeline, ['usuaris_actius', 'newsletter_subscriptors', 'directori_visibles'])}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="data" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="usuaris_actius"           name="Usuaris actius"     stroke="#0a0a0a" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="newsletter_subscriptors"  name="Newsletter"         stroke="#facc15" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="directori_visibles"       name="Directori visible" stroke="#0891b2" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  )
}

function SocialTab({ data }) {
  const sm = data.social_metrics || {}
  const followersByPlatform = sm.followers_series || {}
  const top = sm.top_posts || []
  const latest = sm.latest_platform || []

  // Latest follower count per platform — KPI strip.
  const latestFollowers = useMemo(() => {
    const out = {}
    for (const r of latest) {
      if (r.metric === 'followers' || r.metric === 'members') {
        out[r.platform] = r.valor
      }
    }
    return out
  }, [latest])

  // Aggregate publication counts per channel from `data.social`.
  const publishedByChannel = useMemo(() => {
    const out = {}
    for (const r of (data.social || [])) {
      out[r.channel] = (out[r.channel] || 0) + r.total
    }
    return Object.entries(out).map(([channel, total]) => ({ channel, total }))
  }, [data.social])

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {Object.entries(latestFollowers).map(([platform, valor]) => (
          <Kpi
            key={platform}
            label={platform}
            value={valor}
            hint={platform === 'telegram' ? 'membres' : 'seguidors'}
          />
        ))}
      </div>

      <Card
        title="Creixement de seguidors"
        hint="Sèrie diària per plataforma. Telegram = membres del canal."
      >
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={mergeMultiPlatform(followersByPlatform)}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="data" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Legend />
            {Object.keys(followersByPlatform).map((p) => (
              <Line
                key={p}
                type="monotone"
                dataKey={p}
                name={p}
                stroke={PLATFORM_COLORS[p] || '#0a0a0a'}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Publicacions per canal" hint="Comptador acumulat al període">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={publishedByChannel}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="channel" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="total">
                {publishedByChannel.map((r, i) => (
                  <Cell key={i} fill={PLATFORM_COLORS[r.channel] || '#0a0a0a'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card
          title="Top 10 posts per engagement"
          hint="Likes + replies + shares (snapshot més recent)"
          right={
            <button
              type="button"
              onClick={() => downloadCsv(
                'analytics_top_posts.csv',
                rowsToCsv(['platform', 'tipus', 'territori', 'setmana', 'likes', 'replies', 'shares', 'reach'], top),
              )}
              className="text-xs px-2 py-1 rounded bg-tq-ink text-tq-yellow hover:opacity-90"
            >
              Descarrega CSV
            </button>
          }
        >
          <TableCard className="!shadow-none !p-0 !bg-transparent">
            <table className="w-full text-xs">
              <thead className="text-tq-ink/60">
                <tr>
                  <th className="text-left">Canal</th>
                  <th className="text-left">Tipus</th>
                  <th className="text-right">L</th>
                  <th className="text-right">R</th>
                  <th className="text-right">S</th>
                  <th className="text-right">Reach</th>
                </tr>
              </thead>
              <tbody>
                {top.length === 0 && (
                  <tr><td colSpan={6} className="py-3 text-center text-tq-ink/60">Encara sense dades.</td></tr>
                )}
                {top.map((p, i) => (
                  <tr key={i} className="border-t border-tq-ink/5">
                    <td className="py-1">
                      <Pill tone="ink">{p.platform}</Pill>
                    </td>
                    <td>{p.tipus}{p.territori ? ` · ${p.territori}` : ''}</td>
                    <td className="text-right tabular-nums">{p.likes}</td>
                    <td className="text-right tabular-nums">{p.replies}</td>
                    <td className="text-right tabular-nums">{p.shares}</td>
                    <td className="text-right tabular-nums">{p.reach}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableCard>
        </Card>
      </div>
    </div>
  )
}

function WebTab({ data }) {
  const events = data.events || {}
  const pageviews = data.pageviews || []
  const utm = data.utm || []

  return (
    <div className="space-y-4">
      <Card title="Pageviews diaris" hint="Sèrie temporal sumada (totes les rutes)">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={events.pageview || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="data" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="valor" fill="#facc15" />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card
          title="Top 20 pàgines"
          hint="Rutes més visitades al període"
          right={
            <button
              type="button"
              onClick={() => downloadCsv('pageviews.csv', rowsToCsv(['path', 'total'], pageviews))}
              className="text-xs px-2 py-1 rounded bg-tq-ink text-tq-yellow hover:opacity-90"
            >
              CSV
            </button>
          }
        >
          <table className="w-full text-xs">
            <thead className="text-tq-ink/60">
              <tr>
                <th className="text-left">Ruta</th>
                <th className="text-right">Pageviews</th>
              </tr>
            </thead>
            <tbody>
              {pageviews.length === 0 && (
                <tr><td colSpan={2} className="py-3 text-center text-tq-ink/60">Sense dades.</td></tr>
              )}
              {pageviews.map((r, i) => (
                <tr key={i} className="border-t border-tq-ink/5">
                  <td className="py-1 truncate max-w-[260px]" title={r.path}>{r.path}</td>
                  <td className="text-right tabular-nums">{r.total.toLocaleString('ca-ES')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card
          title="UTM landings"
          hint="Source × campaign — d'on venen els clicks externs"
          right={
            <button
              type="button"
              onClick={() => downloadCsv('utm.csv', rowsToCsv(['source', 'campaign', 'total'], utm))}
              className="text-xs px-2 py-1 rounded bg-tq-ink text-tq-yellow hover:opacity-90"
            >
              CSV
            </button>
          }
        >
          <table className="w-full text-xs">
            <thead className="text-tq-ink/60">
              <tr>
                <th className="text-left">Source</th>
                <th className="text-left">Campaign</th>
                <th className="text-right">Landings</th>
              </tr>
            </thead>
            <tbody>
              {utm.length === 0 && (
                <tr><td colSpan={3} className="py-3 text-center text-tq-ink/60">Sense dades UTM al període.</td></tr>
              )}
              {utm.map((r, i) => (
                <tr key={i} className="border-t border-tq-ink/5">
                  <td className="py-1">{r.source}</td>
                  <td>{r.campaign}</td>
                  <td className="text-right tabular-nums">{r.total.toLocaleString('ca-ES')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  )
}

function CohortsTab({ data }) {
  const events = data.events || {}
  // Aligned daily series for the funnel-ish view: registre → proposta
  // → feedback → social_publicat. Same X axis, four lines.
  const merged = mergeSeries(events, ['registre_complet', 'proposta_crear', 'solicitud_gestor_crear', 'feedback_crear', 'social_publicat'])
  return (
    <div className="space-y-4">
      <Card title="Activitat per dia" hint="Registres / propostes / feedback / publicacions">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={merged}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="data" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="registre_complet"        name="Registres"   stroke="#facc15" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="proposta_crear"          name="Propostes"   stroke="#427c42" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="solicitud_gestor_crear"  name="Sol·licituds" stroke="#7c3aed" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="feedback_crear"          name="Feedback"    stroke="#cf3339" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="social_publicat"         name="Publicacions" stroke="#0a0a0a" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Distribució del feedback" hint="Per surface (artista / album / canco / altres)">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={data.feedback || []}
                dataKey="total"
                nameKey="target"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={(e) => `${e.target}: ${e.total}`}
              >
                {(data.feedback || []).map((_, i) => (
                  <Cell key={i} fill={SERIES_COLORS[i % SERIES_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Tots els comptadors crus" hint="Per a auditoria — esdeveniments registrats i totals">
          <table className="w-full text-xs">
            <thead className="text-tq-ink/60">
              <tr>
                <th className="text-left">Clau</th>
                <th className="text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(events).sort(([, a], [, b]) =>
                (b.reduce((s, p) => s + p.valor, 0)) - (a.reduce((s, p) => s + p.valor, 0))
              ).map(([clau, series]) => (
                <tr key={clau} className="border-t border-tq-ink/5">
                  <td className="py-1 font-mono">{clau}</td>
                  <td className="text-right tabular-nums">
                    {series.reduce((s, p) => s + p.valor, 0).toLocaleString('ca-ES')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  )
}

// ── Helpers shared by tabs ─────────────────────────────────────────

/** Merge multiple {clau: [{data,valor}]} series into one row-per-day shape. */
function mergeSeries(eventsOrPipeline, keys) {
  const byDate = new Map()
  for (const k of keys) {
    for (const p of (eventsOrPipeline[k] || [])) {
      if (!byDate.has(p.data)) byDate.set(p.data, { data: p.data })
      byDate.get(p.data)[k] = p.valor
    }
  }
  // Fill nulls so recharts doesn't drop intermediate days.
  const out = Array.from(byDate.values()).sort((a, b) => a.data.localeCompare(b.data))
  for (const row of out) for (const k of keys) if (row[k] == null) row[k] = 0
  return out
}

/** {platform: [{data,valor}]} → [{data, ig:..., bsky:...}]. */
function mergeMultiPlatform(byPlatform) {
  const byDate = new Map()
  for (const [p, series] of Object.entries(byPlatform)) {
    for (const pt of (series || [])) {
      if (!byDate.has(pt.data)) byDate.set(pt.data, { data: pt.data })
      byDate.get(pt.data)[p] = pt.valor
    }
  }
  return Array.from(byDate.values()).sort((a, b) => a.data.localeCompare(b.data))
}

// ── Main page ─────────────────────────────────────────────────────

export default function StaffAnalyticsPage() {
  const [days, setDays] = useState(30)
  const [tab, setTab] = useState('resum')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.get(`/staff/analytics/summary/?days=${days}`)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [days])

  const right = (
    <div className="flex items-center gap-2">
      <div className="flex bg-white/10 rounded overflow-hidden">
        {WINDOWS.map(w => (
          <button
            key={w.id}
            type="button"
            onClick={() => setDays(w.id)}
            className={
              'text-xs px-3 py-1.5 transition-colors ' +
              (days === w.id ? 'bg-tq-yellow text-tq-ink font-semibold' : 'text-white/80 hover:bg-white/10')
            }
          >
            {w.label}
          </button>
        ))}
      </div>
    </div>
  )

  if (error) {
    return (
      <section>
        <PageHeader title="Analytics" right={right} />
        <p className="text-sm text-rose-300">Error: {error}</p>
      </section>
    )
  }

  return (
    <section>
      <PageHeader
        title="Analytics"
        subtitle="Mètriques agregades, sense dades personals · ètica per disseny"
        right={right}
      />

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/10 mb-4 overflow-x-auto">
        {TABS.map(t => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={
              'text-sm px-4 py-2 -mb-px border-b-2 transition-colors whitespace-nowrap ' +
              (tab === t.id
                ? 'border-tq-yellow text-tq-yellow font-semibold'
                : 'border-transparent text-white/70 hover:text-white')
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading || !data ? (
        <p className="text-sm text-white/70">Carregant…</p>
      ) : tab === 'resum'    ? <ResumTab data={data} />
        : tab === 'pipeline' ? <PipelineTab data={data} />
        : tab === 'social'   ? <SocialTab data={data} />
        : tab === 'web'      ? <WebTab data={data} />
        : tab === 'cohorts'  ? <CohortsTab data={data} />
        : null}
    </section>
  )
}
