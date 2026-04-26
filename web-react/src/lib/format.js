/**
 * Shared formatting helpers — kept in one place so the Catalan month
 * names and date layouts don't drift across the SPA.
 *
 * All inputs are ISO-style strings (YYYY-MM-DD or full ISO datetime);
 * functions tolerate null/undefined and return an empty string in that
 * case so callers can interpolate the result without guards.
 */

export const MESOS_CATALA = [
  'gener', 'febrer', 'març', 'abril', 'maig', 'juny',
  'juliol', 'agost', 'setembre', 'octubre', 'novembre', 'desembre',
]

/** "18 d'abril de 2026" — long, lowercase month, with Catalan apostrophe rule. */
export function fmtDataLlarga(isoDate) {
  if (!isoDate) return ''
  const ymd = isoDate.slice(0, 10)
  const [y, m, d] = ymd.split('-').map(Number)
  if (!y || !m || !d) return ''
  const month = MESOS_CATALA[m - 1]
  // Catalan apostrofa "abril", "agost", "octubre" (vowel-initial) and
  // their elision uses "d'" before them. The simple rule: vowel start.
  const apostrofa = /^[aeiouàèéíòóú]/i.test(month)
  return `${d} ${apostrofa ? "d'" : 'de '}${month} de ${y}`
}

/** "18/04/2026" — compact numeric form. */
export function fmtDataCurta(isoDate) {
  if (!isoDate) return ''
  const ymd = isoDate.slice(0, 10)
  const [y, m, d] = ymd.split('-').map(Number)
  if (!y || !m || !d) return ''
  return `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${y}`
}

/** "2026" — extracts just the year, useful for compact discography rows. */
export function fmtAny(isoDate) {
  if (!isoDate) return ''
  return isoDate.slice(0, 4)
}
