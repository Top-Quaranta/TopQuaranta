import { Component, lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import Layout from './components/Layout'
import { trackPageview } from './lib/analytics'

// Public pages — eagerly imported because they're on the
// critical path for the anonymous bundle.
import HomePage from './pages/HomePage'
import TopPage from './pages/TopPage'
import ArtistesPage from './pages/ArtistesPage'
import ArtistaPage from './pages/ArtistaPage'
import AlbumPage from './pages/AlbumPage'
import CancoPage from './pages/CancoPage'
import MapaPage from './pages/MapaPage'
import AuthPage from './pages/AuthPage'
import AuthCallbackPage from './pages/AuthCallbackPage'
import ComptePage from './pages/ComptePage'
import ComptePerfilPage from './pages/ComptePerfilPage'
import ProposarArtistaPage from './pages/ProposarArtistaPage'
import SolicitarGestioPage from './pages/SolicitarGestioPage'
import GestioArtistaRedirect from './pages/GestioArtistaRedirect'
import ArtistaDashboardPage from './pages/ArtistaDashboardPage'
import ComFuncionaPage from './pages/ComFuncionaPage'
import { LegalIndex } from './pages/legal/LegalLayout'
import AvisLegalPage from './pages/legal/AvisLegalPage'
import PrivacitatPage from './pages/legal/PrivacitatPage'
import CookiesPage from './pages/legal/CookiesPage'
import TermesPage from './pages/legal/TermesPage'
import CodiConductaPage from './pages/legal/CodiConductaPage'
import LlicenciesPage from './pages/legal/LlicenciesPage'
import AccessibilitatPage from './pages/legal/AccessibilitatPage'
import SpotifyCallbackPage from './pages/SpotifyCallbackPage'
import OnboardingPage from './pages/OnboardingPage'
import PerfilUsuariPage from './pages/PerfilUsuariPage'
import MissatgesPage from './pages/MissatgesPage'
import ComunitatLayout from './components/ComunitatLayout'
import ComunitatPage from './pages/ComunitatPage'
import ComunitatPublicaPage from './pages/ComunitatPublicaPage'
import ComunitatDirectoriPage from './pages/ComunitatDirectoriPage'
import ComunitatPublicarPage from './pages/ComunitatPublicarPage'
import ComunitatDetailPage from './pages/ComunitatDetailPage'
import AdminRoute from './components/AdminRoute'
import StaffLayout from './components/StaffLayout'

// Staff pages — lazy-loaded so they don't bloat the anon bundle.
// Only ~5 staff users hit these endpoints; everyone else pays the
// cost of recharts (≈150 KB gz) and the rest of the staff surface.
// May-2026 audit: SPA was a single 1.2 MB chunk; this brings the
// initial public-facing chunk down meaningfully.
const StaffDashboardPage = lazy(() => import('./pages/staff/StaffDashboardPage'))
const PendentsPage = lazy(() => import('./pages/staff/PendentsPage'))
const StaffArtistesPage = lazy(() => import('./pages/staff/StaffArtistesPage'))
const StaffArtistesSenseInstagramPage = lazy(() => import('./pages/staff/StaffArtistesSenseInstagramPage'))
const StaffArtistesAlTopPage = lazy(() => import('./pages/staff/StaffArtistesAlTopPage'))
const ArtistaCrearPage = lazy(() => import('./pages/staff/ArtistaCrearPage'))
const ArtistaEditPage = lazy(() => import('./pages/staff/ArtistaEditPage'))
const StaffCanconsPage = lazy(() => import('./pages/staff/StaffCanconsPage'))
const CancoEditPage = lazy(() => import('./pages/staff/CancoEditPage'))
const StaffAlbumsPage = lazy(() => import('./pages/staff/StaffAlbumsPage'))
const AlbumEditPage = lazy(() => import('./pages/staff/AlbumEditPage'))
const StaffRankingPage = lazy(() => import('./pages/staff/StaffRankingPage'))
const PropostesPage = lazy(() => import('./pages/staff/PropostesPage'))
const PropostaDetailPage = lazy(() => import('./pages/staff/PropostaDetailPage'))
const SolicitudsPage = lazy(() => import('./pages/staff/SolicitudsPage'))
const StaffSollicitudsRevisioPage = lazy(() => import('./pages/staff/StaffSollicitudsRevisioPage'))
const StaffSollicitudRevisioDetailPage = lazy(() => import('./pages/staff/StaffSollicitudRevisioDetailPage'))
const SenyalPage = lazy(() => import('./pages/staff/SenyalPage'))
const HistorialPage = lazy(() => import('./pages/staff/HistorialPage'))
const ConfiguracioPage = lazy(() => import('./pages/staff/ConfiguracioPage'))
const AuditlogPage = lazy(() => import('./pages/staff/AuditlogPage'))
const UsuarisPage = lazy(() => import('./pages/staff/UsuarisPage'))
const UsuariDetailPage = lazy(() => import('./pages/staff/UsuariDetailPage'))
const FeedbackPage = lazy(() => import('./pages/staff/FeedbackPage'))
const StaffSocialPage = lazy(() => import('./pages/staff/StaffSocialPage'))
const NewsletterDraftPage = lazy(() => import('./pages/staff/NewsletterDraftPage'))
const StaffSocialSpotifyPage = lazy(() => import('./pages/staff/StaffSocialSpotifyPage'))
const ChannelView = lazy(() => import('./pages/staff/social/ChannelView'))
const StaffSocialPublicacionsPage = lazy(() =>
  import('./pages/staff/social/StaffSocialPublicacionsPage')
)
const EstatPage = lazy(() => import('./pages/staff/EstatPage'))
const StaffPublicacionsPage = lazy(() => import('./pages/staff/StaffPublicacionsPage'))
const StaffAnalyticsPage = lazy(() => import('./pages/staff/StaffAnalyticsPage'))

/** Top-level error boundary — catches unexpected render errors and
 *  shows a minimal fallback with a reload button. */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-screen gap-4 px-6 text-center">
          <p className="text-gray-300 text-sm">Alguna cosa ha fallat. Recarrega la pàgina.</p>
          <button
            className="text-sm font-semibold text-tq-yellow underline"
            onClick={() => window.location.reload()}
          >
            Recarregar
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

/**
 * RouteAnalytics — fires `trackPageview(pathname)` on every route
 * change. Mounted once inside the Router (so `useLocation` works) and
 * outside the route tree itself (so it doesn't re-mount per page).
 *
 * UTM landings ride along inside the same beacon — `analytics.js`
 * reads `window.location.search` per call, so the first navigation
 * carrying `?utm_source=…` records both pageview + utm_landing in
 * the same POST.
 */
function RouteAnalytics() {
  const location = useLocation()
  useEffect(() => {
    trackPageview(location.pathname)
  }, [location.pathname])
  return null
}

function AppContent() {
  return (
    <Layout>
      <RouteAnalytics />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/top" element={<TopPage />} />
        <Route path="/artistes" element={<ArtistesPage />} />
        <Route path="/artista/:slug" element={<ArtistaPage />} />
        {/* Canonical flat routes (short, stable). */}
        <Route path="/album/:slug" element={<AlbumPage />} />
        <Route path="/canco/:slug" element={<CancoPage />} />
        {/* Nested SEO routes. React Router picks the most specific
            match; both shapes end up rendering the same page, which
            fetches by the leaf slug alone. */}
        <Route path="/artista/:artistaSlug/:albumSlug/:cancoSlug" element={<CancoPage />} />
        <Route path="/artista/:artistaSlug/:albumSlug" element={<AlbumPage />} />
        <Route path="/mapa" element={<MapaPage />} />
        <Route path="/com-funciona" element={<ComFuncionaPage />} />
        {/* Sprint J — legal corpus. Each subpage is independently
            citable; /legal is the index. */}
        <Route path="/legal" element={<LegalIndex />} />
        <Route path="/legal/avis-legal" element={<AvisLegalPage />} />
        <Route path="/legal/privacitat" element={<PrivacitatPage />} />
        <Route path="/legal/cookies" element={<CookiesPage />} />
        <Route path="/legal/termes" element={<TermesPage />} />
        <Route path="/legal/codi-conducta" element={<CodiConductaPage />} />
        <Route path="/legal/llicencies" element={<LlicenciesPage />} />
        <Route path="/legal/accessibilitat" element={<AccessibilitatPage />} />
        {/* Legacy alias so /privacitat (linked from old footer) still works. */}
        <Route path="/privacitat" element={<Navigate to="/legal/privacitat" replace />} />
        <Route path="/compte/accedir" element={<AuthPage />} />
        <Route path="/compte/callback" element={<AuthCallbackPage />} />
        <Route path="/compte" element={<ComptePage />} />
        <Route path="/compte/perfil" element={<ComptePerfilPage />} />
        <Route path="/compte/artista/proposta" element={<ProposarArtistaPage />} />
        <Route path="/compte/artista/gestio" element={<SolicitarGestioPage />} />
        {/* Sprint Portal Artista Ampliat (2026-05-20): the slug-based
            dashboard is canonical. The pk-based legacy URL is kept as
            a client-side redirect so existing bookmarks still work. */}
        <Route path="/compte/artista/:slug/" element={<ArtistaDashboardPage />} />
        <Route path="/compte/artista/:slug" element={<ArtistaDashboardPage />} />
        <Route path="/compte/artista/:pk/editar" element={<GestioArtistaRedirect />} />
        {/* Perfil + missatges moved under /comunitat so they share the
            community sidebar. Old URLs kept as redirects. */}
        <Route path="/compte/perfil-usuari" element={<Navigate to="/comunitat/perfil" replace />} />
        <Route path="/compte/missatges" element={<Navigate to="/comunitat/missatges" replace />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        {/* Comunitat — nested under a shared dark-sidebar layout
            (mirroring Staff). Individual pages render only their own
            content; the sidebar nav lives in `ComunitatLayout`. */}
        <Route
          path="/comunitat/*"
          element={
            <ComunitatLayout>
              <Routes>
                <Route path="/" element={<ComunitatPage />} />
                <Route path="/perfil" element={<PerfilUsuariPage />} />
                <Route path="/missatges" element={<MissatgesPage />} />
                <Route path="/directori" element={<ComunitatDirectoriPage />} />
                <Route path="/publicar" element={<ComunitatPublicarPage />} />
                <Route path="/public" element={<ComunitatPublicaPage />} />
                <Route path="/:pk" element={<ComunitatDetailPage />} />
                <Route path="/:pk/editar" element={<ComunitatPublicarPage />} />
              </Routes>
            </ComunitatLayout>
          }
        />
        <Route path="/spotify/callback" element={<SpotifyCallbackPage />} />
        {/*
          Canonical Spotify OAuth callback route since the FASE B
          revival (2026-05-22). The legacy /spotify/callback is kept
          above for the SSH-based autoritzar_spotify fallback.
        */}
        <Route
          path="/staff/social/spotify/callback"
          element={<SpotifyCallbackPage />}
        />
        {/* Staff panel. All /staff/* routes sit under a shared
            StaffLayout (dark sidebar) and require `is_staff`. As we
            port each Django staff view we'll add a nested route. */}
        <Route
          path="/staff/*"
          element={
            <AdminRoute>
              <StaffLayout>
                <Suspense fallback={<div className="p-8 text-tq-yellow">Carregant…</div>}>
                <Routes>
                  <Route path="/" element={<StaffDashboardPage />} />
                  <Route path="/pendents" element={<PendentsPage />} />
                  <Route path="/artistes" element={<StaffArtistesPage />} />
                  <Route path="/artistes/sense-instagram" element={<StaffArtistesSenseInstagramPage />} />
                  <Route path="/artistes/al-top" element={<StaffArtistesAlTopPage />} />
                  <Route path="/artistes/crear" element={<ArtistaCrearPage />} />
                  <Route path="/artistes/:pk" element={<ArtistaEditPage />} />
                  <Route path="/cancons" element={<StaffCanconsPage />} />
                  <Route path="/cancons/:pk" element={<CancoEditPage />} />
                  <Route path="/albums" element={<StaffAlbumsPage />} />
                  <Route path="/albums/:pk" element={<AlbumEditPage />} />
                  <Route path="/top" element={<StaffRankingPage />} />
                  {/* Legacy alias — keeps any in-flight bookmark working. */}
                  <Route path="/ranking" element={<Navigate to="/staff/top" replace />} />
                  <Route path="/propostes" element={<PropostesPage />} />
                  <Route path="/propostes/:pk" element={<PropostaDetailPage />} />
                  <Route path="/solicituds" element={<SolicitudsPage />} />
                  <Route path="/sollicituds-revisio" element={<StaffSollicitudsRevisioPage />} />
                  <Route path="/sollicituds-revisio/:pk" element={<StaffSollicitudRevisioDetailPage />} />
                  <Route path="/senyal" element={<SenyalPage />} />
                  <Route path="/historial" element={<HistorialPage />} />
                  <Route path="/configuracio" element={<ConfiguracioPage />} />
                  <Route path="/auditlog" element={<AuditlogPage />} />
                  <Route path="/usuaris" element={<UsuarisPage />} />
                  <Route path="/usuaris/:pk" element={<UsuariDetailPage />} />
                  <Route path="/feedback" element={<FeedbackPage />} />
                  <Route path="/social" element={<StaffSocialPage />} />
                  <Route path="/social/esborrany" element={<NewsletterDraftPage />} />
                  <Route path="/social/spotify" element={<StaffSocialSpotifyPage />} />
                  <Route path="/social/instagram" element={<ChannelView canal="instagram" />} />
                  <Route path="/social/mastodon" element={<ChannelView canal="mastodon" />} />
                  <Route path="/social/bluesky" element={<ChannelView canal="bluesky" />} />
                  <Route path="/social/telegram" element={<ChannelView canal="telegram" />} />
                  <Route path="/social/newsletter" element={<ChannelView canal="newsletter" />} />
                  <Route path="/social/publicacions" element={<StaffSocialPublicacionsPage />} />
                  <Route path="/estat" element={<EstatPage />} />
                  <Route path="/publicacions" element={<StaffPublicacionsPage />} />
                  <Route path="/analytics" element={<StaffAnalyticsPage />} />
                </Routes>
                </Suspense>
              </StaffLayout>
            </AdminRoute>
          }
        />
      </Routes>
    </Layout>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      {/* `basename` is derived from Vite's BASE_URL (set in vite.config.js).
          Sprint 4 flipped this to `/` (was `/beta/` during 1-3). */}
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
