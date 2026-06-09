/**
 * StaffSocialPublicacionsPage — /staff/social/publicacions
 *
 * The unified publications audit + lifecycle surface (distribution
 * views, llesca 2). House-style PageHeader + search + FilterPanel
 * (canal / estat / tipus / setmana + sort) over the shared
 * PublicacionsTable. Filters live in the URL so a view is a shareable
 * deep link.
 *
 * Not to be confused with /staff/publicacions (community posts).
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Field, Input, PageHeader, Select } from '../../../components/staff/StaffTable'
import FilterPanel from '../../../components/staff/FilterPanel'
import PublicacionsTable from './PublicacionsTable'
import MetricsStrip from './MetricsStrip'

const DEFAULTS = {
  canal: '',
  estat: '',
  tipus: '',
  setmana: '',
  sort: '-data',
}

const CANALS = [
  ['', 'Tots els canals'],
  ['instagram', 'Instagram'],
  ['mastodon', 'Mastodon'],
  ['bluesky', 'Bluesky'],
  ['telegram', 'Telegram'],
  ['newsletter', 'Newsletter'],
]
const ESTATS = [
  ['', 'Tots els estats'],
  ['publicat', 'Publicat'],
  ['pendent', 'Pendent'],
  ['error', 'Error'],
  ['omes', 'Omès'],
]
const TIPUS = [
  ['', 'Tots els tipus'],
  ['top_ppcc', 'Top global'],
  ['top_territorial', 'Top territorial'],
  ['nous_albums', 'Nous àlbums'],
  ['nous_singles', 'Nous singles'],
]

export default function StaffSocialPublicacionsPage() {
  const [urlParams, setUrlParams] = useSearchParams()
  const [q, setQ] = useState(urlParams.get('q') || '')
  const [applied, setApplied] = useState({
    canal: urlParams.get('canal') ?? DEFAULTS.canal,
    estat: urlParams.get('estat') ?? DEFAULTS.estat,
    tipus: urlParams.get('tipus') ?? DEFAULTS.tipus,
    setmana: urlParams.get('setmana') ?? DEFAULTS.setmana,
    sort: urlParams.get('sort') ?? DEFAULTS.sort,
  })

  // Keep the URL in sync so the view is a shareable deep link.
  function syncUrl(next, nextQ) {
    const p = new URLSearchParams()
    Object.entries(next).forEach(([k, v]) => {
      if (v && v !== DEFAULTS[k]) p.set(k, v)
    })
    if (nextQ) p.set('q', nextQ)
    setUrlParams(p, { replace: true })
  }

  // PublicacionsTable keys its fetch off a JSON.stringify of these, so
  // a fresh object identity per render is harmless (no manual memo).
  const params = { ...applied, q }

  return (
    <section>
      <PageHeader
        title="Publicacions"
        subtitle="Totes les publicacions socials — auditoria i cicle de vida per canal."
      />

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Input
          placeholder="Cerca canal, tipus o territori…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            syncUrl(applied, e.target.value)
          }}
          className="flex-1 min-w-[14rem]"
        />
        <FilterPanel
          applied={applied}
          defaults={DEFAULTS}
          onApply={(next) => {
            setApplied(next)
            syncUrl(next, q)
          }}
        >
          {(p, setP) => (
            <>
              <Field label="Canal">
                <Select
                  aria-label="Canal"
                  value={p.canal}
                  onChange={(e) => setP({ canal: e.target.value })}
                >
                  {CANALS.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Estat">
                <Select
                  aria-label="Estat"
                  value={p.estat}
                  onChange={(e) => setP({ estat: e.target.value })}
                >
                  {ESTATS.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Tipus">
                <Select
                  aria-label="Tipus"
                  value={p.tipus}
                  onChange={(e) => setP({ tipus: e.target.value })}
                >
                  {TIPUS.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Setmana (dilluns ISO)">
                <Input
                  type="date"
                  aria-label="Setmana"
                  value={p.setmana}
                  onChange={(e) => setP({ setmana: e.target.value })}
                />
              </Field>
              <Field label="Ordenació">
                <Select
                  aria-label="Ordenació"
                  value={p.sort}
                  onChange={(e) => setP({ sort: e.target.value })}
                >
                  <option value="-data">Data ↓ (activitat recent)</option>
                  <option value="data">Data ↑</option>
                  <option value="-setmana">Setmana ↓</option>
                  <option value="setmana">Setmana ↑</option>
                  <option value="canal">Canal A-Z</option>
                  <option value="estat">Estat A-Z</option>
                </Select>
              </Field>
            </>
          )}
        </FilterPanel>
      </div>

      <MetricsStrip />

      <PublicacionsTable params={params} />
    </section>
  )
}
