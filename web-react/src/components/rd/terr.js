/**
 * rd/terr.js — territory palette + helpers for the redisseny surface.
 *
 * Single source for the deep/accent pair and the silhouette key, keyed by
 * the BACKEND territory code (CAT/VAL/BAL/AND/CNO/FRA/ALG/CAR/ALT/PPCC).
 * The deep/accent hexes mirror feed-tokens.json (and the `--color-terr-*`
 * @theme tokens). User-facing NAMES are NOT redefined here — they are read
 * from the conserved `TERRITORI_NOM` mapping in editorial.jsx, so the
 * "PPCC → Global, never an end-user PPCC label" contract stays in one place.
 *
 * CAT uses the senyera silhouette (`territory-ppcc.svg`), never the cross —
 * a redisseny brand rule from the handoff.
 */
import { TERRITORI_NOM } from '../editorial'

/* deep/accent per backend code (kit palette). */
const PAL = {
  PPCC: ['#2f5a2f', '#7bbf7b'],
  CAT:  ['#2f5a2f', '#7bbf7b'],
  VAL:  ['#8a4a1e', '#e8a44d'],
  BAL:  ['#1f5a63', '#5cc0cc'],
  AND:  ['#2c3f63', '#7595cf'],
  CNO:  ['#7a2730', '#dd7882'],
  FRA:  ['#6e5520', '#d8b257'],
  ALG:  ['#7a3340', '#d986a0'],
  ALT:  ['#33373d', '#9aa0a6'],
  CAR:  ['#4a4034', '#bda988'],
}

/* Compact public label (never "PPCC"). */
const SHORT = {
  PPCC: 'Global', CAT: 'Catalunya', VAL: 'València', BAL: 'Balears',
  AND: 'Andorra', CNO: 'Nord', FRA: 'Franja', ALG: "L'Alguer",
  ALT: 'Altres', CAR: 'El Carxe',
}

/* Movement semantics (mirror `--color-mv-*`). */
export const MV = {
  up: '#7bbf7b', down: '#dd7882', new: '#facc15',
  eq: 'rgba(255,255,255,0.40)', re: '#e8a44d',
}

export function terr(code) {
  const c = (code || 'ALT').toUpperCase()
  const [deep, accent] = PAL[c] || PAL.ALT
  return {
    code: c,
    nom: TERRITORI_NOM[c] || c,        // full user-facing (PPCC → "Global")
    short: SHORT[c] || TERRITORI_NOM[c] || c,
    deep,
    accent,
    // SVG silhouette name (mm-design territories bucket). CAT → senyera.
    icon: c === 'CAT' || c === 'PPCC' ? 'ppcc' : c.toLowerCase(),
  }
}

export function terrAccent(code) { return terr(code).accent }
export function terrDeep(code) { return terr(code).deep }

/* shade(hex, amt): amt>0 mixes toward white, amt<0 toward black.
   Returns an rgb() string. Mirrors the prototype's shade(). */
export function shade(hex, amt) {
  const h = String(hex).replace('#', '')
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  const n = parseInt(full, 16)
  let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255
  const t = amt < 0 ? 0 : 255, p = Math.abs(amt)
  r = Math.round((t - r) * p + r)
  g = Math.round((t - g) * p + g)
  b = Math.round((t - b) * p + b)
  return `rgb(${r},${g},${b})`
}
