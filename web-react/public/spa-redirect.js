// Companion to public/404.html SPA redirect workaround.
// 404.html encodes the original path+search into ?p= so a deep
// link served as static falls back to / and JS routes from there.
//
// Moved out of inline <script> into external file (May-2026 audit)
// so the CSP can drop `script-src 'unsafe-inline'`. `'self'` covers
// it now.
(function () {
  const p = new URLSearchParams(window.location.search).get('p')
  if (p) {
    window.history.replaceState(null, null, p + window.location.hash)
  }
})()
