/**
 * MmIcon — render a monochrome mm-design SVG via CSS mask so it picks
 * up `currentColor`. Used everywhere we want an icon to follow the
 * surrounding text/background colour without ad-hoc inlined SVGs or
 * raw <img> tags (which would render the SVG's own black fill and
 * lose `color` inheritance).
 *
 * Props:
 *   - name (required): basename of the SVG file inside
 *     `/static/mm-design/icons/<bucket>/<name>.svg`. The default
 *     bucket is `ui` (the most common one); pass `bucket="territories"`
 *     to reach `/static/mm-design/icons/territories/territory-cat.svg`,
 *     etc.
 *   - className: Tailwind utilities for sizing (default `h-4 w-4`).
 *   - label: when given, the span gets `role="img"` + `aria-label`,
 *     making it screen-reader visible. Without it, the icon is treated
 *     as decorative.
 */
export default function MmIcon({ name, bucket = 'ui', className = 'h-4 w-4', label }) {
  const url = `/static/mm-design/icons/${bucket}/${name}.svg`
  return (
    <span
      role={label ? 'img' : 'presentation'}
      aria-label={label}
      className={`inline-block shrink-0 ${className}`}
      style={{
        backgroundColor: 'currentColor',
        WebkitMaskImage: `url(${url})`,
        maskImage: `url(${url})`,
        WebkitMaskRepeat: 'no-repeat',
        maskRepeat: 'no-repeat',
        WebkitMaskPosition: 'center',
        maskPosition: 'center',
        WebkitMaskSize: 'contain',
        maskSize: 'contain',
      }}
    />
  )
}
