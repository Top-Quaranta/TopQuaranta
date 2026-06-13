/**
 * PublicacionsTable — the unified publications table (distribution
 * views, llesca 2).
 *
 * Self-fetching, house-style replacement for the dumped list that used
 * to live in the /staff/social monolith. Reused in two places:
 *   - the standalone page /staff/social/publicacions (with a filter bar
 *     + deep-link query params), and
 *   - the "Publicacions recents" slot of each channel view, scoped to
 *     that channel via `params={{ canal }}`.
 *
 * Columns: Data · Canal (Pill) · Objectiu (tipus+territori) · Setmana ·
 * Estat (Pill) · Enllaç (backend URL constructor) · Accions.
 *
 * Data comes from the paginated `social_list` (`/staff/social/`); the
 * lifecycle actions hit the existing action endpoints unchanged.
 */
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../../lib/api'
import {
  Btn,
  EmptyState,
  Pagination,
  Pill,
  Table,
  TableCard,
  Td,
  Th,
  THead,
  Tr,
} from '../../../components/staff/StaffTable'
import { COLUMNS } from './publicacionsColumns'

const PLATFORM_LABEL = {
  instagram_feed: 'IG feed',
  instagram_story: 'IG story',
  mastodon: 'Mastodon',
  bluesky: 'Bluesky',
  telegram: 'Telegram',
  newsletter: 'Newsletter',
}

const STATUS = {
  pendent: { tone: 'yellow', label: 'Pendent' },
  publicat: { tone: 'green', label: 'Publicat' },
  error: { tone: 'red', label: 'Error' },
  omes: { tone: 'gray', label: 'Omès' },
}

// Platforms whose Graph API can't delete published media on our surface
// (Instagram API with Instagram Login). The remote-delete button is hidden
// for these; deletion is manual in the app + "Reconciliar registre" locally.
const IS_IG = new Set(['instagram_feed', 'instagram_story'])

// Remote-delete labels — only for networks where the API delete works.
// (No IG entries: the button is not rendered for IG.)
const DELETE_LABEL = {
  mastodon: 'Esborrar Mastodon',
  bluesky: 'Esborrar Bluesky',
  telegram: 'Esborrar Telegram',
}

export default function PublicacionsTable({ params }) {
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [output, setOutput] = useState('')
  const [slidesByPk, setSlidesByPk] = useState({})

  // Stable key so filter changes reset to page 1 and refetch.
  const paramsKey = JSON.stringify(params || {})

  const query = useMemo(() => {
    const p = new URLSearchParams()
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v) p.set(k, v)
    })
    p.set('page', page)
    return p.toString()
  }, [paramsKey, page])

  useEffect(() => {
    setPage(1)
  }, [paramsKey])

  function reload() {
    return api
      .get(`/staff/social/?${query}`)
      .then(setData)
      .catch(() => setData(null))
  }
  useEffect(() => {
    reload()
  }, [query])

  // ── actions (existing endpoints, unchanged) ─────────────────────
  async function preview(post) {
    setBusy(true)
    setOutput('▶ Executant preview… (genera els PNGs però no publica)')
    try {
      const res = await api.post('/staff/social/preview/', {
        data: post.setmana,
        tipus: post.tipus,
        platform: post.platform,
      })
      const lines = []
      if (res.args) lines.push(`$ manage.py ${res.args.join(' ')}`)
      lines.push(res.output || '(sense sortida)')
      if (res.error) lines.push(`\n⚠ ${res.error}`)
      setOutput(lines.join('\n'))
    } catch (e) {
      setOutput(`✖ Error: ${e.payload?.error || e.message || e}\n\n${e.payload?.output || ''}`)
    } finally {
      setBusy(false)
    }
  }

  async function loadSlides(post) {
    setBusy(true)
    try {
      const p = new URLSearchParams({
        tipus: post.tipus,
        territori: post.territori || 'general',
        setmana: post.setmana,
        platform: post.platform,
      })
      const res = await api.get(`/staff/social/slides/?${p}`)
      setSlidesByPk((prev) => ({ ...prev, [post.pk]: res }))
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function publicarAra(post) {
    if (
      !confirm(
        `Publicar ara: ${post.platform} · ${post.tipus} · ${post.territori_label || '—'} · setmana del ${post.publication_date}?`
      )
    )
      return
    setBusy(true)
    setOutput("▶ Publicant… (això sí truca l'API si hi ha credencials vàlides)")
    try {
      const res = await api.post('/staff/social/publicar-ara/', {
        data: post.setmana,
        tipus: post.tipus,
        platform: post.platform,
      })
      const lines = []
      if (res.args) lines.push(`$ manage.py ${res.args.join(' ')}`)
      lines.push(res.output || '(sense sortida)')
      if (res.error) lines.push(`\n⚠ ${res.error}`)
      setOutput(lines.join('\n'))
      await reload()
    } catch (e) {
      setOutput(`✖ Error: ${e.payload?.error || e.message || e}\n\n${e.payload?.output || ''}`)
    } finally {
      setBusy(false)
    }
  }

  async function resetPost(post) {
    if (
      !confirm(
        `Reconciliar registre: ${post.platform} · ${post.tipus} · ${post.territori_label || '—'}?\n\n` +
          `Marca aquesta fila com a retirada al NOSTRE sistema (status → "pendent", ` +
          `esborra l'id remota local). NO toca la publicació a la xarxa.\n\n` +
          `Per a Instagram, que no permet esborrar per API: esborra el post a mà a ` +
          `l'app i fes servir això per reconciliar el nostre registre. Confirmes?`
      )
    )
      return
    setBusy(true)
    setOutput('▶ Reconciliant registre…')
    try {
      const res = await api.post('/staff/social/reset/', { pk: post.pk })
      setOutput(
        `✓ Registre reconciliat: status era ${res.previous?.status}, id remota era "${res.previous?.instagram_media_id || '(buit)'}"`
      )
      await reload()
    } catch (e) {
      setOutput(`✖ Error: ${e.payload?.error || e.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function eliminarRemot(post) {
    if (!post.instagram_media_id) {
      alert("Aquest post no té id remota (mai s'ha publicat o ja s'ha resetejat).")
      return
    }
    const platLabel = post.platform.replace('instagram_', 'IG ')
    if (
      !confirm(
        `ESBORRAR DE ${platLabel.toUpperCase()}: ${post.tipus} · ${post.territori_label || '—'}\n\n` +
          `Això elimina la publicació remota i deixa la fila llesta per re-publicar. ` +
          `És DESTRUCTIU. Confirmes?`
      )
    )
      return
    setBusy(true)
    setOutput(`▶ Esborrant publicació de ${platLabel}…`)
    try {
      const res = await api.post('/staff/social/eliminar-remot/', { pk: post.pk })
      setOutput(`${res.ok ? '✓' : '✖'} ${res.msg || ''}`)
      await reload()
    } catch (e) {
      setOutput(`✖ Error: ${e.payload?.error || e.message}\n\n${e.payload?.msg || ''}`)
    } finally {
      setBusy(false)
    }
  }

  async function republicar(post) {
    const platLabel = post.platform.replace('instagram_', 'IG ')
    if (
      !confirm(
        `RE-PUBLICAR ${platLabel.toUpperCase()}: ${post.tipus} · ${post.territori_label || '—'}\n\n` +
          `Esborra la publicació remota actual i en publica una de nova amb el contingut ` +
          `actualitzat. És DESTRUCTIU.\n\nConfirmes?`
      )
    )
      return
    setBusy(true)
    setOutput(`▶ Re-publicant ${platLabel}: esborrant remot + re-publicant…`)
    try {
      const res = await api.post('/staff/social/republicar/', { pk: post.pk })
      const lines = [`✓ ${res.delete_msg || 'remot esborrat'}`]
      if (res.args) lines.push(`$ manage.py ${res.args.join(' ')}`)
      lines.push(res.publish_output || '(sense sortida)')
      setOutput(lines.join('\n'))
      await reload()
    } catch (e) {
      const stepMsg = e.payload?.step ? ` (fallat al pas: ${e.payload.step})` : ''
      setOutput(`✖ Error${stepMsg}: ${e.payload?.msg || e.payload?.error || e.message}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <TableCard>
        <Table>
          <THead>
            <Tr>
              {COLUMNS.map((c) => (
                <Th key={c}>{c}</Th>
              ))}
            </Tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length}>
                  <EmptyState>Cap publicació amb aquests filtres.</EmptyState>
                </td>
              </tr>
            )}
            {data?.results?.flatMap((p) => {
              const s = STATUS[p.status] || { tone: 'gray', label: p.status }
              return [
                <Tr key={p.pk}>
                  <Td className="whitespace-nowrap font-mono text-xs">
                    {p.published_at ? (
                      p.published_at.slice(0, 16).replace('T', ' ')
                    ) : (
                      <span
                        className="text-tq-ink/50 italic"
                        title={`Creat: ${p.created_at?.slice(0, 16).replace('T', ' ')}`}
                      >
                        {p.created_at?.slice(0, 10) || '—'}
                      </span>
                    )}
                  </Td>
                  <Td>
                    <Pill tone="ink">{PLATFORM_LABEL[p.platform] || p.platform}</Pill>
                  </Td>
                  <Td className="text-xs">
                    {p.tipus}
                    {p.territori_label && p.territori_label !== '—' && (
                      <span className="text-tq-ink/60"> · {p.territori_label}</span>
                    )}
                  </Td>
                  <Td
                    className="whitespace-nowrap"
                    title={`Publicació prevista: ${p.publication_date}`}
                  >
                    Setmana {p.project_week}
                  </Td>
                  <Td>
                    <Pill tone={s.tone}>{s.label}</Pill>
                    {p.error_msg && (
                      <p
                        className="text-[10px] text-tq-danger-deep mt-1 max-w-[18rem] break-words"
                        title={p.error_msg}
                      >
                        {p.error_msg.length > 80
                          ? p.error_msg.slice(0, 80) + '…'
                          : p.error_msg}
                      </p>
                    )}
                  </Td>
                  <Td>
                    {p.url ? (
                      <a
                        href={p.url}
                        target="_blank"
                        rel="noopener"
                        className="text-xs underline text-tq-ink/70 hover:text-tq-ink whitespace-nowrap"
                        title={p.url}
                      >
                        Obrir ↗
                      </a>
                    ) : (
                      <span className="text-tq-ink/40 text-xs">—</span>
                    )}
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      <Btn tone="secondary" disabled={busy} onClick={() => preview(p)}>
                        Preview
                      </Btn>
                      <Btn tone="secondary" disabled={busy} onClick={() => loadSlides(p)}>
                        Veure slides
                      </Btn>
                      <Btn disabled={busy} onClick={() => publicarAra(p)}>
                        Publicar
                      </Btn>
                      <Btn tone="secondary" disabled={busy} onClick={() => resetPost(p)}>
                        Reconciliar registre
                      </Btn>
                      {/* Re-publicar and remote-delete both first delete the
                          previous media. Our Instagram surface (Instagram API
                          with Instagram Login) can't delete published media via
                          the API, so neither can keep its promise — both hidden
                          for IG. They stay for Mastodon/Bluesky/Telegram, where
                          the API delete works. For IG: delete by hand in the app,
                          then "Reconciliar registre" + "Publicar". */}
                      {p.instagram_media_id && !IS_IG.has(p.platform) && (
                        <>
                          <Btn disabled={busy} onClick={() => republicar(p)}>
                            Re-publicar
                          </Btn>
                          <Btn tone="danger" disabled={busy} onClick={() => eliminarRemot(p)}>
                            {DELETE_LABEL[p.platform] || `Esborrar ${p.platform}`}
                          </Btn>
                        </>
                      )}
                      {p.instagram_media_id && IS_IG.has(p.platform) && (
                        <span className="text-xs text-tq-ink/55 self-center">
                          Instagram no permet esborrar/re-publicar per API: fes-ho
                          a mà a l'app i després «Reconciliar registre» + «Publicar».
                        </span>
                      )}
                    </div>
                  </Td>
                </Tr>,
                slidesByPk[p.pk] ? (
                  <tr key={`${p.pk}-slides`}>
                    <td colSpan={COLUMNS.length} className="p-3 border-t border-tq-ink/10">
                      <SlidesGallery slides={slidesByPk[p.pk]} />
                    </td>
                  </tr>
                ) : null,
              ]
            })}
          </tbody>
        </Table>
        <Pagination meta={data} onPage={setPage} />
      </TableCard>

      {output && (
        <pre className="bg-tq-ink text-tq-yellow text-xs p-3 rounded overflow-x-auto whitespace-pre-wrap">
          {output}
        </pre>
      )}
    </div>
  )
}

function SlidesGallery({ slides }) {
  const both = (slides.feed?.length || 0) + (slides.stories?.length || 0)
  if (both === 0) {
    return (
      <p className="text-xs text-tq-ink/75 italic">
        Cap PNG renderitzat. Fes "Preview" primer per generar-los.
      </p>
    )
  }
  return (
    <div className="space-y-3">
      {slides.feed?.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/75 mb-1.5">
            Feed · {slides.feed.length} {slides.feed.length === 1 ? 'slide' : 'slides'}
          </p>
          <div className="flex flex-wrap gap-2">
            {slides.feed.map((s) => (
              <a key={s.name} href={s.url} target="_blank" rel="noopener" title={`${s.name} (${s.size_kb} kB)`}>
                <img
                  src={s.url}
                  alt={s.name}
                  className="w-32 h-40 object-cover rounded border border-tq-ink/20 hover:border-tq-ink"
                />
              </a>
            ))}
          </div>
        </div>
      )}
      {slides.stories?.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/75 mb-1.5">
            Stories · {slides.stories.length} {slides.stories.length === 1 ? 'story' : 'stories'}
          </p>
          <div className="flex flex-wrap gap-2">
            {slides.stories.map((s) => (
              <a key={s.name} href={s.url} target="_blank" rel="noopener" title={`${s.name} (${s.size_kb} kB)`}>
                <img
                  src={s.url}
                  alt={s.name}
                  className="w-24 h-44 object-cover rounded border border-tq-ink/20 hover:border-tq-ink"
                />
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
