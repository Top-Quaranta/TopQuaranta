import { Component } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import Layout from './components/Layout'
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
import GestioArtistaEditPage from './pages/GestioArtistaEditPage'
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
import StaffDashboardPage from './pages/staff/StaffDashboardPage'
import PendentsPage from './pages/staff/PendentsPage'
import StaffArtistesPage from './pages/staff/StaffArtistesPage'
import ArtistaCrearPage from './pages/staff/ArtistaCrearPage'
import ArtistaEditPage from './pages/staff/ArtistaEditPage'
import StaffCanconsPage from './pages/staff/StaffCanconsPage'
import CancoEditPage from './pages/staff/CancoEditPage'
import StaffAlbumsPage from './pages/staff/StaffAlbumsPage'
import AlbumEditPage from './pages/staff/AlbumEditPage'
import StaffRankingPage from './pages/staff/StaffRankingPage'
import PropostesPage from './pages/staff/PropostesPage'
import PropostaDetailPage from './pages/staff/PropostaDetailPage'
import SolicitudsPage from './pages/staff/SolicitudsPage'
import SenyalPage from './pages/staff/SenyalPage'
import HistorialPage from './pages/staff/HistorialPage'
import ConfiguracioPage from './pages/staff/ConfiguracioPage'
import AuditlogPage from './pages/staff/AuditlogPage'
import UsuarisPage from './pages/staff/UsuarisPage'
import UsuariDetailPage from './pages/staff/UsuariDetailPage'
import FeedbackPage from './pages/staff/FeedbackPage'
import EstatPage from './pages/staff/EstatPage'
import StaffPublicacionsPage from './pages/staff/StaffPublicacionsPage'

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

function AppContent() {
  return (
    <Layout>
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
        <Route path="/compte/artista/:pk/editar" element={<GestioArtistaEditPage />} />
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
        {/* Staff panel. All /staff/* routes sit under a shared
            StaffLayout (dark sidebar) and require `is_staff`. As we
            port each Django staff view we'll add a nested route. */}
        <Route
          path="/staff/*"
          element={
            <AdminRoute>
              <StaffLayout>
                <Routes>
                  <Route path="/" element={<StaffDashboardPage />} />
                  <Route path="/pendents" element={<PendentsPage />} />
                  <Route path="/artistes" element={<StaffArtistesPage />} />
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
                  <Route path="/senyal" element={<SenyalPage />} />
                  <Route path="/historial" element={<HistorialPage />} />
                  <Route path="/configuracio" element={<ConfiguracioPage />} />
                  <Route path="/auditlog" element={<AuditlogPage />} />
                  <Route path="/usuaris" element={<UsuarisPage />} />
                  <Route path="/usuaris/:pk" element={<UsuariDetailPage />} />
                  <Route path="/feedback" element={<FeedbackPage />} />
                  <Route path="/estat" element={<EstatPage />} />
                  <Route path="/publicacions" element={<StaffPublicacionsPage />} />
                </Routes>
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
