/**
 * StaffArtistesAlTopPage — /staff/artistes/al-top
 *
 * Read-only queue for the social-tagging workflow: artists in the latest
 * weekly PPCC (Global) top, with whether each has a reachable verified
 * manager email (the audience of the "has entrat al top" alert).
 *
 * Consumes the existing endpoint `/staff/artistes/?al_top=1` (adds
 * `te_gestor_email` to each row) + `include_n_top=1` for the Top count.
 * Mirrors StaffArtistesSenseInstagramPage's list pattern; no inline edit.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useEffect } from 'react'
import { api } from '../../lib/api'
import {
  Btn,
  EmptyState,
  PageHeader,
  Pagination,
  Pill,
  Table,
  TableCard,
  Td,
  Th,
  THead,
  Tr,
} from '../../components/rd/surface'

function AvisosPanel() {
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState('')
  const [err, setErr] = useState('')

  async function run(send) {
    if (send && !window.confirm(
      'Enviar de debò els avisos "has entrat al top" als gestors verificats? ' +
      'Aquesta acció envia emails reals.'
    )) {
      return
    }
    setBusy(true)
    setErr('')
    setOut('')
    try {
      const r = await api.post('/staff/avisos-top/enviar/', { send })
      setOut(r.stdout || '(sense sortida)')
    } catch (e) {
      setErr(e.message || 'Error')
      if (e.stdout) setOut(e.stdout)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mb-4 rounded-lg border border-white/10 p-3">
      <p className="text-sm font-semibold mb-2">Avisos "has entrat al top"</p>
      <div className="flex flex-wrap gap-2">
        <Btn onClick={() => run(false)} disabled={busy}>
          Previsualitza (dry-run)
        </Btn>
        <Btn onClick={() => run(true)} disabled={busy} tone="danger">
          Enviar avisos (real)
        </Btn>
      </div>
      {err && <p className="text-[11px] text-red-400 mt-2">{err}</p>}
      {out && (
        <pre className="mt-2 text-[11px] whitespace-pre-wrap text-white/70 bg-black/30 rounded p-2 max-h-48 overflow-auto">
          {out}
        </pre>
      )}
    </div>
  )
}

function Row({ a }) {
  const nTop = a.n_top || 0
  const hasEmail = !!a.te_gestor_email
  return (
    <Tr>
      <Td>
        <Link
          to={`/staff/artistes/${a.pk}`}
          className="font-semibold underline hover:text-tq-yellow"
        >
          {a.nom}
        </Link>
      </Td>
      <Td>
        {nTop > 0 ? (
          <Pill tone={nTop >= 3 ? 'yellow' : 'gray'}>{nTop}×</Pill>
        ) : (
          <span className="text-white/40">—</span>
        )}
      </Td>
      <Td>
        {hasEmail ? (
          <Pill tone="green">✓ gestor amb email</Pill>
        ) : (
          <Pill tone="gray">sense gestor verificat</Pill>
        )}
      </Td>
      <Td>
        {a.instagram_url ? (
          <a
            href={a.instagram_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-tq-yellow underline hover:text-tq-yellow-deep whitespace-nowrap"
          >
            Instagram ↗
          </a>
        ) : (
          <span className="text-white/40 text-xs">sense Instagram</span>
        )}
      </Td>
    </Tr>
  )
}

export default function StaffArtistesAlTopPage() {
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState(null)

  useEffect(() => {
    setData(null)
    const params = new URLSearchParams({
      al_top: '1',
      include_n_top: '1',
      include_gestor_email: '1',
      page: String(page),
    })
    api
      .get(`/staff/artistes/?${params}`)
      .then(setData)
      .catch(e => setError(e.message))
  }, [page])

  const total = data?.total
  const subtitle =
    total === undefined
      ? 'Carregant…'
      : `${total} artistes al top global d'aquesta setmana. "Gestor amb email" indica si rebrien l'avís d'entrada al top.`

  return (
    <section>
      <PageHeader title="Artistes al top" subtitle={subtitle} />
      <AvisosPanel />
      {error && <p className="text-sm text-red-300 mb-4">{error}</p>}
      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Artista</Th>
              <Th title="Cançons d'aquest artista que han aparegut al top (distinct TopSetmanal)">
                Top
              </Th>
              <Th>Avís per email</Th>
              <Th>Instagram</Th>
            </tr>
          </THead>
          <tbody>
            {data?.results?.length === 0 && (
              <tr>
                <td colSpan={4}>
                  <EmptyState>
                    Cap artista al top d'aquesta setmana encara.
                  </EmptyState>
                </td>
              </tr>
            )}
            {data?.results?.map(a => (
              <Row key={a.pk} a={a} />
            ))}
          </tbody>
        </Table>
        <Pagination meta={data} onPage={setPage} />
      </TableCard>
    </section>
  )
}
