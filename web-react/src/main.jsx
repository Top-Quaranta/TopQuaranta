import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HelmetProvider } from 'react-helmet-async'
import 'mm-design/tokens/colors.css'
// NOTE: mm-design/tokens/typography.css is intentionally NOT imported.
// Its only effect here was an `@import` of Google Fonts (the `--mm-font-*`
// / `--mm-text-*` typography tokens it defines are unused in the SPA —
// we use Tailwind `tq-*` + the `--font-*` tokens in index.css). Fonts
// are now self-hosted via @font-face in index.css, so importing it would
// re-introduce the third-party Google Fonts call we removed.
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
