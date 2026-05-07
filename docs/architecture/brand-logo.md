# Brand logo — what we got wrong, what works

This is a "lessons learned" doc, not architecture in the usual
sense. Read it before you touch anything that loads or transforms
the brand logo SVG (`logo-topquaranta-rect.svg`,
`logo-topquaranta-rect-mono.svg`, or any of their renderers).

## The asset

The canonical source is `vendor/mm-design/icons/brand/logo-topquaranta-rect.svg`
— a multi-colour Inkscape export. The SPA copies live at
`web-react/src/assets/logo-topquaranta-rect.svg` (verbatim copy of
the vendor) and `…-mono.svg` (the same SVG with the three brand
colours `#0047ba`, `#cf3339`, `#f1c22f` substituted by `currentColor`
**and** the root `style="color:#cf3339"` stripped).

The Python social renderer (`social/svg_assets.py`) reads the vendor
file directly and rasterises it with `cairosvg`.

## Three traps we've fallen into

### 1. cairosvg missing in production

`social/svg_assets.py` does an optional `import cairosvg` and
returns `None` when the dep is missing. The renderer then does
`paste(None)` and silently no-ops. Result: territorial portades
publish with an empty accent pill where the logo should sit.

**Caught**: 2026-05-07. Cairosvg wasn't in `requirements.txt`.

**Fix**: `cairosvg==2.9.0` in requirements; tested locally + on
production.

### 2. HTML parser doesn't apply inline `style` to SVG paths

The Inkscape-exported SVG uses
`style="fill:#0047ba;stroke:none;..."` on every path. When the
React component injects the SVG via `dangerouslySetInnerHTML`, the
HTML parser preserves the `style` attribute string but does **NOT**
populate the element's `.style` property. So
`getComputedStyle(path).fill` returns the SVG default (black)
instead of the intended brand colour.

This isn't a bug in our SVG, in our component, or in React — it's
a quirk of HTML parsing of SVG fragments inserted via `innerHTML`.
The same SVG opens correctly in Inkscape, in `<img src=>`, and in
any standalone `.svg` file.

**Caught**: 2026-05-07. The header logo rendered as a flat black
blob.

**Fix**: `normalise()` in `TopQuarantaLogo.jsx` extracts `fill:X`
and `stroke:X` from each path's inline `style` and promotes them
to plain `fill="X"` / `stroke="X"` attributes — those ARE wired up
by the HTML parser, regardless of namespace gymnastics. Anchored
by 14 vitest cases in `TopQuarantaLogo.test.js`.

### 3. Mono variant by colour-substitution flattens the design

The brand logo uses three distinct colours to distinguish the three
geometric layers (circle, play triangle, wordmark). Replacing all
three with a single `currentColor` makes them all paint in the
same ink, so the play disappears inside the circle and the design
becomes one solid blob.

**The fix isn't a different SVG**. The transformation that
`promoteStyleToAttributes` applies (item 2 above) produces a working
mono variant **because** the SVG's stroked-outline layer (separate
paths drawn with `fill:none` + `stroke:#XXX`) takes over visually
from the filled-block layer. With every colour collapsed to ink,
the outlines and fills overlap exactly, and the eye reads the
strokes as the final shape — circle outline + play outline +
wordmark outline + wordmark filled, all in ink. It looks editorial,
not flat.

If you regenerate the SVG and the new export lacks the stroked
layer, the mono variant will fail. At that point: either fix the
export to keep the strokes, or use the colour variant only.

## Where the SVG colours come from

The three brand colours are baked into the file (Inkscape doesn't
parameterise them). They mirror `social/colors.py::TERR_COLORS`
values + the project's `tq-yellow-deep`:

  - `#0047ba` — mm-color-blue, used for the circle and the play
  - `#cf3339` — mm-color-error / red, used for the "T" wordmark
  - `#f1c22f` — mm-design yellow (slightly different from the
    SPA's `tq-yellow #facc15`; the SPA value is brighter)

The SVG also has `style="color:#cf3339"` on the root `<svg>` tag.
That sets `currentColor` to red for any descendant that uses
`currentColor` directly (without a `color` cascade from a parent).
For the **mono** variant we strip this — otherwise the mono renders
red instead of inheriting the parent's `text-tq-ink` (or whatever
the page sets).

## The component contract

`<TopQuarantaLogo>` accepts:

  - `className` — sizing, e.g. `"h-7 w-auto"`. The logo's aspect
    ratio is preserved via the wrapper `<span>`'s `aspect-ratio`
    style (≈4.93:1).
  - `variant` — `"mono"` (default) or `"color"`. Mono follows the
    parent's `color` CSS via `currentColor`. Color shows the brand
    palette regardless of context.
  - `alt` — accessibility label.

The wrapping `<Link>` should set `text-tq-ink` (or whichever ink
colour the surface needs) when using the mono variant — the SVG
inherits that.

## When you next change anything

  1. **Run `cd web-react && npm test`** before pushing. The 14
     vitest cases catch the most common regressions: missing
     fill-attribute promotion, root colour pinning currentColor,
     bad whitespace handling.
  2. If you replace the SVG file, do it in BOTH `vendor/` and
     `web-react/src/assets/` (color), then regenerate the mono via:
     ```bash
     sed -e 's/#f1c22f/currentColor/g' \
         -e 's/#cf3339/currentColor/g' \
         -e 's/#0047ba/currentColor/g' \
         -e 's/style="color:currentColor"/style=""/' \
         vendor/mm-design/icons/brand/logo-topquaranta-rect.svg \
         > web-react/src/assets/logo-topquaranta-rect-mono.svg
     ```
  3. Verify on a real page: visit `/` and inspect the header span
     in DevTools. `getComputedStyle(path).fill` for any random path
     must NOT be `rgb(0, 0, 0)` — it must be a real colour
     (`rgb(0, 71, 186)` etc.) or, on the mono variant,
     `rgb(10, 10, 10)` (= ink).
