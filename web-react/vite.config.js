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
