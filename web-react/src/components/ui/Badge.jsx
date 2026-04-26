/**
 * Badge — small label pill.
 *
 * Tones reflect the design-system semantic palette declared at
 * `src/index.css @theme` (`--color-tq-success`, `--color-tq-danger`,
 * `--color-tq-warning`, `--color-tq-neutral`). Inline styles use the
 * tokens so a brand palette update flows through without touching
 * call sites.
 *
 * variant: default | ink | yellow | success | danger | warning
 */
const STYLES = {
  default: { bg: 'rgba(156, 163, 175, 0.16)', fg: 'var(--color-tq-neutral, #6b7280)' },
  success: { bg: 'rgba(16, 185, 129, 0.16)',  fg: 'var(--color-tq-success)'          },
  danger:  { bg: 'rgba(239, 68, 68, 0.16)',   fg: 'var(--color-tq-danger)'           },
  warning: { bg: 'rgba(250, 204, 21, 0.20)',  fg: 'var(--color-tq-yellow-deep)'      },
}

export default function Badge({ children, variant = 'default', className = '' }) {
  // ink/yellow are brand variants — keep the Tailwind classes.
  if (variant === 'ink' || variant === 'yellow') {
    const cls = variant === 'ink' ? 'bg-tq-ink text-tq-yellow' : 'bg-tq-yellow text-tq-ink'
    return (
      <span className={`inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded ${cls} ${className}`}>
        {children}
      </span>
    )
  }
  const s = STYLES[variant] || STYLES.default
  return (
    <span
      className={`inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded ${className}`}
      style={{ background: s.bg, color: s.fg }}
    >
      {children}
    </span>
  )
}
