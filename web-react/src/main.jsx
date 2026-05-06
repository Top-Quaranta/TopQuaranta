import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HelmetProvider } from 'react-helmet-async'
import 'mm-design/tokens/colors.css'
import 'mm-design/tokens/typography.css'
import 'mm-design/tokens/spacing.css'
import './index.css'
import App from './App.jsx'

// HelmetProvider wraps the tree so any `<Helmet>` inside a route
// can rewrite the document <head>. Server-side this would be where
// you'd extract the rendered head; for the SPA we only care about
// the runtime side-effect on `document`.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <HelmetProvider>
      <App />
    </HelmetProvider>
  </StrictMode>,
)
