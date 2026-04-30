/**
 * MusicBrainzPanel — reusable MB metadata block for Artista / Album / Canco
 * staff edit pages.
 *
 * Props:
 *   - kind: "artista" | "album" | "canco"
 *   - data: object with the relevant MB fields (see usage in each page).
 *   - onSync: optional callback for the "Sincronitzar ara" button.
 *     Only useful on artist pages since sync happens per-artist.
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

export default function MusicBrainzPanel({ kind, data, onSync, onClear, busy }) {
  const hasId =
    (kind === 'artista' && data?.id) ||
    (kind === 'album' && data?.mb_release_group_id) ||
    (kind === 'canco' && data?.mb_recording_id)

  const title =
    kind === 'artista'
      ? 'MusicBrainz (artista)'
      : kind === 'album'
      ? 'MusicBrainz (àlbum)'
      : 'MusicBrainz (cançó)'

  const mbUrl = (() => {
    if (kind === 'artista' && data?.id) return `https://musicbrainz.org/artist/${data.id}`
    if (kind === 'album' && data?.mb_release_group_id)
      return `https://musicbrainz.org/release-group/${data.mb_release_group_id}`
    if (kind === 'canco' && data?.mb_recording_id)
      return `https://musicbrainz.org/recording/${data.mb_recording_id}`
    return null
  })()

  return (
    <div className="bg-white text-tq-ink rounded-lg border border-black/5 p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="font-semibold text-sm">{title}</h2>
        <div className="flex items-center gap-2">
          {mbUrl && (
            <a
              href={mbUrl}
              target="_blank"
              rel="noopener"
              className="text-[11px] underline text-tq-ink/70 hover:text-tq-ink"
            >
              obrir a MB ↗
            </a>
          )}
          {kind === 'artista' && onSync && (
            <button
              type="button"
              onClick={onSync}
              disabled={busy || !data?.id}
              title={
                !data?.id
                  ? "Cal desar primer un MBID al camp de l'esquerra"
                  : "Baixa dades de MB i reconcilia àlbums/cançons"
              }
              className="text-[11px] font-semibold px-2.5 py-1 rounded bg-tq-ink text-tq-yellow hover:bg-tq-ink/90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Sincronitzar ara
            </button>
          )}
          {kind === 'artista' && onClear && data?.id && (
            <button
              type="button"
              onClick={onClear}
              disabled={busy}
              title="Desvincula l'MBID i, opcionalment, bloqueja'l perquè el cron no el reassigni"
              className="text-[11px] font-semibold px-2.5 py-1 rounded border border-tq-ink/30 text-tq-ink hover:bg-tq-ink/5 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Desvincular…
            </button>
          )}
        </div>
      </div>

      {!hasId && kind !== 'artista' && (
        <p className="text-xs text-tq-ink/75 italic">
          Aquest {kind === 'album' ? 'àlbum' : 'cançó'} encara no està relacionat amb
          cap entrada de MusicBrainz. Apareixerà quan el cron sincronitzi
          l'artista (o prem "Sincronitzar ara" a la pàgina de l'artista).
        </p>
      )}

      {kind === 'artista' && (
        <>
          {!hasId && (
            <p className="text-xs text-tq-ink/75 italic mb-2">
              Aquest artista encara no té MBID assignat.{' '}
              {data?.auto_match_disabled ? (
                <span>
                  L'auto-match està <strong>desactivat</strong> — el cron
                  no tornarà a proposar cap MBID. Per reactivar-lo, enganxa
                  un MBID vàlid al camp i desa.
                </span>
              ) : (
                <>
                  El cron l'intentarà resoldre pel nom, però si hi ha
                  homonímia (p.ex. Crim) cal posar-lo manualment. Cerca'l a{' '}
                  <a
                    href={`https://musicbrainz.org/search?query=${encodeURIComponent(data?.nom_hint || '')}&type=artist`}
                    target="_blank"
                    rel="noopener"
                    className="underline"
                  >
                    musicbrainz.org
                  </a>{' '}
                  i enganxa l'UUID al camp de l'editor.
                </>
              )}
            </p>
          )}
          {Array.isArray(data?.blocked_mbids) && data.blocked_mbids.length > 0 && (
            <div className="text-[11px] text-tq-ink/70 mb-2 flex flex-wrap gap-1 items-center">
              <span className="uppercase tracking-wide text-tq-ink/75">
                MBIDs bloquejats:
              </span>
              {data.blocked_mbids.map(id => (
                <a
                  key={id}
                  href={`https://musicbrainz.org/artist/${id}`}
                  target="_blank"
                  rel="noopener"
                  className="font-mono underline decoration-dotted hover:decoration-solid"
                  title="Prèviament rebutjat per staff — el cron no el reassignarà"
                >
                  {id.slice(0, 8)}…
                </a>
              ))}
            </div>
          )}
          <Row label="MBID" value={data?.id} />
          <Row label="Tipus" value={data?.type} />
          <Row label="Gènere (MB)" value={data?.gender} />
          <Row label="Àrea" value={data?.area} />
          <Row label="Disambiguation" value={data?.disambiguation} />
          <Row label="Sort name" value={data?.sort_name} />
          <Row label="Inici" value={data?.begin_date} />
          <Row
            label="Fi"
            value={
              data?.end_date ? (
                <span
                  className="font-semibold"
                  style={{ color: 'var(--color-tq-danger)' }}
                >{data.end_date}</span>
              ) : null
            }
          />
          <Row label="Àlies" value={data?.aliases} />
          <Row label="Tags" value={data?.tags} />
          <Row label="Valoració MB" value={data?.rating} />
          <Row label="ISRCs coneguts" value={data?.n_isrcs_known} />
          <Row label="Última sync" value={formatSync(data?.last_sync)} />
        </>
      )}

      {kind === 'album' && (
        <>
          <Row label="Release-group" value={data?.mb_release_group_id} />
          <Row label="Tipus secondari" value={data?.mb_type_secondary} />
          <Row label="Estat" value={data?.mb_status} />
          <Row
            label="Confirmat"
            value={
              data?.mbrainz_confirmed === true ? (
                <Pill tone="green">Confirmat</Pill>
              ) : data?.mbrainz_confirmed === false ? (
                <Pill tone="red">No confirmat</Pill>
              ) : (
                <span className="text-tq-ink/70">?</span>
              )
            }
          />
        </>
      )}

      {kind === 'canco' && (
        <>
          <Row label="Recording" value={data?.mb_recording_id} />
          <Row label="Work" value={data?.mb_work_id} />
          <Row
            label="Idioma (Work)"
            value={
              data?.mb_lyrics_language === 'cat' ? (
                <span
                  className="font-semibold"
                  style={{ color: 'var(--color-tq-success)' }}
                >
                  català ✓
                </span>
              ) : (
                data?.mb_lyrics_language || null
              )
            }
          />
          <Row
            label="Confirmat"
            value={
              data?.mbrainz_confirmed === true ? (
                <Pill tone="green">Confirmat</Pill>
              ) : data?.mbrainz_confirmed === false ? (
                <Pill tone="red">No confirmat</Pill>
              ) : (
                <span className="text-tq-ink/70">?</span>
              )
            }
          />
        </>
      )}
    </div>
  )
}
