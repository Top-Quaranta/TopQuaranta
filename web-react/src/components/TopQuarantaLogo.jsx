/**
 * TopQuarantaLogo — horizontal rectangular wordmark.
 *
 * Two variants:
 *   - variant="mono" (default): the SVG is inlined into the DOM with
 *     every `fill` set to `currentColor`, so the logo follows the
 *     parent element's CSS `color`. Use this on branded surfaces
 *     (yellow header, black footer).
 *   - variant="color": inlines the full-brand SVG (blue + red + yellow
 *     from the mm-design palette). Use on neutral backgrounds (white
 *     cards) when the branded multicolour version is wanted.
 *
 * We inline via Vite's `?raw` import rather than loading through an
 * <img> + CSS `mask-image`, because the mono file contains many inner
 * elements whose own `style` rules would shadow the mask's implicit
 * alpha mapping on some browsers. Inlining the SVG lets `currentColor`
 * cascade naturally.
 */
import rawMono from '../assets/logo-topquaranta-rect-mono.svg?raw'
import rawColor from '../assets/logo-topquaranta-rect.svg?raw'

// Viewbox aspect ratio of the source SVG: 1876.9116 × 380.45602 → ≈4.93.
const ASPECT_RATIO = 1876.9116 / 380.45602

// Inkscape exports SVGs with `style="fill:X;stroke:Y;..."` inline on
// every path. When that string is injected via `dangerouslySetInnerHTML`,
// the HTML parser preserves the `style` attribute literally but does
// NOT populate the element's `.style` property — so the browser
// computes `fill: black` (the SVG default) instead of the intended
// brand colour. Caught 2026-05-07 with the header logo rendering as
// a flat black blob despite #0047ba/#cf3339/#f1c22f fills being in
// the markup.
//
// Fix: extract `fill:X` and `stroke:X` from the inline `style` and
// promote them to plain `fill="X"` / `stroke="X"` attributes, which
// the HTML parser DOES wire up as SVG presentation attributes. We
// keep the rest of the style intact (opacity, fill-rule,
// stroke-width, …) — those work via the attribute path too but are
// already harmless.
export function promoteStyleToAttributes(svg) {
  return svg.replace(/style="([^"]*)"/g, (match, css) => {
    const get = (prop) => {
      const m = css.match(new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`))
      return m ? m[1].trim() : null
    }
    const fill = get('fill')
    const stroke = get('stroke')
    let extras = ''
    if (fill) extras += ` fill="${fill}"`
    if (stroke) extras += ` stroke="${stroke}"`
    return `${match}${extras}`
  })
}

// The source SVG ships with hardcoded `width`/`height` attributes and
// no explicit sizing class. Strip them so the <svg> fills its wrapper
// <span> instead of rendering at native pixels.
export function normalise(svg) {
  return promoteStyleToAttributes(
    svg
      .replace(/\swidth="[^"]*"/, '')
      .replace(/\sheight="[^"]*"/, '')
      .replace(
        /<svg\b/,
        '<svg style="width:100%;height:100%;display:block"',
      ),
  )
}

const monoSvg = normalise(rawMono)
const colorSvg = normalise(rawColor)

export default function TopQuarantaLogo({
  className = 'h-7',
  variant = 'mono',
  alt = 'TopQuaranta',
}) {
  const svg = variant === 'color' ? colorSvg : monoSvg

  return (
    <span
      role="img"
      aria-label={alt}
      className={className}
      style={{
        display: 'inline-block',
        aspectRatio: ASPECT_RATIO,
        lineHeight: 0,
      }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
