/**
 * rd/primitives.jsx — shared building blocks for the redisseny surface.
 *
 * The network-kit visual language ported to the web: Anton (crits),
 * Instrument Serif italic (whisper), Bricolage (body), liquid-glass
 * surfaces over colour glows. Visual rules live in index.css under
 * `.rd-*`; these components are the thin React layer over them.
 *
 * Exports: Band, Glow, Glass, Btn, Kicker, Crit, Numeral, Move,
 * TerrLogo, RdCover.
 *
 * Light mode (additive, 2026-06-23 — staff retrofit option B): `Glass`
 * takes `tone="light"` (white card) and `Btn` takes `tone` (primary |
 * secondary | outline | danger | ghost) + `size` (sm | md) for the
 * light surface. These mirror staff `StaffTable` byte-for-byte and are
 * NOT yet consumed by any page — the canon just gained the layer.
 */
import { createElement } from 'react'
import MmIcon from '../MmIcon'
import { terr, MV, shade } from './terr'

/* Full-bleed band. tone: ink | ink2 | hero | top-hero | yellow. */
export function Band({ tone = 'ink', className = '', children, ...rest }) {
  const mod = tone === 'ink' ? '' : ` rd-band--${tone}`
  return (
    <section className={`rd-band${mod} ${className}`} {...rest}>
      <div className="rd-wrap">{children}</div>
    </section>
  )
}

/* Decorative colour glow behind a band header. `color` overrides the
   default green/terra; pass the territory deep for territorial heroes. */
export function Glow({ variant = 'a', color, style }) {
  const s = color
    ? { background: `radial-gradient(circle, ${color}, transparent 70%)`, ...style }
    : style
  return <div className={`rd-glow rd-glow--${variant}`} style={s} aria-hidden="true" />
}

/* Surface primitive.
   tone: ink (default) — the dark liquid-glass redisseny surface
   (`.rd-glass`, solid on mobile, blurred on desktop — see CSS).
   tone: light — a white card with ink text (mirrors the staff
   `StaffTable::TableCard` byte-for-byte). LIGHT MODE is additive for the
   staff retrofit (option B: staff stays white, rd gains a light layer);
   it uses Tailwind utilities so it renders correctly OUTSIDE `.rd-root`
   too. The ink path is unchanged. */
const GLASS_LIGHT = 'bg-white text-tq-ink rounded-lg border border-black/5 overflow-hidden'
export function Glass({ as = 'div', tone = 'ink', className = '', children, ...rest }) {
  const base = tone === 'light' ? GLASS_LIGHT : 'rd-glass'
  return createElement(as, { className: `${base} ${className}`, ...rest }, children)
}

/* Button.
   Default (ink/redisseny): pill, variant: hot | ghost (`.rd-btn`).
   LIGHT MODE (additive): pass `tone` (primary | secondary | outline |
   danger | ghost) + `size` (sm | md) to render the light-surface button.
   The tone/size class strings mirror staff `StaffTable::Btn`
   byte-for-byte, so a future staff swap is pixel-identical. When `tone`
   is omitted the existing pill path is unchanged. Renders <button> or,
   with `href`, <a>. */
const BTN_LIGHT_TONES = {
  primary: 'bg-tq-ink text-tq-yellow hover:bg-tq-ink/90',
  secondary: 'bg-transparent text-tq-ink border border-tq-ink/20 hover:bg-tq-ink/5',
  outline: 'bg-transparent text-white border border-white/30 hover:bg-white/10',
  danger: 'bg-red-600 text-white hover:bg-red-700',
  ghost: 'text-tq-ink/70 hover:text-tq-ink hover:bg-tq-ink/5',
}
const BTN_LIGHT_SIZES = {
  sm: 'text-xs font-semibold px-2.5 py-1 rounded',
  md: 'text-sm font-semibold px-3 py-1.5 rounded',
}
export function Btn({ variant = 'hot', tone, size = 'sm', className = '', href, children, ...rest }) {
  if (tone) {
    const cls = `${BTN_LIGHT_TONES[tone] || BTN_LIGHT_TONES.primary} ${BTN_LIGHT_SIZES[size] || BTN_LIGHT_SIZES.sm} transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${className}`.trim()
    if (href) return <a href={href} className={cls} {...rest}>{children}</a>
    return <button type="button" className={cls} {...rest}>{children}</button>
  }
  const cls = `rd-btn rd-btn--${variant} ${className}`
  if (href) return <a href={href} className={cls} {...rest}>{children}</a>
  return <button type="button" className={cls} {...rest}>{children}</button>
}

/* Whisper kicker — Instrument Serif italic. */
export function Kicker({ children, color, className = '' }) {
  return (
    <span className={`rd-kicker ${className}`} style={color ? { color } : undefined}>
      {children}
    </span>
  )
}

/* Crit — Anton all-caps voice. Defaults to an <h2>; pass `as`. */
export function Crit({ as = 'h2', children, size, color, className = '', style }) {
  return createElement(
    as,
    { className: `rd-crit ${className}`, style: { ...(size ? { fontSize: size } : {}), ...(color ? { color } : {}), margin: 0, ...style } },
    children,
  )
}

/* Anton tabular numeral (top positions, KPIs). */
export function Numeral({ n, size = 30, color = '#fff', className = '', style }) {
  return (
    <span
      className={className}
      style={{ fontFamily: 'var(--font-crit)', fontSize: size, lineHeight: 0.86, color, fontVariantNumeric: 'tabular-nums', ...style }}
    >
      {n}
    </span>
  )
}

/* Movement cue — 5 semantic states, constant colours across territories.
   Reads the same (posicio, posicio_anterior) contract as the legacy
   TrendCue. `re` (re-entry) can be forced via the explicit prop. */
export function Move({ posicio, posicio_anterior, re = false, size = 22, showNum = true }) {
  if (re) {
    return <span style={{ fontFamily: 'var(--font-crit)', color: MV.re, fontSize: size * 0.78 }} title="Reentrada">RE</span>
  }
  if (posicio_anterior == null) {
    return <span style={{ fontFamily: 'var(--font-crit)', color: MV.new, fontSize: size * 0.82, letterSpacing: size * 0.03 }} title="Novetat">NOU</span>
  }
  const delta = posicio_anterior - posicio          // >0 up, <0 down
  if (delta === 0) {
    return <span aria-label="Estable" title="Estable" style={{ display: 'inline-block', width: size * 0.62, height: Math.max(2, size * 0.13), background: MV.eq, borderRadius: 2 }} />
  }
  const up = delta > 0
  const col = up ? MV.up : MV.down
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: size * 0.18 }} title={up ? `Puja ${delta}` : `Baixa ${-delta}`}>
      <span
        aria-hidden="true"
        style={{
          width: 0, height: 0,
          borderLeft: `${size * 0.30}px solid transparent`,
          borderRight: `${size * 0.30}px solid transparent`,
          [up ? 'borderBottom' : 'borderTop']: `${size * 0.40}px solid ${col}`,
        }}
      />
      {showNum && (
        <span style={{ color: col, fontFamily: 'var(--font-body)', fontWeight: 800, fontSize: size * 0.78 }}>
          {Math.abs(delta)}
        </span>
      )}
    </span>
  )
}

/* Territory silhouette recoloured to the territory accent (mm-design SVG
   via mask). CAT → senyera (handled in terr()). `label` makes it SR-visible. */
export function TerrLogo({ code, className = 'h-5 w-5', label, color }) {
  const t = terr(code)
  return (
    <span style={{ color: color || t.accent, display: 'inline-flex' }}>
      <MmIcon bucket="territories" name={`territory-${t.icon}`} className={className} label={label} />
    </span>
  )
}

/* Cover — the real Deezer art is sacred (never cropped/overlaid). When
   `src` is present we show it; otherwise a branded fallback tile: a tint
   gradient + Anton initial + interior keyline. */
export function RdCover({ src, alt = '', label = '?', tint = '#2a2740', size = 56, radius = 10, className = '' }) {
  // A numeric size → fixed square; a string size (e.g. "100%") → full-width
  // square via aspect-ratio (responsive grid cells).
  const fluid = typeof size !== 'number'
  const box = fluid
    ? { width: '100%', aspectRatio: '1', borderRadius: radius, flexShrink: 0 }
    : { width: size, height: size, borderRadius: radius, flexShrink: 0 }
  if (src) {
    return (
      <img
        src={src}
        alt={alt}
        className={className}
        loading="lazy"
        style={{ ...box, objectFit: 'cover', display: 'block' }}
      />
    )
  }
  const initial = String(label || '?').trim().charAt(0).toUpperCase() || '?'
  return (
    <div
      className={className}
      aria-hidden={alt ? undefined : 'true'}
      style={{
        ...box,
        display: 'grid', placeItems: 'center',
        background: `linear-gradient(152deg, ${shade(tint, 0.16)} 0%, ${shade(tint, -0.22)} 100%)`,
        boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.08)',
      }}
    >
      <span style={{ fontFamily: 'var(--font-crit)', fontSize: fluid ? '2.4rem' : size * 0.46, color: 'rgba(255,255,255,0.9)', lineHeight: 1 }}>
        {initial}
      </span>
    </div>
  )
}
