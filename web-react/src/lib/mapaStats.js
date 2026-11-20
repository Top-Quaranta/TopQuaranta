/** Index `/mapa/stats/` rows by the same key the GeoJSON features use.
 *  The API names the territory `codi`; reading `territori` here left every
 *  municipi (and territori) lookup empty, so the panel showed zeros. */
export function indexaStats(stats, level) {
  const m = {}
  for (const r of stats) {
    if (level === 'territori') m[r.codi] = r
    else if (level === 'comarca') m[r.comarca] = r
    else m[`${r.codi}::${r.comarca}::${r.municipi}`] = r
  }
  return m
}
