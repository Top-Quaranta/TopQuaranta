/**
 * Alert — banner for inline feedback (form errors, success notices,
 * informational warnings) with semantic tones.
 *
 * Replaces the dozens of ad-hoc `bg-red-100 text-red-800 p-3 rounded-md`
 * blocks scattered across pages, which all needed updating in concert
 * any time the brand palette shifted. Tones map to the design-system
 * semantic colour tokens (declared in `src/index.css @theme`):
 *
 *   - danger  → `--color-tq-danger`  (errors, rebuig)
 *   - success → `--color-tq-success` (confirmacions, OK)
 *   - warning → `--color-tq-warning` (avisos, dubtes)
 *   - info    → `--color-tq-neutral` (informació neutra)
 *
 * Backgrounds use a 12% alpha tint of the same hue so the banner reads
 * even on the dark ink body, and text picks the saturated token for
 * accessible contrast on light surfaces.
 *
 * Props:
 *   - tone (default 'danger')
 *   - children: the message
 *   - className: extra utility classes (e.g. layout margins)
 */
const TONES = {
  danger:  { bg: 'rgba(239, 68, 68, 0.12)',   fg: 'var(--color-tq-danger)'  },
  success: { bg: 'rgba(16, 185, 129, 0.12)',  fg: 'var(--color-tq-success)' },
  warning: { bg: 'rgba(250, 204, 21, 0.16)',  fg: 'var(--color-tq-yellow-deep, #ca8a04)' },
  info:    { bg: 'rgba(156, 163, 175, 0.16)', fg: 'var(--color-tq-neutral, #6b7280)' },
}

export default function Alert({ tone = 'danger', children, className = '' }) {
  const t = TONES[tone] || TONES.danger
  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      className={`p-3 rounded-md text-sm ${className}`}
      style={{ background: t.bg, color: t.fg }}
    >
      {children}
    </div>
  )
}
