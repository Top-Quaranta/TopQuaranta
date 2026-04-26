/**
 * StaffTable — light wrapper around a real <table>.
 *
 * Most staff pages need the same things: a white container, a dense
 * header, clickable row links, occasional action buttons in the last
 * column. Centralising the chrome keeps pages short and consistent.
 */
export function TableCard({ children, className = '' }) {
  return (
    <div
      className={
        'bg-white text-tq-ink rounded-lg border border-black/5 overflow-hidden ' +
        className
      }
    >
      {children}
    </div>
  )
}

export function Table({ children }) {
  return <table className="w-full text-sm">{children}</table>
}

export function THead({ children }) {
  return (
    <thead className="bg-tq-ink/5 text-[11px] uppercase tracking-wide">
      {children}
    </thead>
  )
}

export function Th({ children, className = '', ...rest }) {
  return (
    <th
      className={'text-left font-semibold px-3 py-2 ' + className}
      {...rest}
    >
      {children}
    </th>
  )
}

/**
 * Forward arbitrary props (most importantly `onClick`) so callers
 * can attach e.g. `e.stopPropagation()` on the cell wrapping a
 * checkbox to keep Tr-level navigation from eating the click. Was
 * a silent drop before, which made checkboxes in clickable rows
 * behave as if they navigated instead of toggling.
 */
export function Td({ children, className = '', ...rest }) {
  return (
    <td className={'px-3 py-2 align-middle ' + className} {...rest}>
      {children}
    </td>
  )
}

export function Tr({ children, onClick, className = '' }) {
  return (
    <tr
      onClick={onClick}
      className={
        'border-t border-black/5 ' +
        (onClick ? 'hover:bg-tq-yellow/10 cursor-pointer ' : '') +
        className
      }
    >
      {children}
    </tr>
  )
}

export function EmptyState({ children }) {
  return <p className="px-3 py-6 text-sm opacity-60 text-center">{children}</p>
}

export function Pill({ children, tone = 'ink' }) {
  // Brand tones use Tailwind utilities; semantic ones go through the
  // design tokens (`--color-tq-success/danger/neutral`) so a palette
  // change reaches every pill in one edit.
  if (tone === 'ink' || tone === 'yellow') {
    const cls =
      tone === 'yellow'
        ? 'bg-tq-yellow text-tq-ink'
        : 'bg-tq-ink/10 text-tq-ink'
    return (
      <span
        className={`inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full ${cls}`}
      >
        {children}
      </span>
    )
  }
  const sem = {
    green: { bg: 'rgba(16, 185, 129, 0.16)', fg: 'var(--color-tq-success)' },
    red:   { bg: 'rgba(239, 68, 68, 0.16)',  fg: 'var(--color-tq-danger)' },
    gray:  { bg: 'rgba(156, 163, 175, 0.20)', fg: 'var(--color-tq-neutral, #6b7280)' },
  }
  const s = sem[tone] || sem.gray
  return (
    <span
      className="inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full"
      style={{ background: s.bg, color: s.fg }}
    >
      {children}
    </span>
  )
}

export function Btn({
  children,
  tone = 'primary',
  size = 'sm',
  disabled,
  ...rest
}) {
  const tones = {
    primary: 'bg-tq-ink text-tq-yellow hover:bg-tq-ink/90',
    secondary:
      'bg-transparent text-tq-ink border border-tq-ink/20 hover:bg-tq-ink/5',
    outline:
      'bg-transparent text-white border border-white/30 hover:bg-white/10',
    danger: 'bg-red-600 text-white hover:bg-red-700',
    ghost: 'text-tq-ink/70 hover:text-tq-ink hover:bg-tq-ink/5',
  }
  const sizes = {
    sm: 'text-xs font-semibold px-2.5 py-1 rounded',
    md: 'text-sm font-semibold px-3 py-1.5 rounded',
  }
  return (
    <button
      type="button"
      disabled={disabled}
      className={
        (tones[tone] || tones.primary) +
        ' ' +
        (sizes[size] || sizes.sm) +
        ' transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
      }
      {...rest}
    >
      {children}
    </button>
  )
}

export function Input(props) {
  return (
    <input
      {...props}
      className={
        'text-sm px-2.5 py-1.5 rounded border border-tq-ink/20 bg-white text-tq-ink placeholder-tq-ink/40 focus:outline-none focus:ring-2 focus:ring-tq-yellow ' +
        (props.className || '')
      }
    />
  )
}

export function Select({ children, ...props }) {
  return (
    <select
      {...props}
      className={
        'text-sm px-2.5 py-1.5 rounded border border-tq-ink/20 bg-white text-tq-ink focus:outline-none focus:ring-2 focus:ring-tq-yellow ' +
        (props.className || '')
      }
    >
      {children}
    </select>
  )
}

export function Pagination({ meta, onPage }) {
  if (!meta || meta.num_pages <= 1) return null
  return (
    <div className="flex items-center gap-2 px-3 py-2 text-xs text-tq-ink/60">
      <Btn
        tone="secondary"
        disabled={!meta.has_previous}
        onClick={() => onPage(meta.page - 1)}
      >
        Anterior
      </Btn>
      <span>
        Pàg {meta.page} de {meta.num_pages} · {meta.total} entrades
      </span>
      <Btn
        tone="secondary"
        disabled={!meta.has_next}
        onClick={() => onPage(meta.page + 1)}
      >
        Següent
      </Btn>
    </div>
  )
}

export function PageHeader({ title, subtitle, right }) {
  return (
    <header className="mb-4 flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-2xl font-bold text-white">{title}</h1>
        {subtitle && <p className="text-sm text-white/70">{subtitle}</p>}
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </header>
  )
}

/**
 * Field — labelled wrapper for a select/input inside the FilterPanel.
 * Centralised so the three list pages (Artistes, Cançons, Albums)
 * stop redefining the same helper.
 */
export function Field({ label, children }) {
  return (
    <label className="flex flex-col gap-1 text-xs font-semibold text-tq-ink/80">
      <span>{label}</span>
      {children}
    </label>
  )
}
