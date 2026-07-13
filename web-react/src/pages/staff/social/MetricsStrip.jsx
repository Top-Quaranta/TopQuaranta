/**
 * MetricsStrip — per-platform engagement totals above the publications
 * table. Reads the additive `/staff/social/metrics-summary/` endpoint
 * (latest MetricaSocialPost snapshot of each post, summed per platform).
 * Read-only; silently renders nothing while loading, on error, or when
 * no post has a metric snapshot yet.
 */
import { useEffect, useState } from 'react'
import { api } from '../../../lib/api'
import { Pill } from '../../../components/rd/surface'

const PLATFORM_LABEL = {
  instagram_feed: 'IG feed',
  instagram_story: 'IG story',
  mastodon: 'Mastodon',
  bluesky: 'Bluesky',
  telegram: 'Telegram',
  newsletter: 'Newsletter',
  rss: 'RSS',
}

// The metrics worth a compact glance per platform. `clicks` is mostly a
// newsletter signal, so it rides along but stays last.
const METRICS = [
  ['reach', 'Abast'],
  ['impressions', 'Impr.'],
  ['likes', 'Likes'],
  ['replies', 'Resp.'],
  ['shares', 'Compart.'],
  ['clicks', 'Clics'],
]

function fmt(n) {
  return (n ?? 0).toLocaleString('ca-ES')
}

export default function MetricsStrip() {
  const [rows, setRows] = useState([])

  useEffect(() => {
    let alive = true
    api
      .get('/staff/social/metrics-summary/')
      .then((res) => {
        if (alive) setRows(res?.per_platform || [])
      })
      .catch(() => {
        if (alive) setRows([])
      })
    return () => {
      alive = false
    }
  }, [])

  if (!rows.length) return null

  return (
    <div className="mb-3" aria-label="Mètriques per plataforma">
      <div className="flex flex-wrap gap-2">
        {rows.map((r) => (
          <div
            key={r.platform}
            className="rounded-lg border border-tq-ink/10 bg-white px-3 py-2 text-tq-ink"
          >
            <div className="flex items-center gap-2 mb-1">
              <Pill tone="ink">{PLATFORM_LABEL[r.platform] || r.platform}</Pill>
              <span className="text-xs text-tq-ink/60">
                {r.n_posts} {r.n_posts === 1 ? 'publicació' : 'publicacions'}
              </span>
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
              {METRICS.map(([k, label]) => (
                <span key={k}>
                  <span className="text-tq-ink/60">{label} </span>
                  <span className="font-semibold tabular-nums">{fmt(r[k])}</span>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
