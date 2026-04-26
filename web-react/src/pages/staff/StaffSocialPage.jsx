/**
 * StaffSocialPage — /staff/social
 *
 * Operations cockpit for the Instagram distribution. Shows:
 *  - The active phase + kill switch + token TTL.
 *  - The list of recent SocialPost rows with status badges.
 *  - A preview button per slot that triggers `publicar_social
 *    --dry-run` server-side and prints the captured stdout.
 *  - A "Publicar ara" button that re-publishes with --force.
 *
 * No fancy chrome — staff tool, not public-facing. Lists collapse
 * to scroll on mobile via the Table wrapper.
 */
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { Table, Select } from '../../components/staff/StaffTable'

const STATUS_TONE = {
  pendent:  'bg-yellow-100 text-yellow-900',
  publicat: 'bg-emerald-100 text-emerald-900',
  error:    'bg-red-100 text-red-900',
  omes:     'bg-gray-200 text-gray-800',
}

function StatusBadge({ status }) {
  return (
    <span className={
      'inline-block text-[10px] uppercase tracking-wide font-semibold px-2 py-0.5 rounded-full ' +
      (STATUS_TONE[status] || 'bg-gray-200 text-gray-800')
    }>
      {status}
    </span>
  )
}

export default function StaffSocialPage() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [output, setOutput] = useState('')

  const reload = () => api.get('/staff/social/').then(setData).catch(() => setData(null))
  useEffect(() => { reload() }, [])

  if (!data) return <p className="p-6">Carregant…</p>
  const { config, results } = data

  const tokenTone =
    config.token_days_left == null  ? 'bg-gray-200 text-gray-700' :
    config.token_days_left <  7      ? 'bg-red-100 text-red-900' :
    config.token_days_left <  21     ? 'bg-yellow-100 text-yellow-900' :
                                       'bg-emerald-100 text-emerald-900'

  async function toggle() {
    setBusy(true)
    try {
      await api.post('/staff/social/toggle/', { actiu: !config.instagram_actiu })
      await reload()
    } finally { setBusy(false) }
  }

  async function setFase(n) {
    if (!confirm(`Passar a fase ${n}?`)) return
    await api.post('/staff/social/fase/', { fase: n })
    await reload()
  }

  async function setStoryCap(n) {
    await api.post('/staff/social/story-cap/', { n })
    await reload()
  }

  async function preview(post) {
    setBusy(true); setOutput('')
    try {
      const res = await api.post('/staff/social/preview/', {
        data: post.setmana, tipus: post.tipus, platform: post.platform,
      })
      setOutput(res.output || '(sense sortida)')
    } catch (e) {
      setOutput(`Error: ${e.message || e}`)
    } finally { setBusy(false) }
  }

  async function publicarAra(post) {
    if (!confirm(`Publicar ara: ${post.platform} · ${post.tipus} · ${post.territori || '—'} · ${post.setmana}?`)) return
    setBusy(true); setOutput('')
    try {
      const res = await api.post('/staff/social/publicar-ara/', {
        data: post.setmana, tipus: post.tipus, platform: post.platform,
      })
      setOutput(res.output || '(sense sortida)')
      await reload()
    } catch (e) {
      setOutput(`Error: ${e.message || e}`)
    } finally { setBusy(false) }
  }

  return (
    <section className="p-4 md:p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold font-display">Distribució — Instagram</h1>
        <p className="text-sm text-tq-ink/60 mt-1">
          Control del calendari setmanal. Cada slot publica via Graph
          API. Mode <strong>{config.dry_run ? 'DRY-RUN' : 'PRODUCCIÓ'}</strong>
          {' '} (depèn de <code>INSTAGRAM_ACCESS_TOKEN</code>).
        </p>
      </header>

      {/* ── Config controls ───────────────────────────────────── */}
      <div className="grid sm:grid-cols-3 gap-3">
        <div className="p-3 border rounded-md">
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/60">Kill switch</p>
          <button
            type="button"
            onClick={toggle}
            disabled={busy}
            className={
              'mt-2 px-3 py-1.5 rounded-md text-sm font-semibold ' +
              (config.instagram_actiu
                ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                : 'bg-red-600 text-white hover:bg-red-700')
            }
          >
            {config.instagram_actiu ? 'ACTIU — clica per pausar' : 'PAUSAT — clica per activar'}
          </button>
        </div>

        <div className="p-3 border rounded-md">
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/60">Fase distribució</p>
          <div className="flex gap-1 mt-2">
            {[1, 2, 3, 4, 5].map(n => (
              <button
                key={n}
                type="button"
                disabled={busy}
                onClick={() => setFase(n)}
                className={
                  'px-3 py-1 rounded text-sm font-semibold ' +
                  (config.fase_distribucio === n
                    ? 'bg-tq-yellow text-tq-ink'
                    : 'bg-gray-100 text-tq-ink hover:bg-gray-200')
                }
              >
                {n}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-tq-ink/60 mt-1">
            1=dissabte · 2=+dimecres · 3=+dilluns · 4=+divendres · 5=+dimarts
          </p>
        </div>

        <div className="p-3 border rounded-md">
          <p className="text-[10px] uppercase tracking-widest text-tq-ink/60">Token Instagram</p>
          <span className={'inline-block mt-2 px-2 py-0.5 rounded text-xs font-semibold ' + tokenTone}>
            {config.token_days_left == null ? 'No configurat' :
             `${config.token_days_left} dies fins caducar`}
          </span>
        </div>
      </div>

      <div className="p-3 border rounded-md max-w-md">
        <p className="text-[10px] uppercase tracking-widest text-tq-ink/60 mb-1">
          Story cap PPCC (cançons)
        </p>
        <Select
          value={config.story_max_cancons_ppcc}
          onChange={e => setStoryCap(parseInt(e.target.value, 10))}
        >
          {[5, 10, 15, 20, 30, 40].map(n => <option key={n} value={n}>{n} stories</option>)}
        </Select>
        <p className="text-[10px] text-tq-ink/60 mt-1">
          Si la story completion rate cau per sota del 25 % al story #N,
          baixa aquí a N.
        </p>
      </div>

      {/* ── Captured stdout ──────────────────────────────────── */}
      {output && (
        <pre className="bg-tq-ink text-tq-yellow text-xs p-3 rounded overflow-x-auto whitespace-pre-wrap">{output}</pre>
      )}

      {/* ── Posts list ───────────────────────────────────────── */}
      <Table>
        <thead>
          <tr>
            <th className="text-left">Setmana</th>
            <th className="text-left">Plataforma</th>
            <th className="text-left">Tipus</th>
            <th className="text-left">Territori</th>
            <th className="text-left">Estat</th>
            <th className="text-left">Publicat</th>
            <th className="text-left">Accions</th>
          </tr>
        </thead>
        <tbody>
          {results.map(p => (
            <tr key={p.pk}>
              <td>{p.setmana}</td>
              <td className="text-xs">{p.platform.replace('instagram_', '')}</td>
              <td className="text-xs">{p.tipus}</td>
              <td>{p.territori || '—'}</td>
              <td><StatusBadge status={p.status} /></td>
              <td className="text-xs">{p.published_at ? p.published_at.slice(0, 16).replace('T', ' ') : '—'}</td>
              <td>
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => preview(p)}
                    disabled={busy}
                    className="text-xs px-2 py-1 rounded bg-gray-100 hover:bg-gray-200"
                  >
                    Preview
                  </button>
                  <button
                    type="button"
                    onClick={() => publicarAra(p)}
                    disabled={busy}
                    className="text-xs px-2 py-1 rounded bg-tq-ink text-tq-yellow font-semibold hover:bg-tq-ink/90"
                  >
                    Publicar
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>

      {results.length === 0 && (
        <p className="text-sm text-tq-ink/60 italic">
          Encara no hi ha cap publicació. Utilitza Preview per generar-ne en mode dry-run.
        </p>
      )}
    </section>
  )
}
