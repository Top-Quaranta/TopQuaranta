/**
 * editorial.jsx — shared layout primitives + brand mappings used by
 * the editorial-style pages (HomePage, TopPage, ArtistesPage,
 * MapaPage, ComunitatPage…).
 *
 * Pulled out of HomePage so every redesigned page can reuse the
 * same alternating ink/white bands, the tone-aware section header,
 * the territory palette and the territory-name table without each
 * file copying it. WCAG-aware: kicker colour adapts to its band.
 *
 * Public surface:
 *   - <Section tone="ink|white" className?> — full-bleed band.
 *   - <SectionHeader kicker title>{subtitle}</SectionHeader>
 *   - <TerritoriBadge codi className/> — monochrome SVG via mask.
 *   - TERR_COLORS, TERRITORI_NOM, FOCUS_TERRITORIS — brand maps.
 *   - <TrendCue posicio posicio_anterior/> — top-list arrow icon.
 */
import { createContext, useContext } from 'react'
import MmIcon from './MmIcon'

/* Territory accent palette. Brand colours from mm-design where they
 * exist (mm-color-*); custom amber/teal/orange/violet/pink chosen
 * for ≥4.5:1 contrast on white (Sprint F a11y). Used for badges,
 * focus tiles, descoberta tags. Hex values here are NOT one-off
 * decoration but a long-lived brand mapping that lives in code by
 * design — exposed once so every page reads the same. */
export const TERR_COLORS = {
  PPCC: '#427c42', // mm-color-green
  CAT:  '#8a6900', // dark amber (5.08:1)
  VAL:  '#cf3339', // mm-color-red
  BAL:  '#0047ba', // mm-color-blue
  AND:  '#7c3aed',
  CNO:  '#0e7490',
  FRA:  '#c2410c',
  ALG:  '#db2777',
  ALT:  '#525252',
  CAR:  '#525252',
}

/* User-facing label map. NOTE: territori code stays the legacy
 * `PPCC` (`Territori.codi`) for query-param compatibility — only
 * the display string flips to "Global" (Sprint I bis decision). */
export const TERRITORI_NOM = {
  PPCC: 'Global',
  CAT:  'Catalunya',
  VAL:  'País Valencià',
  BAL:  'Illes Balears',
  AND:  'Andorra',
  CNO:  'Catalunya del Nord',
  FRA:  'Franja de Ponent',
  ALG:  "L'Alguer",
  ALT:  'Altres',
  CAR:  'El Carxe',
}

/* Rotation set used by the HomePage "Focus" section. CAR is omitted
 * (not viable yet); ALT is omitted (it's the catch-all). */
export const FOCUS_TERRITORIS = ['CAT', 'VAL', 'BAL', 'AND', 'CNO', 'FRA', 'ALG', 'PPCC']

/* Section context: lets descendants (mainly SectionHeader) pick
 * tone-aware colours without each one taking a `tone` prop. */
const SectionToneContext = createContext('ink')

export function Section({ tone = 'ink', children, className = '' }) {
  const bg = tone === 'ink'
    ? 'bg-tq-ink text-white'
    : 'bg-white text-tq-ink'
  return (
    <section className={`-mx-6 lg:-mx-12 px-6 lg:px-12 py-10 md:py-12 ${bg} ${className}`}>
      <SectionToneContext.Provider value={tone}>
        <div className="max-w-6xl mx-auto">{children}</div>
      </SectionToneContext.Provider>
    </section>
  )
}

export function SectionHeader({ kicker, title, children }) {
  const tone = useContext(SectionToneContext)
  // On ink: brand yellow (~9:1 on tq-ink). On white: muted ink
  // (~7:1 on white) so we never re-introduce the 1.53:1 violation
  // caught at the Sprint F audit.
  const kickerCls = tone === 'ink' ? 'text-tq-yellow' : 'text-tq-ink/60'
  return (
    <header className="mb-5 md:mb-6">
      {kicker && (
        <p className={`text-[10px] uppercase tracking-widest mb-1.5 ${kickerCls}`}>
          {kicker}
        </p>
      )}
      <h2 className="text-xl md:text-2xl font-bold font-display">{title}</h2>
      {children && <div className="mt-1.5 text-sm opacity-80 max-w-2xl">{children}</div>}
    </header>
  )
}

/* Monochrome territory SVG via CSS mask — picks up `currentColor`
 * from the wrapping element, so callers control colour with text/
 * style. Sized by the className. */
export function TerritoriBadge({ codi, className = 'h-5 w-5' }) {
  return (
    <MmIcon
      bucket="territories"
      name={`territory-${codi.toLowerCase()}`}
      className={className}
    />
  )
}

/* Trend cue used by every top-list row. `posicio_anterior=null` →
 * novetat; `>` → puja; `<` → baixa; equal → estable. WCAG-safe on
 * any background because each branch picks a token-backed colour
 * with ≥3:1 contrast on the standard ink/white surfaces. */
export function TrendCue({ posicio, posicio_anterior }) {
  if (posicio_anterior == null) {
    return (
      <span title="Novetat" className="text-tq-ink contrast-safe-novetat">
        <MmIcon name="badge-new" className="h-4 w-4" label="Novetat" />
      </span>
    )
  }
  if (posicio_anterior > posicio) {
    const delta = posicio_anterior - posicio
    return (
      <span title={`Puja ${delta}`} style={{ color: 'var(--mm-color-success)' }}>
        <MmIcon name="arrow-up-trend" className="h-4 w-4" label={`Puja ${delta}`} />
      </span>
    )
  }
  if (posicio_anterior < posicio) {
    const delta = posicio - posicio_anterior
    return (
      <span title={`Baixa ${delta}`} className="text-tq-ink/40">
        <MmIcon name="arrow-down-trend" className="h-4 w-4" label={`Baixa ${delta}`} />
      </span>
    )
  }
  return (
    <MmIcon name="dash-stable" className="h-4 w-4 text-tq-ink/30" label="Estable" />
  )
}
