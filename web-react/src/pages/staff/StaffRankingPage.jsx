/**
 * StaffRankingPage — /staff/top
 *
 * Provisional ranking review, per territory. Bulk select + reject
 * (canco or artist). No pagination: always shows the full top-40.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import {
  Btn,
  EmptyState,
  PageHeader,
  Pill,
  Select,
  Table,
  TableCard,
  Td,
  Th,
  THead,
  Tr,
} from '../../components/rd/surface'

function fmtFactor(v) {
  if (v === null || v === undefined) return '—'
  // Factors are in [0, 1]; show as percentage with 1 decimal.
  return `${(v * 100).toFixed(1)}%`
}

function fmtScore(v) {
  if (v === null || v === undefined) return '—'
  return Math.round(v).toLocaleString()
}

export default function StaffRankingPage() {
  const [territori, setTerritori] = useState('CAT')
  const [data, setData] = useState(null)
  const [sel, setSel] = useState(new Set())
  const [motiu, setMotiu] = useState('desvincular_artista')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  function load() {
    setData(null)
    api.get(`/staff/top/?territori=${territori}`).then(setData).catch(() => setData(null))
  }
  useEffect(load, [territori])

  function toggle(pk) {
    setSel(s => {
      const n = new Set(s)
      n.has(pk) ? n.delete(pk) : n.add(pk)
      return n
    })
  }

  async function act(action) {
    if (sel.size === 0) { setMsg('Cap entrada seleccionada.'); return }
    if (!confirm(`${action} ${sel.size} entrades amb motiu "${motiu}"?`)) return
    setBusy(true); setMsg('')
    try {
      const out = await api.post('/staff/top/accio/', {
        action,
        ids: [...sel],
        motiu,
      })
      setMsg(`Fet. ${out.n || out.n_cancons} cançons afectades.`)
      setSel(new Set())
      load()
    } catch (e) {
      setMsg(e.payload?.error || e.message)
    } finally { setBusy(false) }
  }

  return (
    <section>
      <PageHeader
        title="Top provisional"
        subtitle={data ? `${data.entries.length} entrades a ${territori}` : 'Carregant…'}
      />

      <div className="flex flex-wrap gap-2 mb-3">
        <Select aria-label="Territori" value={territori} onChange={e => setTerritori(e.target.value)}>
          {data?.territoris?.map(t => (
            <option key={t.codi} value={t.codi}>{t.codi} — {t.nom}</option>
          ))}
          {!data && <option value="CAT">CAT</option>}
        </Select>
      </div>

      {/* The "Escoltes" column shows RAW weekly plays; the score that
          ordered this list applies the adaptive outlier soft-cap when
          active (per /staff/configuracio), so a magnitude outlier can
          sit lower than its raw escoltes alone would suggest. */}
      <p className="text-xs opacity-60 mb-3">
        Escoltes = brutes (rolling 7 dies). El càlcul comprimeix els outliers
        amb el sostre suau per territori segons la{' '}
        <Link to="/staff/configuracio" className="underline">configuració</Link>.
      </p>

      {sel.size > 0 && (
        <div className="flex flex-wrap gap-2 mb-3 p-2 bg-tq-yellow/90 text-tq-ink rounded">
          <span className="text-sm font-semibold">{sel.size} seleccionades</span>
          <Select aria-label="Motiu" value={motiu} onChange={e => setMotiu(e.target.value)}>
            {/* MOTIUS_REBUIG arrives as [value, label] tuples. Unpack so
                the <option value> holds the key the backend accepts. */}
            {data?.motius?.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          <Btn tone="danger" onClick={() => act('rebutjar_canco')} disabled={busy}>Rebutjar cançons</Btn>
          <Btn tone="danger" onClick={() => act('rebutjar_artista')} disabled={busy}>Rebutjar artistes</Btn>
          <Btn tone="secondary" onClick={() => setSel(new Set())} disabled={busy}>Netejar</Btn>
        </div>
      )}

      {msg && <p className="text-sm text-white/80 mb-3">{msg}</p>}

      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th className="w-8"></Th>
              <Th>#</Th>
              <Th>Cançó</Th>
              <Th>Artista</Th>
              <Th>Escoltes 7d</Th>
              <Th title="Escoltes efectives després del sostre suau adaptatiu per territori (genoll = multiplicador × mediana del top). Igual a les brutes quan la fila no es comprimeix.">Escoltes ef.</Th>
              <Th title="Factor d'antiguitat: 1 - (dies/365)^2.5">Antiguitat</Th>
              <Th title="Penalització per setmanes anteriors al top (Σ coef/2^(N-1))">Top passat</Th>
              <Th title="(1-0.25)^cancons_album_abans · (1-0.2)^cancons_artista_abans">Monopoli</Th>
              <Th>Score</Th>
            </tr>
          </THead>
          <tbody>
            {data?.entries?.length === 0 && (
              <tr><td colSpan={10}><EmptyState>Cap entrada.</EmptyState></td></tr>
            )}
            {data?.entries?.map(e => (
              <Tr key={e.pk}>
                <Td><input type="checkbox" aria-label={`Selecciona ${e.canco_nom || `entrada ${e.pk}`}`} checked={sel.has(e.pk)} onChange={() => toggle(e.pk)} /></Td>
                <Td className="font-bold">{e.posicio}</Td>
                <Td>
                  {e.canco_pk ? (
                    <Link className="underline hover:text-tq-ink" to={`/staff/cancons/${e.canco_pk}`}>
                      {e.canco_nom}
                    </Link>
                  ) : e.canco_nom}
                </Td>
                <Td>
                  {e.artista_pk ? (
                    <Link className="underline hover:text-tq-ink" to={`/staff/artistes/${e.artista_pk}`}>
                      {e.artista_nom}
                    </Link>
                  ) : e.artista_nom}
                </Td>
                <Td className="text-xs">{e.escoltes_setmanals?.toLocaleString()}</Td>
                <Td className="text-xs">
                  {e.escoltes_efectives?.toLocaleString()}
                  {e.soft_cap_aplicat && (
                    <span
                      className="ml-1 text-tq-yellow"
                      title={`Sostre suau aplicat: ${e.escoltes_setmanals?.toLocaleString()} → ${e.escoltes_efectives?.toLocaleString()}`}
                    >↓</span>
                  )}
                </Td>
                <Td className="text-xs">{fmtFactor(e.age_factor)}</Td>
                <Td className="text-xs">{fmtFactor(e.past_top_factor)}</Td>
                <Td className="text-xs">{fmtFactor(e.monopoli_factor)}</Td>
                <Td className="text-xs font-semibold">{fmtScore(e.score_final)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </TableCard>
    </section>
  )
}
