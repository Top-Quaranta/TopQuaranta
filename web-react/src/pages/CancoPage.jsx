/**
 * CancoPage — public song profile with the full ranking history.
 *
 * Reads /api/v1/cancons/<pk>/ and renders:
 *   - Header: cover + title + artist + album link
 *   - Chart: per-territory ranking evolution (recharts LineChart,
 *     Y axis inverted since position 1 is the top)
 *   - Optional provisional-ranking callout
 *
 * The chart lines colour-match territory colors defined in HomePage
 * to keep the brand language consistent.
 */
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis, Legend,
} from 'recharts'
import { api } from '../lib/api'
import Alert from '../components/ui/Alert'
import { albumUrl } from '../lib/urls'
import { useFeedbackTarget } from '../context/FeedbackContext'
import ExternalListenLinks from '../components/ExternalListenLinks'
import TopBreakdownPanel from '../components/TopBreakdownPanel'
import { SeoHead } from '../lib/seoHead'

const TERRITORI_COLORS = {
  PPCC: '#427c42', CAT: '#c99b0c', VAL: '#cf3339', BAL: '#0047ba',
  AND:  '#7c3aed', CNO: '#0891b2', FRA: '#ea580c', ALG: '#db2777',
  ALT:  '#6b7280',
}
const TERRITORI_NOM = {
  CAT: 'Catalunya', VAL: 'País Valencià', BAL: 'Illes Balears',
  PPCC: 'General',  ALT: 'Altres',        AND: 'Andorra',
  CNO: 'Catalunya del Nord', FRA: 'Franja de Ponent',
  ALG: "L'Alguer",  CAR: 'Carxe',
}

function formatDuration(ms) {
  if (!ms) return '—'
  const totalSeconds = Math.floor(ms / 1000)
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function CancoPage() {
  // React Router hands us whichever params the matched route had:
  //   /canco/:slug                                      → slug
  //   /artista/:artistaSlug/:albumSlug/:cancoSlug       → cancoSlug
  // The leaf slug is the authoritative lookup in either case.
  const params = useParams()
  const slug = params.cancoSlug || params.slug
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.get(`/cancons/${slug}/`)
      .then(setData)
      .catch(e => setError(e.status === 404 ? 'Cançó no trobada.' : (e.message || 'Error')))
      .finally(() => setLoading(false))
  }, [slug])

  useFeedbackTarget(
    data
      ? { targetType: 'canco', targetPk: data.pk, targetSlug: data.slug, targetLabel: data.nom }
      : null,
  )

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div className="h-60 bg-white/5 rounded-lg animate-pulse" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto">
        <Alert tone="danger">{error}</Alert>
      </div>
    )
  }

  if (!data) return null

  return (
    <article className="max-w-4xl mx-auto text-white space-y-6">
      <SeoHead entity="canco" slug={slug} />
      {/* Header */}
      <header className="bg-white text-tq-ink rounded-lg p-6 shadow-md flex flex-col sm:flex-row gap-6">
        {data.album?.imatge_url ? (
          <img
            src={data.album.imatge_url}
            alt=""
            className="w-full sm:w-48 h-48 object-cover rounded-md shrink-0"
          />
        ) : (
          <div className="w-full sm:w-48 h-48 bg-gray-100 rounded-md shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-wider text-gray-500">Cançó</p>
          <h1 className="text-3xl font-bold font-display mt-1">{data.nom}</h1>
          {data.artista && (
            <p className="mt-2 text-lg">
              <Link
                to={`/artista/${data.artista.slug}`}
                className="hover:text-tq-yellow-deep"
              >
                {data.artista.nom}
              </Link>
              {data.artistes_col?.length > 0 && (
                <span className="text-gray-500 text-sm">
                  {' '}amb{' '}
                  {data.artistes_col.map((col, j) => (
                    <span key={col.slug}>
                      {j > 0 ? ', ' : ''}
                      <Link to={`/artista/${col.slug}`} className="underline">
                        {col.nom}
                      </Link>
                    </span>
                  ))}
                </span>
              )}
            </p>
          )}
          {data.album && (
            <p className="text-sm text-gray-500 mt-1">
              Àlbum: <Link to={albumUrl({ albumSlug: data.album.slug, artistaSlug: data.artista?.slug })} className="underline">{data.album.nom}</Link>
            </p>
          )}
          <p className="text-xs text-gray-500 mt-2 space-x-3">
            <span>{formatDuration(data.durada_ms)}</span>
            {data.isrc && <span>ISRC: {data.isrc}</span>}
            {data.data_llancament && <span>Publicada: {data.data_llancament}</span>}
          </p>
          <ExternalListenLinks
            className="mt-4"
            kind="canco"
            title={data.nom}
            artist={data.artista?.nom}
            deezerId={data.deezer_id}
            isrc={data.isrc}
          />
        </div>
      </header>

      {/* Algorithm transparency panel — discreet, collapsed by default.
          Returns null when there's nothing to show (anon viewer of a
          song that isn't in the current top). */}
      <TopBreakdownPanel slug={data.slug} />

      {/* Ranking chart */}
      {data.historial?.length > 0 && (
        <section className="bg-white text-tq-ink rounded-lg p-6 shadow-md">
          <h2 className="text-xl font-bold font-display mb-1">Evolució al top</h2>
          <p className="text-xs text-gray-500 mb-4">
            Posició setmanal — més baix és millor (1 = top)
          </p>
          <div className="w-full h-72">
            <ResponsiveContainer>
              <LineChart data={data.historial} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
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
                {data.territoris_historial.map(t => (
                  <Line
                    key={t}
                    type="monotone"
                    dataKey={t}
                    stroke={TERRITORI_COLORS[t] || '#6b7280'}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {/* Provisional callout */}
      {data.provisional?.length > 0 && (
        <section className="bg-tq-yellow-soft text-tq-ink rounded-lg p-4 text-sm">
          <p className="font-semibold mb-1">Actualment al provisional:</p>
          <ul className="flex flex-wrap gap-2">
            {data.provisional.map(p => (
              <li key={p.territori} className="px-2 py-0.5 bg-white rounded-sm">
                #{p.posicio} a {TERRITORI_NOM[p.territori] || p.territori}
              </li>
            ))}
          </ul>
        </section>
      )}

      {!data.historial?.length && !data.provisional?.length && (
        <p className="text-tq-ink-muted text-sm">
          Aquesta cançó encara no ha aparegut a cap top.
        </p>
      )}
    </article>
  )
}
