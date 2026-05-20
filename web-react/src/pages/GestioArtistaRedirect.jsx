/**
 * GestioArtistaRedirect — /compte/artista/:pk/editar
 *
 * Backwards-compat shim for the legacy pk-based URL. Sprint Portal
 * Artista Ampliat (2026-05-20) moved the canonical surface to
 * `/compte/artista/<slug>/`. We resolve the slug client-side via the
 * dashboard endpoint (which already returns the gestor's UserArtista
 * list with slugs) and `navigate(..., {replace: true})` so the back
 * button still works.
 *
 * If the pk doesn't match any of the user's UserArtista rows, we
 * fall back to /compte (the dashboard) so the user lands somewhere
 * useful instead of a 404.
 */
import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'

export default function GestioArtistaRedirect() {
  const { pk } = useParams()
  const navigate = useNavigate()
  const { profile, loading: authLoading } = useAuth()
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (authLoading || !profile) return
    api
      .get('/compte/dashboard/')
      .then(d => {
        const ua = (d.gestio_list || []).find(
          row => String(row.artista?.pk) === String(pk)
        )
        const slug = ua?.artista?.slug
        if (slug) {
          navigate(`/compte/artista/${slug}/#editar`, { replace: true })
        } else {
          navigate('/compte', { replace: true })
        }
      })
      .catch(() => navigate('/compte', { replace: true }))
      .finally(() => setDone(true))
  }, [authLoading, profile, pk, navigate])

  if (authLoading) return null
  if (!profile)
    return (
      <Navigate
        to={`/compte/accedir?next=/compte/artista/${pk}/editar`}
        replace
      />
    )

  return done ? null : (
    <section className="max-w-3xl mx-auto py-10">
      <div className="h-8 bg-white/10 rounded w-1/2 animate-pulse" />
    </section>
  )
}
