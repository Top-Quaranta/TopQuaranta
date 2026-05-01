/**
 * LastfmPanel — read-only display of Last.fm artist metadata.
 *
 * Mirrors the layout pattern of `MusicBrainzPanel`. All fields come
 * from `Artista.lastfm_*` populated by the daily
 * `obtenir_metadata_lastfm` cron — there is no on-demand "sync now"
 * button (the artist is touched at most once a week by design, and a
 * staff member who needs fresh data can run the management command
 * with `--artista-id`).
 *
 * Bio HTML is embedded raw via `dangerouslySetInnerHTML`. Last.fm
 * already strips dangerous tags on its end and the field is only
 * visible to staff, so the risk surface is minimal.
 */
import { Pill } from './StaffTable'

function Row({ label, value }) {
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
    return null
  }
  const rendered = Array.isArray(value) ? value.join(', ') : value
  return (
    <div className="flex gap-3 text-sm border-b border-tq-ink/5 py-1.5 last:border-0">
      <span className="w-36 text-[11px] uppercase tracking-wide text-tq-ink/75 shrink-0">
        {label}
      </span>
      <span className="min-w-0 break-words">{rendered}</span>
    </div>
  )
}

function formatSync(iso) {
  if (!iso) return 'mai sincronitzat'
  const d = new Date(iso)
  return d.toLocaleString('ca', { dateStyle: 'short', timeStyle: 'short' })
}

function formatNum(n) {
  if (n == null) return null
  return Number(n).toLocaleString('ca')
}

export default function LastfmPanel({ data }) {
  const hasAnything =
    data?.url || data?.bio_summary || data?.listeners != null || data?.image_large

  return (
    <div className="bg-white text-tq-ink rounded-lg border border-black/5 p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="font-semibold text-sm">Last.fm</h2>
        {data?.url && (
          <a
            href={data.url}
            target="_blank"
            rel="noopener"
            className="text-[11px] underline text-tq-ink/70 hover:text-tq-ink"
          >
            obrir a Last.fm ↗
          </a>
        )}
      </div>

      {data?.auto_match_disabled && (
        <p
          className="text-xs italic mb-2 p-2 rounded"
          style={{ background: 'rgba(239, 68, 68, 0.10)', color: 'var(--color-tq-danger)' }}
        >
          Auto-sync Last.fm <strong>desactivat</strong> per a aquest artista
          (col·lisió de nom amb un homònim). El cron mai el tocarà fins
          que un membre de l'staff aixequi el lockout.
        </p>
      )}

      {!hasAnything && !data?.auto_match_disabled && (
        <p className="text-xs text-tq-ink/75 italic mb-2">
          Aquest artista encara no s'ha sincronitzat amb Last.fm. El cron
          (05:00 UTC) l'agafarà segons la cua de prioritat. Per forçar-ho
          ara, executa{' '}
          <code className="bg-tq-ink/5 px-1 rounded">
            ./manage.py obtenir_metadata_lastfm --artista-id {data?.pk || '<pk>'}
          </code>.
        </p>
      )}

      {data?.image_large && (
        <img
          src={data.image_extralarge || data.image_large}
          alt=""
          className="w-32 h-32 object-cover rounded-md float-right ml-3 mb-3"
        />
      )}

      <Row label="Listeners" value={formatNum(data?.listeners)} />
      <Row label="Playcount total" value={formatNum(data?.playcount_total)} />
      <Row
        label="En gira"
        value={
          data?.ontour === true
            ? <Pill tone="green">Sí</Pill>
            : data?.ontour === false
              ? <Pill tone="gray">No</Pill>
              : null
        }
      />
      <Row
        label="Tags"
        value={(data?.tags || []).slice(0, 8).map(t => t.name).filter(Boolean)}
      />
      <Row
        label="Similars (rep.)"
        value={data?.nb_similars > 0 ? data.nb_similars : null}
      />
      <Row label="Última sync" value={formatSync(data?.last_sync)} />

      {/* Aliases UI moved to ArtistaEditPage form (inline alongside
          the canonical lastfm_nom input) for parity with deezer_ids
          and territoris editing. This panel stays read-only. */}

      {data?.bio_summary && (
        <details className="mt-3 text-xs text-tq-ink/80">
          <summary className="cursor-pointer font-semibold text-tq-ink/75 uppercase tracking-wide text-[11px]">
            Bio (resum)
          </summary>
          <div
            className="mt-2 prose prose-sm max-w-none"
            dangerouslySetInnerHTML={{ __html: data.bio_summary }}
          />
          {data.bio_content && data.bio_content !== data.bio_summary && (
            <details className="mt-2">
              <summary className="cursor-pointer font-semibold text-tq-ink/75 text-[11px]">
                veure bio sencera
              </summary>
              <div
                className="mt-2 prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: data.bio_content }}
              />
            </details>
          )}
          {data.bio_published && (
            <p className="text-[10px] opacity-50 mt-2">
              Publicat: {new Date(data.bio_published).toLocaleDateString('ca')}
            </p>
          )}
        </details>
      )}
    </div>
  )
}
