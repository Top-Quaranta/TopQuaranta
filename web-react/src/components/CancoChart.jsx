/**
 * CancoChart — per-territory ranking-evolution line chart for a song.
 *
 * Split out of CancoPage and loaded via React.lazy so recharts
 * (~115 KB gz, with its d3 deps) is NOT pulled into the public entry
 * bundle. Before this split, CancoPage imported recharts statically
 * and was itself a static import in App.jsx, so the chunk was
 * modulepreloaded on EVERY public page (Home/Top/Artista/Album/Canco),
 * adding ~1.2-1.5s of unused JS to each (LCP audit Task 1, 2026-05).
 *
 * The cover/title/text above are the LCP-critical content and paint
 * immediately; this chart streams in a few ms later inside a Suspense
 * boundary whose fallback reserves the same height (no CLS).
 *
 * Props:
 *   - historial:  array of weekly rows ({ setmana, <TERR>: posicio, … })
 *   - territoris: array of territory codes that have a line
 */
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { TERRITORI_NOM } from './editorial'
// Territory chart-series colour = canonical deep, from the single
// territory-token source (rd/terr.js). Fase 1 unification: replaces the
// old per-chart TERRITORI_COLORS copy (which diverged + lacked CAR).
import { terrChart } from './rd/terr'

export default function CancoChart({ historial, territoris }) {
  return (
    <ResponsiveContainer>
      <LineChart data={historial} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis
          dataKey="setmana"
          tickFormatter={d => d.slice(5)}
          tick={{ fill: '#6b7280', fontSize: 11 }}
          stroke="#9ca3af"
        />
        <YAxis
          reversed
          domain={[1, 40]}
          tick={{ fill: '#6b7280', fontSize: 11 }}
          stroke="#9ca3af"
          label={{ value: 'Posició', angle: -90, position: 'insideLeft', fill: '#6b7280', style: { fontSize: 11 } }}
        />
        <Tooltip
          formatter={(v, n) => [`#${v}`, TERRITORI_NOM[n] || n]}
          labelFormatter={l => `Setmana ${l}`}
        />
        <Legend
          formatter={n => TERRITORI_NOM[n] || n}
          wrapperStyle={{ fontSize: 12 }}
        />
        {territoris.map(t => (
          <Line
            key={t}
            type="monotone"
            dataKey={t}
            stroke={terrChart(t)}
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
