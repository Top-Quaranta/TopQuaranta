/**
 * LocationCascade — territori → comarca → municipi picker.
 *
 * Shape of `value`:
 *   { territori, comarca, municipi_id, municipi_nom, manual }
 *
 * Special case: when `territori === 'ALT'`, the comarca and municipi
 * selects collapse into a single free-text input mapped to
 * `value.manual`. That mirrors the Municipi table — non-PPCC places
 * don't have curated data, so we fall back to an unvalidated string
 * which the approval/save endpoints persist as
 * `ArtistaLocalitat.localitat_manual`.
 *
 * Options come from the public localitzacio endpoints
 * (/api/v1/localitzacio/territoris, /comarques?territori=, /municipis?comarca=).
 * Each select lazy-loads on the previous choice to avoid over-fetching.
 */
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'

const ALT = 'ALT'

function useTerritoris() {
  const [ts, setTs] = useState([])
  useEffect(() => {
    api.get('/localitzacio/territoris/').then(setTs).catch(() => {})
  }, [])
  return ts
}

const selectClass =
  'text-sm px-2.5 py-1.5 rounded border border-tq-ink/20 bg-white text-tq-ink ' +
  'focus:outline-none focus:ring-2 focus:ring-tq-yellow disabled:opacity-50'

const inputClass =
  'text-sm px-2.5 py-1.5 rounded border border-tq-ink/20 bg-white text-tq-ink ' +
  'placeholder-tq-ink/40 focus:outline-none focus:ring-2 focus:ring-tq-yellow'

export default function LocationCascade({ value, onChange }) {
  const territoris = useTerritoris()
  const [comarques, setComarques] = useState([])
  const [municipis, setMunicipis] = useState([])

  const territori = value?.territori || ''
  const comarca = value?.comarca || ''
  const isAlt = territori === ALT

  useEffect(() => {
    if (!territori || isAlt) {
      setComarques([])
      return
    }
    api
      .get(`/localitzacio/comarques/?territori=${encodeURIComponent(territori)}`)
      .then(setComarques)
      .catch(() => setComarques([]))
  }, [territori, isAlt])

  useEffect(() => {
    if (!comarca || isAlt) {
      setMunicipis([])
      return
    }
    api
      .get(`/localitzacio/municipis/?comarca=${encodeURIComponent(comarca)}`)
      .then(setMunicipis)
      .catch(() => setMunicipis([]))
  }, [comarca, isAlt])

  // Keep municipi_nom in sync with municipi_id so the select shows the
  // right label after reload.
  function pickMunicipi(pk) {
    if (!pk) {
      onChange({ ...value, municipi_id: null, municipi_nom: '' })
      return
    }
    const m = municipis.find(x => String(x.pk) === String(pk))
    onChange({
      ...value,
      municipi_id: Number(pk),
      municipi_nom: m?.nom || '',
    })
  }

  return (
    <div className="flex flex-wrap gap-1">
      <select
        aria-label="Territori"
        value={territori}
        onChange={e => {
          const next = e.target.value
          // Reset downstream whenever territori changes.
          onChange({
            territori: next,
            comarca: '',
            municipi_id: null,
            municipi_nom: '',
            manual: next === ALT ? (value?.manual || '') : '',
          })
        }}
        className={selectClass}
      >
        <option value="">— Territori —</option>
        {territoris.map(t => (
          <option key={t.codi} value={t.codi}>
            {t.nom}
          </option>
        ))}
      </select>

      {isAlt ? (
        <input
          aria-label="Nom de la localitat"
          value={value?.manual || ''}
          onChange={e =>
            onChange({ ...value, manual: e.target.value })
          }
          placeholder="Nom de la localitat"
          className={inputClass + ' min-w-[220px]'}
        />
      ) : (
        <>
          <select
            aria-label="Comarca"
            value={comarca}
            onChange={e =>
              onChange({
                ...value,
                comarca: e.target.value,
                municipi_id: null,
                municipi_nom: '',
              })
            }
            disabled={!territori}
            className={selectClass}
          >
            <option value="">— Comarca —</option>
            {comarques.map(c => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            aria-label="Municipi"
            value={value?.municipi_id ?? ''}
            onChange={e => pickMunicipi(e.target.value)}
            disabled={!comarca}
            className={selectClass}
          >
            <option value="">— Municipi —</option>
            {municipis.map(m => (
              <option key={m.pk} value={m.pk}>
                {m.nom}
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  )
}
