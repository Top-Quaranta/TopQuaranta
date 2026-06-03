import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Sprint 4: React is the primary UI served from the site root. The
  // Django app still runs behind Caddy for `/api/*`, 2FA flows, email
  // activation and sitemap/robots. Everything else falls through to
  // the SPA index.
  base: '/',
  server: {
    // During dev (`npm run dev`), proxy API calls to the local Django
    // gunicorn so the React app talks to the real backend without CORS.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8083',
        changeOrigin: true,
      },
    },
  },
  ssr: {
    noExternal: ['mm-design'],
  },
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
  build: {
    // Sprint S Bloc D (CWV): split heavy deps out of the main bundle
    // so the homepage doesn't pay for recharts (only used in
    // /staff/analytics + the canço history chart). Brings the
    // anonymous bundle from ~1.05 MB to ~600 KB.
    rolldownOptions: {
      output: {
        // Rolldown takes a function, not the legacy object shape.
        // Returns the chunk name; null/undefined means "leave it
        // in the default chunk".
        manualChunks(id) {
          if (id.includes('node_modules')) {
            // React core in its OWN stable chunk, evaluated first. Every
            // page needs it, so it's always loaded. Pinning it here stops
            // the shared React runtime (scheduler/react-is) from being
            // co-located into a feature chunk: before this, one such
            // shared module landed inside the `recharts` chunk, so the
            // entry imported a symbol from it and the browser
            // modulepreloaded all of recharts (~112 KB gz) on EVERY
            // public page, even though only the lazy CancoChart uses it.
            // `react-router` / `react-helmet-async` keep their own rules
            // below (the trailing slash makes `react/`, `react-dom/`,
            // `react-is/`, `scheduler/` not match `react-router/` etc.).
            if (
              /node_modules\/(react|react-dom|react-is|scheduler)\//.test(id)
            ) {
              return 'react'
            }
            if (
              id.includes('recharts') ||
              /node_modules\/d3-/.test(id) ||
              id.includes('victory-vendor')
            ) {
              return 'recharts'
            }
            if (id.includes('react-router')) {
              return 'react-router'
            }
            if (id.includes('react-helmet-async')) {
              return 'helmet'
            }
          }
        },
      },
    },
  },
})
