/**
 * EstatPage — /staff/estat
 *
 * Visual system-health dashboard. Everything staff wants to know at
 * a glance:
 *   - BD inventory (artistes/albums/cançons counts with state pills)
 *   - Whisper LID coverage progress bar + rate
 *   - Ranking state (weekly + provisional)
 *   - Cron health matrix (colour-coded per last run)
 *   - ML model summary + feature importance bar chart
 *   - Community queues (feedback/propostes/sol·licituds)
 *
 * Data comes from a single GET /api/v1/staff/estat/ call — no live
 * polling (daily data doesn't change that fast), but the page
 * refreshes every 60 s in case staff leaves it open.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { PageHeader, Pill, TableCard } from '../../components/staff/StaffTable'

// ── Small display helpers ────────────────────────────────────────────────

function BigNumber({ label, value, sub, tone = 'ink', to }) {
  // ink/yellow are brand colours (utility classes). Semantic tones map
  // to the `--color-tq-success/danger/neutral` design tokens via inline
  // styles, so a palette change reaches them without touching call sites.
  const tones = {
    ink:    'bg-white text-tq-ink',
    yellow: 'bg-tq-yellow text-tq-ink',
  }
  const semStyle = {
    green:  { background: 'rgba(16, 185, 129, 0.16)', color: 'var(--color-tq-success)'                  },
    red:    { background: 'rgba(239, 68, 68, 0.16)',  color: 'var(--color-tq-danger)'                   },
    gray:   { background: 'rgba(156, 163, 175, 0.16)', color: 'var(--color-tq-neutral, #6b7280)'        },
  }
  const inner = (
    <>
      <p className="text-[10px] uppercase tracking-widest opacity-70">{label}</p>
      <p className="text-3xl font-bold font-display tabular-nums mt-1">
        {typeof value === 'number' ? value.toLocaleString('ca') : value ?? '—'}
      </p>
      {sub && <p className="text-[11px] opacity-60 mt-0.5">{sub}</p>}
    </>
  )
  const cls = tones[tone] || tones.ink
  const style = semStyle[tone]
  if (to) {
    return (
      <Link
        to={to}
        className={`block rounded-lg p-4 hover:shadow-md transition-shadow ${cls || ''}`}
        style={style}
      >
        {inner}
      </Link>
    )
  }
  return <div className={`rounded-lg p-4 ${cls || ''}`} style={style}>{inner}</div>
}

/**
 * StatRow — labelled value with optional `to` link, used in the
 * MusicBrainz / Whisper detail panels.
 */
function StatRow({ label, value, to, accent }) {
  // `accent` accepts a semantic tone key (success | danger | warning)
  // and resolves to the matching design-system colour token. Falls
  // through to ink for the default text colour.
  const accentColor = {
    success: 'var(--color-tq-success)',
    danger:  'var(--color-tq-danger)',
    warning: 'var(--color-tq-yellow-deep)',
  }[accent]
  const valNode = (
    <span
      className="font-semibold tabular-nums"
      style={accentColor ? { color: accentColor } : undefined}
    >
      {typeof value === 'number' ? value.toLocaleString('ca') : value ?? '—'}
    </span>
  )
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-xs border-b border-black/5 last:border-0">
      <span className="opacity-70">{label}</span>
      {to ? (
        <Link to={to} className="underline decoration-dotted hover:decoration-solid">
          {valNode}
        </Link>
      ) : (
        valNode
      )}
    </div>
  )
}

function StackedBar({ segments, total }) {
  // segments = [{label, value, color, to?}]. `to` makes the segment
  // and its legend entry a click-through to a pre-filtered list.
  if (!total) return null
  return (
    <div className="w-full">
      <div className="flex h-6 rounded-md overflow-hidden border border-black/5">
        {segments.map(s => {
          const pct = (s.value / total) * 100
          if (pct <= 0) return null
          const tooltip = `${s.label}: ${s.value.toLocaleString('ca')} (${pct.toFixed(1)}%)`
          // The Link itself carries the colour + width so we don't get
          // the "Link is wider than its inner div" mismatch. Block
          // display so width: % actually applies on the <a> element.
          const styleSeg = {
            width: `${pct}%`,
            background: s.color,
          }
          return s.to ? (
            <Link
              key={s.label}
              to={s.to}
              title={tooltip}
              aria-label={tooltip}
              className="block h-full hover:opacity-80 transition-opacity"
              style={styleSeg}
            />
          ) : (
            <div
              key={s.label}
              style={styleSeg}
              title={tooltip}
            />
          )
        })}
      </div>
      <div className="flex flex-wrap gap-3 mt-2 text-[11px]">
        {segments.map(s => {
          const body = (
            <>
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm"
                style={{ background: s.color }}
              />
              <span className="font-semibold">{s.label}</span>
              <span className="opacity-60">
                {s.value.toLocaleString('ca')} ({((s.value / total) * 100).toFixed(1)}%)
              </span>
            </>
          )
          return s.to ? (
            <Link
              key={s.label}
              to={s.to}
              className="inline-flex items-center gap-1 underline decoration-dotted hover:decoration-solid"
            >
              {body}
            </Link>
          ) : (
            <span key={s.label} className="inline-flex items-center gap-1">
              {body}
            </span>
          )
        })}
      </div>
    </div>
  )
}

function HorizontalBars({ items, max, formatValue, showDirection }) {
  return (
    <ul className="space-y-1.5">
      {items.map(item => {
        const pct = max ? (item.value / max) * 100 : 0
        // direction: +1 → higher value pushes approval, -1 → rejection,
        // 0 → no direction (TF-IDF / absent). Bar colour reflects it.
        const dir = item.direction ?? 0
        const barColor =
          dir > 0 ? 'var(--color-tq-success)' :
          dir < 0 ? 'var(--color-tq-danger)' :
          'var(--mm-color-accent, #facc15)'
        return (
          <li key={item.name} className="flex items-center gap-3 text-xs">
            {showDirection && (
              <span
                className="w-4 shrink-0 text-center font-bold"
                title={
                  dir > 0 ? 'Més valor → més APROVA'
                  : dir < 0 ? 'Més valor → més REBUTJA'
                  : 'Sense direcció (feature neutra o textual)'
                }
                style={{
                  color: dir > 0 ? 'var(--color-tq-success)'
                    : dir < 0 ? 'var(--color-tq-danger)'
                    : 'var(--color-tq-neutral-soft, #888)',
                }}
              >
                {dir > 0 ? '↑' : dir < 0 ? '↓' : '·'}
              </span>
            )}
            <span className="w-48 truncate font-mono text-tq-ink/80" title={item.name}>
              {item.name}
            </span>
            <div className="flex-1 h-4 bg-tq-ink/5 rounded overflow-hidden">
              <div
                className="h-full"
                style={{ width: `${pct}%`, background: barColor }}
              />
            </div>
            <span className="w-14 text-right tabular-nums">
              {formatValue ? formatValue(item.value) : item.value}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function CronStatus({ cron }) {
  const ok = cron.status === 'OK'
  const tone = ok ? 'green' : 'red'
  const when = cron.last_run ? cron.last_run.slice(0, 16).replace('T', ' ') : '—'
  const attempts = cron.attempts && cron.attempts !== '1' ? ` · ${cron.attempts}×` : ''
  return (
    <li className="flex items-center gap-3 text-xs py-1.5 border-t border-black/5 first:border-t-0">
      <Pill tone={tone}>{cron.status || '—'}</Pill>
      <span className="font-mono font-semibold text-tq-ink/80 flex-1 truncate">
        {cron.name}
      </span>
      <span className="opacity-60 whitespace-nowrap">
        {when}
        {attempts}
      </span>
    </li>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────

export default function EstatPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    function load() {
      api.get('/staff/estat/').then(setData).catch(e => setError(e.message))
    }
    load()
    const t = setInterval(load, 60_000)
    return () => clearInterval(t)
  }, [])

  if (error) {
    return (
      <section>
        <PageHeader title="Estat del sistema" />
        <p className="text-sm text-red-300">Error: {error}</p>
      </section>
    )
  }
  if (!data) {
    return (
      <section>
        <PageHeader title="Estat del sistema" subtitle="Carregant…" />
      </section>
    )
  }

  const { bd, whisper, ranking, senyal, comunitat, crons, ml, flux, musicbrainz: mb, homonimia } = data

  // Biggest importance for scaling bars.
  const maxImp = ml?.importances?.[0]?.value || 1
  const topImportances = (ml?.importances || []).slice(0, 20)

  // Classified counts for the ML class bar.
  const clsA = ml?.classe_distribution?.A || 0
  const clsB = ml?.classe_distribution?.B || 0
  const clsC = ml?.classe_distribution?.C || 0
  const clsNone = ml?.classe_distribution?.none || 0
  const clsTotal = clsA + clsB + clsC + clsNone

  // The "forever-pending" bucket (tracks without a Deezer preview)
  // can never be analysed — we keep it visible so the cobertura % is
  // honest, but exclude it from any ETA maths.
  const whisperPendentAmbPreview = whisper.pendent_amb_preview ?? 0
  const whisperPendentSensePreview = whisper.pendent_sense_preview ?? 0
  const whisperPendentTotal = whisperPendentAmbPreview + whisperPendentSensePreview
  const whisperAnalitzat = whisper.ca + whisper.no_ca
  const whisperTotal = whisperAnalitzat + whisperPendentTotal
  const whisperDailyLimit = whisper.daily_limit || 100
  const whisperEtaDies = whisperPendentAmbPreview > 0
    ? Math.ceil(whisperPendentAmbPreview / whisperDailyLimit)
    : 0

  return (
    <section className="space-y-6">
      <PageHeader
        title="Estat del sistema"
        subtitle="Salut, dades i rendiment del pipeline en temps real"
      />

      {/* ─── Flux setmanal — la lectura més crítica a la part de dalt ─── */}
      {flux && (
        <section>
          <h2 className="text-sm uppercase tracking-widest text-white/60 mb-2">
            Flux de verificació
          </h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <BigNumber
              label="Entren / setmana"
              value={flux.intake_setmanal_robust}
              sub={
                flux.anomaly_days_excluded > 0
                  ? `robust · últims 7d: ${flux.intake_7d}`
                  : `últims 7d: ${flux.intake_7d}`
              }
              tone="yellow"
            />
            <BigNumber
              label="Caducaran en 7 dies"
              value={flux.caducaran_7d}
              sub={`${flux.caducaran_30d} en els propers 30d`}
              tone="gray"
            />
            <BigNumber
              label="Target setmanal"
              value={flux.target_verificacio_setmanal}
              sub="Per no acumular backlog"
              tone={
                flux.target_verificacio_setmanal === 0
                  ? 'green'
                  : flux.target_verificacio_setmanal > 200
                  ? 'red'
                  : 'yellow'
              }
            />
            <BigNumber
              label="Backlog actual"
              value={flux.backlog_no_verificades}
              sub="Cançons no verificades"
              tone={flux.backlog_no_verificades > 5000 ? 'red' : 'ink'}
            />
          </div>
          <div className="mt-3 bg-white text-tq-ink rounded-lg p-4">
            <div className="flex items-baseline gap-3 mb-2">
              <p className="text-[11px] uppercase tracking-widest opacity-60">
                Entrades per setmana (últimes 4)
              </p>
              {flux.anomaly_days_excluded > 0 && (
                <p className="text-[11px] text-tq-yellow-deep">
                  ({flux.anomaly_days_excluded} dies d'anomalia exclosos del càlcul robust — llindar {flux.anomaly_day_threshold}/dia)
                </p>
              )}
            </div>
            <div className="flex items-end gap-2" style={{ height: 140 }}>
              {(() => {
                const MAX_BAR_PX = 100
                const maxN = Math.max(...flux.intake_per_setmana.map(x => x.n), 1)
                return flux.intake_per_setmana.map(w => {
                  const hPx = Math.max(2, Math.round((w.n / maxN) * MAX_BAR_PX))
                  return (
                  <div
                    key={w.label}
                    className="flex-1 flex flex-col items-center gap-1 min-w-0"
                  >
                    <div className="w-full flex items-end" style={{ height: MAX_BAR_PX }}>
                      <div
                        className="w-full rounded-t"
                        style={{
                          height: hPx,
                          background:
                            'linear-gradient(180deg, var(--color-tq-yellow) 0%, var(--color-tq-accent) 100%)',
                        }}
                        title={`${w.label}: ${w.n} entrades`}
                      />
                    </div>
                    <div className="text-[10px] tabular-nums opacity-70 truncate w-full text-center">
                      {w.n.toLocaleString('ca')}
                    </div>
                    <div className="text-[9px] opacity-50 truncate w-full text-center">
                      {w.label}
                    </div>
                  </div>
                  )
                })
              })()}
            </div>
            <p className="text-[11px] opacity-60 mt-3 leading-relaxed">
              <strong>Lectura:</strong> amb ~{flux.intake_setmanal_robust} entrades setmanals i{' '}
              {flux.caducaran_7d} caducitats en els propers 7 dies, cal verificar com a mínim{' '}
              <strong>{flux.target_verificacio_setmanal} cançons per setmana</strong> per
              no acumular més backlog. El backlog actual és de{' '}
              {flux.backlog_no_verificades.toLocaleString('ca')} cançons.
            </p>
          </div>

          {flux.top_artistes_backlog?.length > 0 && (
            <div className="mt-3 bg-white text-tq-ink rounded-lg p-4">
              <p className="text-[11px] uppercase tracking-widest opacity-60 mb-2">
                Top artistes amb més backlog
              </p>
              <ul className="divide-y divide-tq-ink/10">
                {flux.top_artistes_backlog.map(a => (
                  <li key={a.pk} className="py-2 flex items-center gap-3">
                    <span className="text-xl font-bold font-display tabular-nums text-tq-yellow-deep w-12 text-right shrink-0">
                      {a.n_backlog}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Link
                          to={`/staff/artistes/${a.pk}`}
                          className="font-semibold text-sm underline hover:text-tq-yellow-deep"
                        >
                          {a.nom}
                        </Link>
                        {a.musicbrainz_id && (
                          <span
                            className="text-[10px] uppercase font-semibold px-1.5 rounded"
                            style={{ background: 'rgba(16, 185, 129, 0.16)', color: 'var(--color-tq-success)' }}
                          >
                            MBID
                          </span>
                        )}
                        {a.mb_end_date && (
                          <span
                            className="text-[10px] uppercase font-semibold px-1.5 rounded"
                            style={{ background: 'rgba(239, 68, 68, 0.16)', color: 'var(--color-tq-danger)' }}
                          >
                            Dissolt {a.mb_end_date.slice(0, 4)}
                          </span>
                        )}
                        <Link
                          to={`/staff/cancons?artista_pk=${a.pk}&verificada=0`}
                          className="text-[11px] underline opacity-70 hover:opacity-100"
                        >
                          veure cua
                        </Link>
                      </div>
                      {a.samples?.length > 0 && (
                        <p className="text-[11px] opacity-60 truncate mt-0.5">
                          {a.samples.join(' · ')}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="text-[11px] opacity-60 mt-2">
                Prioritza revisar aquests artistes: o bé tenen disco gran real,
                o bé són víctimes de col·lisió de noms a Deezer. Si hi veus un
                "dissolt" amb cançons recents, el Deezer ID probablement és
                d'un homònim actiu.
              </p>
            </div>
          )}
        </section>
      )}

      {/* ─── BD inventory ─── */}
      <section>
        <h2 className="text-sm uppercase tracking-widest text-white/60 mb-2">
          Base de dades
        </h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <BigNumber
            label="Cançons"
            value={bd.cancons.total}
            sub={`${bd.cancons.verificades.toLocaleString('ca')} verificades · ${bd.cancons.no_verificades_actives.toLocaleString('ca')} pendents`}
            to="/staff/cancons?verificada="
          />
          <BigNumber
            label="Artistes aprovats"
            value={bd.artistes.aprovats}
            sub={`${bd.artistes.pendents.toLocaleString('ca')} pendents de revisió`}
            tone="yellow"
            to="/staff/artistes?aprovat=1"
          />
          <BigNumber
            label="Albums actius"
            value={bd.albums.actius}
            sub={bd.albums.descartats ? `${bd.albums.descartats} descartats` : undefined}
            to="/staff/albums?descartat=0"
          />
          <BigNumber
            label="Senyal diari"
            value={senyal.total}
            sub={senyal.data_recent ? `últim: ${senyal.data_recent}` : undefined}
            to="/staff/senyal"
          />
        </div>

        <div className="mt-3 bg-white text-tq-ink rounded-lg p-4">
          <p className="text-[11px] uppercase tracking-widest opacity-60 mb-2">
            Distribució cançons
          </p>
          <StackedBar
            total={bd.cancons.total}
            segments={[
              { label: 'Verificades', value: bd.cancons.verificades, color: 'var(--color-tq-success)', to: '/staff/cancons?verificada=1' },
              { label: 'Pendents',    value: bd.cancons.no_verificades_actives, color: 'var(--color-tq-warning)', to: '/staff/cancons?verificada=0' },
              { label: 'Inactives',   value: bd.cancons.inactives, color: 'var(--color-tq-neutral)' },
            ]}
          />
        </div>
      </section>

      {/* ─── Whisper LID ─── */}
      <section>
        <h2 className="text-sm uppercase tracking-widest text-white/60 mb-2">
          Whisper LID (detecció d'idioma)
        </h2>
        <div className="bg-white text-tq-ink rounded-lg p-4">
          <p className="text-[11px] uppercase tracking-widest opacity-60 mb-2">
            Cobertura ({(whisperAnalitzat / Math.max(whisperTotal, 1) * 100).toFixed(1)}% analitzat
            {whisperPendentSensePreview > 0 && (
              <> · {(whisperPendentSensePreview / Math.max(whisperTotal, 1) * 100).toFixed(1)}% sense preview Deezer</>
            )})
          </p>
          <StackedBar
            total={whisperTotal}
            segments={[
              { label: 'Català',           value: whisper.ca,                 color: 'var(--color-tq-success)',      to: '/staff/cancons?verificada=&whisper=ca' },
              { label: 'No-català',        value: whisper.no_ca,              color: 'var(--color-tq-danger)',       to: '/staff/cancons?verificada=&whisper=no_ca' },
              { label: 'Pendent (cua)',    value: whisperPendentAmbPreview,   color: 'var(--color-tq-warning)',      to: '/staff/cancons?verificada=&whisper=pendent&preview=si' },
              { label: 'Sense preview',    value: whisperPendentSensePreview, color: 'var(--color-tq-neutral-soft)', to: '/staff/cancons?verificada=&whisper=pendent&preview=no' },
            ]}
          />
          <p className="text-[11px] opacity-60 mt-3">
            {whisperPendentAmbPreview === 0 ? (
              <>Cua al dia. La cron de les 05:00 UTC processa les noves entrades (límit {whisperDailyLimit}/nit).</>
            ) : (
              <>
                Cua processable: <strong>{whisperPendentAmbPreview.toLocaleString('ca')}</strong> cançons.
                A {whisperDailyLimit}/nit, la cron arribarà al fons en{' '}
                <strong>{whisperEtaDies} {whisperEtaDies === 1 ? 'dia' : 'dies'}</strong>.
              </>
            )}
            {whisperPendentSensePreview > 0 && (
              <>
                {' '}Les <strong>{whisperPendentSensePreview.toLocaleString('ca')}</strong> cançons sense preview
                Deezer no es poden analitzar mai (no apliquen al càlcul d'ETA).
              </>
            )}
          </p>
        </div>
      </section>

      {/* ─── MusicBrainz coverage ─── */}
      {mb && (
        <section>
          <h2 className="text-sm uppercase tracking-widest text-white/60 mb-2">
            MusicBrainz
          </h2>
          <div className="grid lg:grid-cols-2 gap-3">
            {/* Artistes — desglossament */}
            <div className="bg-white text-tq-ink rounded-lg p-4">
              <p className="text-[11px] uppercase tracking-widest opacity-60 mb-2">
                Artistes aprovats (MBID assignat a {((mb.aprovats_amb_mbid / Math.max(mb.aprovats_total, 1)) * 100).toFixed(1)} %)
              </p>
              <StackedBar
                total={mb.aprovats_total}
                segments={[
                  { label: 'Amb MBID',           value: mb.aprovats_amb_mbid,            color: 'var(--color-tq-success)',      to: '/staff/artistes?aprovat=1&mb=amb_mbid' },
                  { label: 'Provat sense MBID',  value: mb.aprovats_provat_sense_mbid,   color: 'var(--color-tq-warning)',      to: '/staff/artistes?aprovat=1&mb=provat_sense_mbid' },
                  { label: 'Mai provat',         value: mb.aprovats_mai_provat,          color: 'var(--color-tq-neutral-soft)', to: '/staff/artistes?aprovat=1&mb=mai_provat' },
                ]}
              />
              <div className="mt-3">
                <StatRow
                  label="Artistes sincronitzats (alguna vegada)"
                  value={mb.artistes_sincronitzats}
                  to="/staff/artistes?aprovat=&mb=amb_mbid"
                />
                <StatRow
                  label="Auto-match bloquejat (staff)"
                  value={mb.aprovats_bloquejats}
                  to="/staff/artistes?aprovat=1&mb=bloquejat"
                />
                <StatRow
                  label="Detectats com a dissolts"
                  value={mb.artistes_dissolts_detectats}
                  to="/staff/artistes?aprovat=1&mb=dissolt"
                  accent="danger"
                />
                <StatRow
                  label="Sync més antic pendent"
                  value={mb.sync_mes_antic ? mb.sync_mes_antic.slice(0, 16).replace('T', ' ') : '—'}
                />
              </div>
            </div>

            {/* Cançons + àlbums — confirmacions MB */}
            <div className="bg-white text-tq-ink rounded-lg p-4">
              <p className="text-[11px] uppercase tracking-widest opacity-60 mb-2">
                Cançons no verificades (cobertura MB)
              </p>
              <StackedBar
                total={mb.no_verif_total}
                segments={[
                  { label: 'MB confirma cançó',     value: mb.no_verif_mb_confirmat,       color: 'var(--color-tq-success)',      to: '/staff/cancons?verificada=0&mb=confirmat' },
                  { label: 'Artista té MBID',        value: mb.no_verif_artista_amb_mbid,  color: 'var(--color-tq-warning)',      to: '/staff/cancons?verificada=0&mb=artista_amb_mbid' },
                  { label: 'Sense cobertura',        value: mb.no_verif_sense_cobertura,   color: 'var(--color-tq-neutral-soft)', to: '/staff/cancons?verificada=0&mb=sense_cobertura' },
                ]}
              />
              <div className="mt-3">
                <StatRow
                  label="Cançons confirmades per MB (totes)"
                  value={`${mb.cancons_confirmades.toLocaleString('ca')} / ${mb.cancons_verificades_total.toLocaleString('ca')} verif.`}
                  to="/staff/cancons?verificada=&mb=confirmat"
                />
                <StatRow
                  label="Cançons no confirmades (MB diu que no)"
                  value="veure"
                  to="/staff/cancons?verificada=&mb=no_confirmat"
                />
                <StatRow
                  label="Àlbums confirmats per MB"
                  value={`${mb.albums_confirmats.toLocaleString('ca')} / ${mb.albums_total.toLocaleString('ca')}`}
                  to="/staff/albums?mb=confirmat"
                />
                <StatRow
                  label="Cançons amb lletra 'cat' (Work)"
                  value={mb.cancons_lletra_cat}
                  to="/staff/cancons?verificada=&mb=cat"
                  accent="success"
                />
              </div>
              <p className="text-[11px] opacity-60 mt-3">
                "Artista té MBID" són candidates clares: la cançó encara no
                s'ha pogut conciliar amb cap recording, però sabem qui n'és
                l'artista a MB. Una sync manual pot acabar de quadrar-les.
              </p>
            </div>
          </div>
        </section>
      )}

      {/* ─── Casos sospitosos d'homonímia Deezer ─── */}
      {homonimia && (
        <section>
          <h2 className="text-sm uppercase tracking-widest text-white/60 mb-2">
            Homonímia Deezer
          </h2>
          <div className="bg-white text-tq-ink rounded-lg p-4">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <p className="text-[11px] uppercase tracking-widest opacity-60">
                  Casos sospitosos a revisar
                </p>
                <p
                  className="text-3xl font-bold font-display tabular-nums"
                  style={{ color: homonimia.casos_sospitosos > 0 ? 'var(--color-tq-warning)' : 'var(--color-tq-success)' }}
                >
                  {homonimia.casos_sospitosos.toLocaleString('ca')}
                </p>
              </div>
              <p className="text-[11px] opacity-70 max-w-md text-right">
                Un cas és sospitós si el mateix Deezer artist ID encara
                està lligat a un artista i té cançons verificades, però
                també hi ha rebuigs com a "perfil Deezer no és el nostre
                artista". Si l'staff ja ha desvinculat el Deezer ID
                erroni, el cas desapareix.
              </p>
            </div>

            {homonimia.casos_sospitosos === 0 ? (
              <p className="text-xs italic text-tq-ink/60">
                Cap cas pendent ara mateix. Quan rebutgis una cançó amb
                "perfil Deezer no és el nostre artista", apareixerà aquí
                si el Deezer ID continua lligat i té cançons verificades.
              </p>
            ) : (
              <table className="w-full text-xs border-t border-black/5">
                <thead>
                  <tr className="text-[10px] uppercase tracking-widest opacity-60">
                    <th className="text-left py-2">Artista</th>
                    <th className="text-left">Deezer artist ID</th>
                    <th className="text-right">Verificades</th>
                    <th className="text-right">Rebutjades</th>
                    <th className="text-right">Últim rebuig</th>
                  </tr>
                </thead>
                <tbody>
                  {homonimia.casos.map(c => (
                    <tr key={`${c.artista_pk}-${c.deezer_id}`} className="border-t border-black/5">
                      <td className="py-2">
                        <Link
                          to={`/staff/artistes/${c.artista_pk}`}
                          className="font-semibold underline hover:text-tq-yellow-deep"
                        >
                          {c.artista_nom}
                        </Link>
                      </td>
                      <td>
                        <a
                          href={`https://www.deezer.com/artist/${c.deezer_id}`}
                          target="_blank"
                          rel="noopener"
                          className="font-mono text-[11px] underline opacity-80 hover:opacity-100"
                        >
                          {c.deezer_id} ↗
                        </a>
                      </td>
                      <td className="text-right tabular-nums">
                        <Link
                          to={`/staff/cancons?verificada=1&artista_pk=${c.artista_pk}`}
                          className="underline hover:text-tq-yellow-deep"
                        >
                          {c.n_verificades}
                        </Link>
                      </td>
                      <td className="text-right tabular-nums" style={{ color: 'var(--color-tq-danger)' }}>
                        {c.n_rebutjades}
                      </td>
                      <td className="text-right text-[11px] opacity-70">
                        {c.last_rejected_at
                          ? c.last_rejected_at.slice(0, 10)
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}

      {/* ─── Ranking + Comunitat ─── */}
      <section className="grid lg:grid-cols-2 gap-3">
        <div className="bg-white text-tq-ink rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Ranking</h3>
          <dl className="grid grid-cols-2 gap-y-1 text-xs">
            <dt className="opacity-60">Setmanes històriques</dt>
            <dd className="text-right font-semibold tabular-nums">{ranking.setmanes_historiques}</dd>
            <dt className="opacity-60">Entrades provisionals ara</dt>
            <dd className="text-right font-semibold tabular-nums">{ranking.provisional_ara}</dd>
            <dt className="opacity-60">Últim oficial</dt>
            <dd className="text-right font-semibold">{ranking.ultim_oficial || '—'}</dd>
          </dl>
        </div>

        <div className="bg-white text-tq-ink rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Cues obertes</h3>
          <dl className="grid grid-cols-2 gap-y-1 text-xs">
            <dt className="opacity-60">
              <Link to="/staff/pendents" className="underline hover:text-tq-yellow-deep">Artistes pendents</Link>
            </dt>
            <dd className="text-right font-semibold tabular-nums">{bd.artistes.pendents}</dd>

            <dt className="opacity-60">
              <Link to="/staff/propostes" className="underline hover:text-tq-yellow-deep">Propostes d'artista</Link>
            </dt>
            <dd className="text-right font-semibold tabular-nums">{comunitat.propostes_pendents}</dd>

            <dt className="opacity-60">
              <Link to="/staff/solicituds" className="underline hover:text-tq-yellow-deep">Sol·licituds de gestió</Link>
            </dt>
            <dd className="text-right font-semibold tabular-nums">{comunitat.solicituds_pendents}</dd>

            <dt className="opacity-60">
              <Link to="/staff/feedback" className="underline hover:text-tq-yellow-deep">Feedback obert</Link>
            </dt>
            <dd className="text-right font-semibold tabular-nums">{comunitat.feedback_obert}</dd>
          </dl>
        </div>
      </section>

      {/* ─── Cron health ─── */}
      <section>
        <h2 className="text-sm uppercase tracking-widest text-white/60 mb-2">
          Pipelines (cron)
        </h2>
        <div className="bg-white text-tq-ink rounded-lg p-3">
          <ul>
            {crons.map(c => <CronStatus key={c.name} cron={c} />)}
            {crons.length === 0 && (
              <p className="text-xs text-tq-ink/60 p-3">
                Sense dades de cron disponibles. Comprova que
                <code>/var/log/topquaranta/status/</code> existeix i és llegible.
              </p>
            )}
          </ul>
        </div>
      </section>

      {/* ─── ML ─── */}
      <section>
        <h2 className="text-sm uppercase tracking-widest text-white/60 mb-2">
          Machine Learning
        </h2>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
          <BigNumber
            label="Features totals"
            value={ml.features_total}
            sub={ml.noise_count != null ? `${ml.noise_count} amb <0,05% impacte` : undefined}
          />
          <BigNumber
            label="Training set"
            value={ml.training_size}
            sub={
              ml.class_balance
                ? `${ml.class_balance.aprovades} aprov. · ${ml.class_balance.rebutjades} rebuig`
                : undefined
            }
          />
          <BigNumber
            label="Confiança mitjana"
            value={ml.confianca_avg != null ? ml.confianca_avg.toFixed(3) : '—'}
            sub={
              ml.confianca_min != null
                ? `rang ${ml.confianca_min}–${ml.confianca_max}`
                : undefined
            }
          />
          <BigNumber
            label="Cançons classificades"
            value={clsTotal}
            sub={clsNone ? `${clsNone} encara sense classe` : undefined}
            tone="yellow"
          />
        </div>

        <div className="grid lg:grid-cols-[1fr_1fr] gap-3">
          <div className="bg-white text-tq-ink rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3">Distribució de classes</h3>
            <StackedBar
              total={clsTotal}
              segments={[
                { label: 'A (aprova)',    value: clsA,    color: 'var(--color-tq-success)' },
                { label: 'B (dubte)',     value: clsB,    color: 'var(--color-tq-warning)' },
                { label: 'C (rebutja)',   value: clsC,    color: 'var(--color-tq-danger)' },
                { label: 'Sense classe',  value: clsNone, color: 'var(--color-tq-neutral-soft)' },
              ]}
            />
            {ml.model_mtime && (
              <p className="text-[11px] opacity-60 mt-3">
                Model re-entrenat: {ml.model_mtime.slice(0, 16).replace('T', ' ')}
              </p>
            )}
          </div>

          <div className="bg-white text-tq-ink rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3">
              Importància de features (top 20)
            </h3>
            <HorizontalBars
              items={topImportances}
              max={maxImp}
              formatValue={v => (v * 100).toFixed(2) + '%'}
              showDirection
            />
            <p className="text-[11px] opacity-70 mt-3 flex flex-wrap gap-x-3 gap-y-1">
              <span><span style={{ color: 'var(--color-tq-success)' }}>↑</span> més valor → aprova</span>
              <span><span style={{ color: 'var(--color-tq-danger)' }}>↓</span> més valor → rebutja</span>
              <span>· sense direcció (TF-IDF o sense dades)</span>
            </p>
            {ml.importances.length > 20 && (
              <p className="text-[11px] opacity-60 mt-1">
                {ml.importances.length - 20} features més amb importància residual.
              </p>
            )}
          </div>
        </div>
      </section>
    </section>
  )
}
