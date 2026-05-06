/**
 * SEO head sync — fetch per-page metadata from the Django source
 * of truth and inject it into the document <head> via
 * react-helmet-async.
 *
 * Both the SSR view (web/seo/views.py) and this hook read the same
 * `web/seo/meta.py::Meta` payload, exposed at
 * `/api/v1/seo/<entity>/<slug>/`. So the <head> a human sees in
 * Chrome is identical to what Googlebot saw via the SSR path.
 *
 * Fail-open: if the API call fails (offline, transient 500), the
 * SPA shell's default <title> stays — no broken pages.
 */
import { useEffect, useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { api } from './api'

/**
 * Resolve the canonical Meta dict for a given entity and inject it.
 *
 * Usage:
 *   <SeoHead entity="artista" slug={artista.slug} />
 *   <SeoHead entity="homepage" />
 *   <SeoHead entity="top" extraQuery={`?territori=${territori}`} />
 *
 * @param {string} entity   - one of "homepage", "top", "artistes",
 *                            "mapa", "artista", "album", "canco".
 * @param {string} slug     - entity slug (omit for non-detail pages).
 * @param {object} fallback - optional fallback {title, description}
 *                            shown while the API call is in flight,
 *                            so the page never renders the homepage
 *                            shell title for a brief moment.
 */
export function SeoHead({ entity, slug = '', fallback = null }) {
  const [meta, setMeta] = useState(fallback)

  useEffect(() => {
    let active = true
    const path = slug
      ? `/seo/${entity}/${encodeURIComponent(slug)}/`
      : `/seo/${entity}/`
    api
      .get(path)
      .then(d => { if (active) setMeta(d) })
      .catch(() => { /* fail-open: keep fallback or shell defaults */ })
    return () => { active = false }
  }, [entity, slug])

  if (!meta) return null

  // Schema.org JSON-LD blocks. Critical for Google's Rich Results
  // Test, which executes JS but doesn't see structured data unless
  // the page actually adds a <script type="application/ld+json">.
  // The Django endpoint returns the SAME builders the SSR templates
  // use; we just mirror them into the SPA's <head>.
  const jsonldBlocks = Array.isArray(meta.jsonld) ? meta.jsonld : []
  const escapeJsonForScript = (obj) =>
    JSON.stringify(obj)
      .replace(/</g, '\\u003c')
      .replace(/>/g, '\\u003e')
      .replace(/&/g, '\\u0026')

  return (
    <Helmet>
      <title>{meta.title}</title>
      <meta name="description" content={meta.description} />
      <link rel="canonical" href={meta.canonical_url} />
      <link rel="alternate" hrefLang="ca" href={meta.canonical_url} />
      <link rel="alternate" hrefLang="x-default" href={meta.canonical_url} />
      <meta property="og:type" content={meta.og_type} />
      <meta property="og:title" content={meta.title} />
      <meta property="og:description" content={meta.description} />
      <meta property="og:url" content={meta.canonical_url} />
      <meta property="og:image" content={meta.og_image} />
      <meta property="og:image:width" content="1200" />
      <meta property="og:image:height" content="630" />
      <meta property="og:locale" content={meta.locale} />
      <meta property="og:site_name" content={meta.site_name} />
      <meta name="twitter:card" content={meta.twitter_card} />
      <meta name="twitter:title" content={meta.title} />
      <meta name="twitter:description" content={meta.description} />
      <meta name="twitter:image" content={meta.og_image} />
      {jsonldBlocks.map((block, i) => (
        <script key={i} type="application/ld+json">
          {escapeJsonForScript(block)}
        </script>
      ))}
    </Helmet>
  )
}
