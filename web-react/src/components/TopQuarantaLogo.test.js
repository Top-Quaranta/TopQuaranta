/**
 * Regression tests for the TopQuarantaLogo SVG transformation.
 *
 * These tests anchor the lesson learned 2026-05-07:
 *
 *   The Inkscape-exported brand logo carries presentation as
 *   `style="fill:#XXX;stroke:#YYY;..."` on every path. When the SVG
 *   string is injected via `dangerouslySetInnerHTML`, the HTML parser
 *   keeps the `style` attribute literally but does NOT populate the
 *   element's `.style` property — so `getComputedStyle(path).fill`
 *   returns the SVG default (black) instead of the brand colour.
 *   Result: the logo renders as a flat black blob despite the colour
 *   markup being in the DOM.
 *
 *   We work around this in `normalise()` by promoting `fill:X` and
 *   `stroke:X` from the inline `style` to plain `fill="X"` /
 *   `stroke="X"` attributes — those ARE wired up by the HTML parser.
 *
 * If anyone re-imports the SVG from a fresh Inkscape export and
 * forgets the promotion step, these tests fail. Don't delete them.
 */

import { describe, expect, it } from 'vitest'

import { normalise, promoteStyleToAttributes } from './TopQuarantaLogo'

describe('promoteStyleToAttributes', () => {
  it('extracts fill from an inline style and adds it as an attribute', () => {
    const out = promoteStyleToAttributes('<path style="fill:#0047ba" d="..."/>')
    expect(out).toContain('fill="#0047ba"')
  })

  it('extracts stroke from an inline style and adds it as an attribute', () => {
    const out = promoteStyleToAttributes(
      '<path style="stroke:#cf3339;stroke-width:2" d="..."/>',
    )
    expect(out).toContain('stroke="#cf3339"')
  })

  it('promotes both fill and stroke when both are present', () => {
    const out = promoteStyleToAttributes(
      '<path style="opacity:1;fill:#f1c22f;fill-rule:nonzero;stroke:#cf3339;stroke-width:2" d="..."/>',
    )
    expect(out).toContain('fill="#f1c22f"')
    expect(out).toContain('stroke="#cf3339"')
  })

  it('keeps the original style attribute intact (other props still apply)', () => {
    const out = promoteStyleToAttributes(
      '<path style="opacity:1;fill:#0047ba;fill-rule:nonzero" d="..."/>',
    )
    expect(out).toContain('style="opacity:1;fill:#0047ba;fill-rule:nonzero"')
    expect(out).toContain('fill="#0047ba"')
  })

  it("respects 'none' fill", () => {
    const out = promoteStyleToAttributes(
      '<path style="fill:none;stroke:#0047ba" d="..."/>',
    )
    expect(out).toContain('fill="none"')
    expect(out).toContain('stroke="#0047ba"')
  })

  it('handles whitespace inside the style block', () => {
    const out = promoteStyleToAttributes(
      '<path style="  fill : #cf3339 ; stroke : #f1c22f " d="..."/>',
    )
    expect(out).toContain('fill="#cf3339"')
    expect(out).toContain('stroke="#f1c22f"')
  })

  it("doesn't add fill when none is declared in the style", () => {
    const out = promoteStyleToAttributes(
      '<path style="opacity:0.5" d="..."/>',
    )
    expect(out).not.toMatch(/fill="/)
    expect(out).not.toMatch(/stroke="/)
  })

  it('processes every <path> in a multi-path fragment', () => {
    const input = `<svg>
      <path style="fill:#0047ba" d="A"/>
      <path style="fill:#cf3339" d="B"/>
      <path style="fill:#f1c22f" d="C"/>
    </svg>`
    const out = promoteStyleToAttributes(input)
    expect(out.match(/fill="#0047ba"/g)).toHaveLength(1)
    expect(out.match(/fill="#cf3339"/g)).toHaveLength(1)
    expect(out.match(/fill="#f1c22f"/g)).toHaveLength(1)
  })

  it('promotes currentColor too (mono variant)', () => {
    const out = promoteStyleToAttributes(
      '<path style="fill:currentColor;stroke:currentColor" d="..."/>',
    )
    expect(out).toContain('fill="currentColor"')
    expect(out).toContain('stroke="currentColor"')
  })
})

describe('normalise (full pipeline on the actual SVG asset)', () => {
  it('strips hardcoded width/height and adds the inline sizing style', async () => {
    const svg = await loadSvg('logo-topquaranta-rect.svg')
    const out = normalise(svg)
    expect(out).not.toMatch(/<svg[^>]*\swidth="\d/)
    expect(out).not.toMatch(/<svg[^>]*\sheight="\d/)
    expect(out).toContain('style="width:100%;height:100%;display:block"')
  })

  it('converts every brand-coloured fill in the colour SVG to an attribute', async () => {
    const svg = await loadSvg('logo-topquaranta-rect.svg')
    const out = normalise(svg)
    // The colour SVG uses #0047ba, #cf3339, #f1c22f as fills.
    // Every occurrence inside an inline style must also appear as an
    // SVG presentation attribute on the same element.
    const styleFillCount = (out.match(/style="[^"]*fill:#[0-9a-f]{6}/gi) || [])
      .length
    const attrFillCount = (out.match(/\sfill="#[0-9a-f]{6}"/gi) || []).length
    expect(attrFillCount).toBeGreaterThanOrEqual(styleFillCount)
  })

  it('converts every brand-coloured stroke in the colour SVG to an attribute', async () => {
    const svg = await loadSvg('logo-topquaranta-rect.svg')
    const out = normalise(svg)
    const styleStrokeCount = (
      out.match(/style="[^"]*stroke:#[0-9a-f]{6}/gi) || []
    ).length
    const attrStrokeCount = (out.match(/\sstroke="#[0-9a-f]{6}"/gi) || []).length
    expect(attrStrokeCount).toBeGreaterThanOrEqual(styleStrokeCount)
  })

  it('promotes currentColor across the mono SVG', async () => {
    const svg = await loadSvg('logo-topquaranta-rect-mono.svg')
    const out = normalise(svg)
    // After substitution, EVERY style block that mentions currentColor
    // must produce a matching attribute.
    const styleCount = (
      out.match(/style="[^"]*(?:fill|stroke):currentColor/gi) || []
    ).length
    expect(styleCount).toBeGreaterThan(0) // sanity: there ARE such blocks
    const fillAttrs = (out.match(/\sfill="currentColor"/gi) || []).length
    const strokeAttrs = (out.match(/\sstroke="currentColor"/gi) || []).length
    // Each style block has either fill OR stroke (sometimes both); at
    // minimum, the total attribute count should reach the style count.
    expect(fillAttrs + strokeAttrs).toBeGreaterThanOrEqual(styleCount)
  })

  it('mono SVG does not pin currentColor to red via root style', async () => {
    const svg = await loadSvg('logo-topquaranta-rect-mono.svg')
    // The vendor SVG has `style="color:#cf3339"` on the root <svg>,
    // which would override `currentColor` everywhere to red. The mono
    // generation step must strip this — otherwise mono on a yellow
    // header renders red instead of inheriting the parent's text-tq-ink.
    expect(svg).not.toMatch(/<svg[^>]*style="[^"]*color\s*:\s*#cf3339/i)
  })
})

// ── Helpers ─────────────────────────────────────────────────────────

async function loadSvg(filename) {
  // Vitest runs in node — read the SVG asset from disk.
  const fs = await import('node:fs/promises')
  const url = await import('node:url')
  const path = await import('node:path')
  const here = path.dirname(url.fileURLToPath(import.meta.url))
  return fs.readFile(path.join(here, '..', 'assets', filename), 'utf8')
}
