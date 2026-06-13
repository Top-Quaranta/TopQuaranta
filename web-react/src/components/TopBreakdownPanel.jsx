/**
 * TopBreakdownPanel — algorithm transparency for a single cançó.
 *
 * Single source of truth for both the public CancoPage and the staff
 * CancoEditPage: hits `/api/v1/cancons/<slug>/top-breakdown/` which
 * picks the right payload by the viewer's permission. Anonymous users
 * get only territoris where the song is in the current TopProvisional;
 * staff and verified `UserArtista` over the main artist also see the
 * eligible-but-not-ranked territoris with theoretical scores AND a
 * compact numeric table (the prose alone is too dry for diagnostics).
 *
 * Visibility rule: returns null silently when there's nothing to show
 * (so anonymous viewers of a song outside the top never see the
 * section). Errors also fail-silent — the panel is non-essential to
 * the page.
 *
 * Visual: yellow accent on top-3 positions, success/warning/danger
 * tokens for the factor pills, score bar that highlights the
 * dominant penalty. Designed to coexist with the page's main
 * metadata without competing for attention.
 */
import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const MIN_AGE_FACTOR_TO_MENTION = 0.95

function fmtScore(v) {
  if (v == null) return '—'
  return Math.round(v).toLocaleString('ca')
}

function fmtPct(v) {
  if (v == null) return '0%'
  return `${Number(v).toLocaleString('ca', { maximumFractionDigits: 1 })}%`
}

function fmtNum(v) {
  if (v == null) return '—'
  return Number(v).toLocaleString('ca')
}

/* Colour for the position pill: gold for #1, silver for #2, bronze
 * for #3, ink for the rest. Falls back to neutral for theoretical
 * (out-of-top) entries. */
function positionTone(posicio) {
  if (posicio == null) return { bg: 'rgba(156, 163, 175, 0.15)', fg: 'var(--color-tq-neutral, #6b7280)', label: 'fora del top' }
  if (posicio === 1) return { bg: 'var(--color-tq-yellow)', fg: 'var(--mm-color-ink, #0a0a0a)' }
  if (posicio <= 3) return { bg: 'var(--color-tq-yellow-soft, #fde68a)', fg: 'var(--color-tq-yellow-deep, #ca8a04)' }
  if (posicio <= 10) return { bg: 'rgba(16, 185, 129, 0.15)', fg: 'var(--color-tq-success)' }
  // #11+: soft slate so it doesn't mimic the "fora del top" gray nor
  // shout like the top-3 podium tones.
  return { bg: 'rgba(10, 10, 10, 0.08)', fg: 'var(--color-tq-ink)' }
}

/* Subtle severity for a penalty percentage — drives the pill colour
 * inside the numeric table. >25 → danger; 5..25 → warning; else success.
 *
 * Note on red: we use `#b91c1c` (red-700) for danger text instead of
 * the system's bright `--color-tq-danger` (#ef4444). The bright red
 * is illegible on dark surfaces and saturates badly on the light pink
 * tint we use as background. Darker red sits comfortably on both
 * white cards and the staff dark body if the panel ever bleeds.
 */
const RED_TEXT = '#b91c1c'
function penaltyTone(pct) {
  if (!pct) return { bg: 'rgba(16, 185, 129, 0.12)', fg: 'var(--color-tq-success)' }
  if (pct < 5) return { bg: 'rgba(16, 185, 129, 0.12)', fg: 'var(--color-tq-success)' }
  if (pct < 25) return { bg: 'rgba(250, 204, 21, 0.18)', fg: 'var(--color-tq-yellow-deep)' }
  return { bg: 'rgba(239, 68, 68, 0.15)', fg: RED_TEXT }
}

function explain(entry) {
  const lines = []
  // The algorithm has four branches that compute escoltes_setmanals
  // with very different precision. Surface the difference honestly so
  // the user knows when the number is a real 7-day delta vs a
  // lifetime average estimate.
  const escoltes = entry.escoltes_setmanals.toLocaleString('ca')
  const efectives =
    entry.weekly_plays_eff != null ? entry.weekly_plays_eff.toLocaleString('ca') : null
  if (entry.senyal_disponible === false) {
    lines.push(
      `Encara no tenim cap senyal de Last.fm per a aquesta cançó. Apareixerà aquí quan el cron diari l'ingereixi (06:00 UTC).`
    )
  } else if (entry.metode_calcul === 'mitjana_vida') {
    lines.push(
      `Estimació: ~${escoltes} escoltes setmanals (mitjana de tota la vida disponible). Encara no tenim prou historial de mostres per calcular el delta dels últims 7 dies de manera precisa; aquesta xifra fa de pont mentrestant.`
    )
  } else if (entry.metode_calcul === 'release_recent') {
    lines.push(
      `Estimació: ~${escoltes} escoltes setmanals (extrapolades des del llançament — la cançó es va publicar fa pocs dies).`
    )
  } else if (entry.metode_calcul === 'delta_parcial') {
    lines.push(
      `Aquesta setmana ha acumulat aproximadament ${escoltes} escoltes a Last.fm (delta calculat amb una mostra parcial).`
    )
  } else {
    lines.push(
      `Aquesta setmana ha acumulat ${escoltes} escoltes a Last.fm.`
    )
  }
  if (entry.soft_cap_aplicat && efectives) {
    lines.push(
      `Aquesta cançó té moltíssimes més escoltes que el que és habitual al seu territori, així que apliquem el sostre suau: de ${escoltes} escoltes brutes en compten ${efectives} efectives per al càlcul. No baixa la cançó del top; només evita que un pic aixafe la resta.`
    )
  }
  if (entry.age_factor != null && entry.age_factor < MIN_AGE_FACTOR_TO_MENTION) {
    const dies = entry.dies_des_del_llancament
    if (dies != null) {
      lines.push(
        `La cançó fa ${dies} dies que és disponible. A mesura que s'apropa als 365 dies, el top la penalitza progressivament.`
      )
    }
  }
  if (entry.past_top_penalty_pct > 0) {
    const n = (entry.setmanes_al_top || []).length
    if (n > 0) {
      lines.push(
        `Ha aparegut ${n} ${n === 1 ? 'vegada' : 'vegades'} al top anteriorment, cosa que li aplica una penalització acumulada del ${fmtPct(entry.past_top_penalty_pct)}.`
      )
    } else {
      lines.push(
        `Penalització per aparicions prèvies al top: ${fmtPct(entry.past_top_penalty_pct)}.`
      )
    }
  }
  if (entry.monopoli_artista_pct > 0) {
    lines.push(
      `L'artista ja té altres cançons al top aquesta setmana, cosa que reparteix la puntuació (−${fmtPct(entry.monopoli_artista_pct)}).`
    )
  }
  if (entry.monopoli_album_pct > 0) {
    lines.push(
      `L'àlbum ja té altres cançons al top aquesta setmana (−${fmtPct(entry.monopoli_album_pct)}).`
    )
  }
  if (entry.posicio == null) {
    if (entry.senyal_disponible === false) {
      lines.push(
        `Aquesta cançó no és al top aquesta setmana i encara no podem calcular puntuació teòrica fins que arribin més dades de senyal.`
      )
    } else {
      lines.push(
        `Aquesta cançó no és al top aquesta setmana. Amb les escoltes actuals i les penalitzacions aplicades, la seua puntuació teòrica és ${fmtScore(entry.score_final)}.`
      )
    }
  }
  return lines
}

function PositionBadge({ posicio }) {
  const t = positionTone(posicio)
  return (
    <span
      className="inline-flex items-center justify-center min-w-[3rem] h-12 px-3 rounded-lg font-display font-bold tabular-nums"
      style={{ background: t.bg, color: t.fg, fontSize: '1.5rem' }}
    >
      {posicio != null ? `#${posicio}` : '—'}
    </span>
  )
}

function FactorPill({ label, value, formatted, tone }) {
  return (
    <div
      className="flex flex-col gap-0.5 px-3 py-2 rounded-md"
      style={{ background: tone.bg }}
    >
      <span className="text-[10px] uppercase tracking-wide opacity-70" style={{ color: tone.fg }}>
        {label}
      </span>
      <span className="text-sm font-semibold tabular-nums" style={{ color: tone.fg }}>
        {formatted ?? fmtPct(value)}
      </span>
    </div>
  )
}

function NumericTable({ entries }) {
  /* Compact diagnostic table. Only rendered for staff/elevated viewers
   * — gives them the same visibility they had in the legacy
   * RankingBreakdownPanel without leaving the unified component. */
  return (
    <div
      className="mt-4 rounded-lg overflow-hidden"
      style={{ border: '1px solid rgba(0,0,0,0.06)' }}
    >
      <table className="w-full text-xs">
        <thead style={{ background: 'rgba(0,0,0,0.04)' }}>
          <tr>
            <th className="text-left px-2 py-1.5 font-semibold uppercase tracking-wide text-[10px] opacity-60">Territori</th>
            <th className="text-right px-2 py-1.5 font-semibold uppercase tracking-wide text-[10px] opacity-60">#</th>
            <th className="text-right px-2 py-1.5 font-semibold uppercase tracking-wide text-[10px] opacity-60" title="Escoltes setmanals (rolling 7 dies)">Escoltes 7d</th>
            <th className="text-right px-2 py-1.5 font-semibold uppercase tracking-wide text-[10px] opacity-60" title="age_factor: 1 - (dies/365)^2.5">Antiguitat</th>
            <th className="text-right px-2 py-1.5 font-semibold uppercase tracking-wide text-[10px] opacity-60" title="Penalització acumulada per aparicions prèvies al top">Top passat</th>
            <th className="text-right px-2 py-1.5 font-semibold uppercase tracking-wide text-[10px] opacity-60" title="Penalització per altres cançons del mateix àlbum/artista al top">Monopoli</th>
            <th className="text-right px-2 py-1.5 font-semibold uppercase tracking-wide text-[10px] opacity-60">Score</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => {
            const monopoli = (e.monopoli_album_pct || 0) + (e.monopoli_artista_pct || 0)
            return (
              <tr
                key={`${e.territori}-${i}`}
                style={{
                  background: e.is_at_top ? undefined : 'rgba(156, 163, 175, 0.06)',
                  borderTop: i > 0 ? '1px solid rgba(0,0,0,0.04)' : undefined,
                }}
              >
                <td className="px-2 py-1.5 font-semibold">
                  {e.territori}
                  <span className="ml-1 text-[10px] opacity-50 font-normal">{e.nom_territori}</span>
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums font-bold">
                  {e.posicio != null ? `#${e.posicio}` : <span className="opacity-30">—</span>}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {e.soft_cap_aplicat && e.weekly_plays_eff != null ? (
                    <span title="Escoltes brutes → efectives (sostre suau)">
                      <span className="opacity-50 line-through">{fmtNum(e.escoltes_setmanals)}</span>
                      <span className="mx-0.5 opacity-40">→</span>
                      <span style={{ color: 'var(--color-tq-yellow-deep)' }}>{fmtNum(e.weekly_plays_eff)}</span>
                    </span>
                  ) : (
                    fmtNum(e.escoltes_setmanals)
                  )}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums" style={{
                  color: e.age_factor != null && e.age_factor < 0.95
                    ? 'var(--color-tq-yellow-deep)'
                    : undefined,
                }}>
                  {e.age_factor != null ? `${(e.age_factor * 100).toFixed(1)}%` : '—'}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums" style={{
                  color: e.past_top_penalty_pct > 0 ? RED_TEXT : undefined,
                }}>
                  {e.past_top_penalty_pct ? `−${fmtPct(e.past_top_penalty_pct)}` : '—'}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums" style={{
                  color: monopoli > 0 ? RED_TEXT : undefined,
                }}>
                  {monopoli > 0 ? `−${fmtPct(monopoli)}` : '—'}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums font-bold">
                  {fmtScore(e.score_final)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function EntryDetail({ entry }) {
  const lines = explain(entry)
  const ageDisplay = entry.age_factor != null ? `${(entry.age_factor * 100).toFixed(0)}%` : '—'
  const monopoli = (entry.monopoli_album_pct || 0) + (entry.monopoli_artista_pct || 0)
  return (
    <article style={{ color: 'var(--color-tq-ink, #0a0a0a)' }}>
      {/* Hero row: position + score */}
      <div className="flex items-center gap-3 mb-3">
        <PositionBadge posicio={entry.posicio} />
        <div className="flex-1 min-w-0">
          <p className="text-xs uppercase tracking-wide opacity-60">{entry.nom_territori}</p>
          <p className="text-2xl font-display font-bold tabular-nums leading-tight">
            {fmtScore(entry.score_final)}
            <span className="ml-1 text-xs font-normal opacity-50">punts</span>
          </p>
          {entry.posicio == null && (
            <p
              className="text-[11px] uppercase tracking-wide font-semibold mt-0.5"
              style={{ color: 'var(--color-tq-neutral, #6b7280)' }}
            >
              Puntuació teòrica
            </p>
          )}
        </div>
      </div>

      {/* Factor pills — visual at-a-glance breakdown */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
        <FactorPill
          label="Escoltes 7d"
          formatted={
            entry.senyal_disponible === false
              ? 'sense historial'
              : fmtNum(entry.escoltes_setmanals)
          }
          tone={
            entry.senyal_disponible === false
              ? { bg: 'rgba(156, 163, 175, 0.15)', fg: 'var(--color-tq-neutral, #6b7280)' }
              : { bg: 'rgba(10, 10, 10, 0.05)', fg: 'var(--color-tq-ink)' }
          }
        />
        <FactorPill
          label="Antiguitat"
          formatted={ageDisplay}
          tone={
            entry.age_factor != null && entry.age_factor < 0.95
              ? { bg: 'rgba(250, 204, 21, 0.18)', fg: 'var(--color-tq-yellow-deep)' }
              : { bg: 'rgba(16, 185, 129, 0.12)', fg: 'var(--color-tq-success)' }
          }
        />
        <FactorPill
          label="Top passat"
          formatted={entry.past_top_penalty_pct ? `−${fmtPct(entry.past_top_penalty_pct)}` : 'cap'}
          tone={penaltyTone(entry.past_top_penalty_pct)}
        />
        <FactorPill
          label="Monopoli"
          formatted={monopoli ? `−${fmtPct(monopoli)}` : 'cap'}
          tone={penaltyTone(monopoli)}
        />
      </div>

      {/* Prose explanation */}
      <ul className="space-y-1.5 list-none text-sm leading-relaxed">
        {lines.map((l, i) => (
          <li key={i} className="flex gap-2">
            <span style={{ color: 'var(--color-tq-yellow)' }}>·</span>
            <span>{l}</span>
          </li>
        ))}
      </ul>

      {/* Past-top history detail */}
      {(entry.setmanes_al_top || []).length > 0 && (
        <details className="mt-3 text-xs opacity-80">
          <summary className="cursor-pointer font-semibold uppercase tracking-wide opacity-70">
            Aparicions anteriors al top
          </summary>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {entry.setmanes_al_top.map((w, i) => (
              <li
                key={i}
                className="inline-flex items-baseline gap-1 px-2 py-0.5 rounded-full text-[11px]"
                style={{
                  background: 'rgba(10, 10, 10, 0.05)',
                  color: 'var(--color-tq-ink)',
                }}
              >
                <span className="font-bold tabular-nums">#{w.posicio}</span>
                <span className="opacity-60">·</span>
                <span className="opacity-70">{w.setmana}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  )
}

export default function TopBreakdownPanel({ slug }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)

  useEffect(() => {
    if (!slug) return
    api
      .get(`/cancons/${slug}/top-breakdown/`)
      .then(setData)
      .catch(e => setErr(e.message))
  }, [slug])

  if (err) return null
  if (!data) return null
  if (!data.entries || data.entries.length === 0) return null

  const elevated = data.elevated_view
  const label = elevated ? 'Com ho fa al top?' : 'Per què està aquí?'
  const entry = data.entries[Math.min(active, data.entries.length - 1)]

  return (
    <section
      className="bg-white text-tq-ink rounded-lg shadow-sm overflow-hidden mt-4"
      style={{ border: '1px solid rgba(0,0,0,0.05)' }}
    >
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left transition-colors"
        style={{
          background: open
            ? 'linear-gradient(90deg, var(--color-tq-yellow) 0%, var(--color-tq-yellow-soft, #fde68a) 100%)'
            : undefined,
        }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span
            aria-hidden="true"
            className="inline-flex items-center justify-center w-6 h-6 rounded-full font-bold text-sm"
            style={{
              background: open ? 'var(--color-tq-ink)' : 'var(--color-tq-yellow)',
              color: open ? 'var(--color-tq-yellow)' : 'var(--color-tq-ink)',
            }}
          >
            ?
          </span>
          <span className="text-sm font-display font-semibold">
            {label}
          </span>
          {!open && elevated && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded-full font-semibold uppercase tracking-wide"
              style={{
                background: 'var(--color-tq-ink)',
                color: 'var(--color-tq-yellow)',
              }}
            >
              gestor
            </span>
          )}
        </div>
        <span className="text-xs opacity-70 shrink-0">
          {open ? '▲ amaga' : `▼ ${data.entries.length} ${data.entries.length === 1 ? 'territori' : 'territoris'}`}
        </span>
      </button>

      {open && (
        <div className="p-4">
          {data.entries.length > 1 && (
            <nav className="flex flex-wrap gap-1 mb-4" aria-label="Tria de territori">
              {data.entries.map((e, i) => {
                const isActive = i === active
                return (
                  <button
                    key={`${e.territori}-${i}`}
                    type="button"
                    onClick={() => setActive(i)}
                    className={'px-3 py-1 rounded-full text-xs font-semibold transition-all ' + (
                      isActive
                        ? 'shadow-sm'
                        : 'hover:opacity-80'
                    )}
                    style={isActive ? {
                      background: 'var(--color-tq-ink)',
                      color: 'var(--color-tq-yellow)',
                    } : {
                      background: e.is_at_top ? 'rgba(10, 10, 10, 0.06)' : 'rgba(156, 163, 175, 0.10)',
                      color: 'var(--color-tq-ink)',
                    }}
                    title={e.posicio != null ? `#${e.posicio}` : 'fora del top (teòric)'}
                  >
                    {e.territori}
                    {e.posicio != null ? (
                      <span className="ml-1 opacity-60">#{e.posicio}</span>
                    ) : (
                      <span className="ml-1 opacity-40">—</span>
                    )}
                  </button>
                )
              })}
            </nav>
          )}

          <EntryDetail entry={entry} />

          {elevated && (
            <>
              <NumericTable entries={data.entries} />
              <p className="mt-3 text-[11px] opacity-50 italic">
                Veus el desglossament complet (gestor de l'artista o staff). Les
                files grises són teòriques: la cançó no és al top en aquell
                territori i el càlcul exclou les penalitzacions de monopoli.
              </p>
            </>
          )}
        </div>
      )}
    </section>
  )
}
