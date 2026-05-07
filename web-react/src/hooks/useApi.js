/**
 * useApi — single-source hook for the GET → loading/error/data dance.
 *
 * Replaces the 60+ inline `useEffect(() => { setLoading(true); api.get(...).then(setData)...` blocks
 * across `web-react/src/pages/`. Centralising it adds three things every
 * callsite needed but typically forgot:
 *
 *   1. Cancellation on unmount or path change. Without this, the second
 *      response of a fast nav (A → B) can clobber B's data with A's.
 *   2. `reload()` — many pages need to re-fetch after a mutation
 *      (delete, edit, etc.). Local components used to maintain a
 *      `version` state by hand to trigger this.
 *   3. Optional `mapError(err)` for status-based custom messages
 *      (e.g. "Àlbum no trobat" on 404 vs generic "Error" otherwise).
 *
 * Usage:
 *
 *   const { data, error, loading, reload } = useApi(`/albums/${slug}/`)
 *
 *   // With status-aware error:
 *   const { data, error } = useApi(`/albums/${slug}/`, {
 *     mapError: (e) => e.status === 404 ? 'Àlbum no trobat.' : null,
 *   })
 *
 *   // With explicit deps (when path itself doesn't change but inputs do):
 *   const { data } = useApi('/some/path/', { deps: [filterValue] })
 *
 *   // Skip fetch while path is null:
 *   const { data } = useApi(slug ? `/albums/${slug}/` : null)
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

export function useApi(path, opts = {}) {
  const { mapError, deps = [] } = opts
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  // Start `loading=true` only when we have a path to fetch — pages
  // with `useApi(null)` shouldn't show a spinner forever.
  const [loading, setLoading] = useState(Boolean(path))
  const [version, setVersion] = useState(0)
  // Keep the latest mapError in a ref so changing the function
  // identity doesn't retrigger the fetch (common pitfall when the
  // caller defines `mapError` inline).
  const mapErrorRef = useRef(mapError)
  mapErrorRef.current = mapError

  const reload = useCallback(() => setVersion((v) => v + 1), [])

  useEffect(() => {
    if (!path) {
      setData(null)
      setError(null)
      setLoading(false)
      return undefined
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .get(path)
      .then((d) => {
        if (!cancelled) setData(d)
      })
      .catch((e) => {
        if (cancelled) return
        const mapped = mapErrorRef.current ? mapErrorRef.current(e) : null
        setError(mapped || e.message || 'Error')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, version, ...deps])

  return { data, error, loading, reload, setData }
}

export default useApi
