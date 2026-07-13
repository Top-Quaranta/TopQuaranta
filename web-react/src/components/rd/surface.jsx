/**
 * rd/surface.jsx — light staff surface kit (canon, staff-unification
 * option B: staff stays white; the rd canon owns the light layer).
 *
 * This is the single home of the staff table/form chrome. `TableCard`
 * and `Btn` delegate to the rd canon (`Glass tone="light"` / the unified
 * `Btn`); the rest are the light primitives the canon gained for staff.
 * `components/staff/StaffTable.jsx` re-exports everything here as a
 * back-compat shim (so public pages importing `Field`/`Select` and the
 * shared `FilterPanel`/panels keep working). Staff pages import from
 * here directly.
 *
 * Every class string is byte-for-byte the historical StaffTable kit, so
 * the retrofit is pixel-identical by construction.
 */
import { Btn as CanonBtn, Glass } from './primitives'

/* White card — the rd canon light surface (`Glass tone="light"`). */
export function TableCard({ children, className = "" }) {
  return (
    <Glass tone="light" className={className}>
      {children}
    </Glass>
  );
}

/**
 * Wrap the real <table> in a horizontally-scrollable div so dense
 * staff lists don't collapse / get cut off on mobile. `min-w-[640px]`
 * keeps a sensible minimum width even when there's plenty of room
 * (prevents the table from cramming columns) — narrower viewports
 * trigger the inner scrollbar. The outer `TableCard` still owns
 * `overflow-hidden` for its rounded corners, so this scroll lives
 * just inside that mask.
 */
export function Table({ children }) {
  // tabIndex + role+aria-label so the horizontally-scrollable
  // region is reachable by keyboard (axe-core
  // scrollable-region-focusable, WCAG 2.1.1).
  return (
    <div
      className="overflow-x-auto"
      tabIndex={0}
      role="region"
      aria-label="Taula desplaçable"
    >
      <table className="w-full min-w-[640px] text-sm">{children}</table>
    </div>
  );
}

export function THead({ children }) {
  return (
    <thead className="bg-tq-ink/5 text-[11px] uppercase tracking-wide">
      {children}
    </thead>
  );
}

export function Th({ children, className = "", ...rest }) {
  return (
    <th className={"text-left font-semibold px-3 py-2 " + className} {...rest}>
      {children}
    </th>
  );
}

/**
 * Forward arbitrary props (most importantly `onClick`) so callers
 * can attach e.g. `e.stopPropagation()` on the cell wrapping a
 * checkbox to keep Tr-level navigation from eating the click. Was
 * a silent drop before, which made checkboxes in clickable rows
 * behave as if they navigated instead of toggling.
 */
export function Td({ children, className = "", ...rest }) {
  return (
    <td className={"px-3 py-2 align-middle " + className} {...rest}>
      {children}
    </td>
  );
}

export function Tr({ children, onClick, className = "" }) {
  return (
    <tr
      onClick={onClick}
      className={
        "border-t border-black/5 " +
        (onClick ? "hover:bg-tq-yellow/10 cursor-pointer " : "") +
        className
      }
    >
      {children}
    </tr>
  );
}

export function EmptyState({ children }) {
  return <p className="px-3 py-6 text-sm opacity-60 text-center">{children}</p>;
}

// Callout — a full-width banner for inline feedback (errors, success
// notices, warnings) on the staff panel's white card surfaces. The wide
// counterpart of Pill (which is for short inline states). Tones go
// through the mm-design semantic tokens so a palette change reaches every
// callout in one edit; a soft tint background keeps it readable on white.
export function Callout({ tone = "info", children, className = "" }) {
  const sem = {
    red: { bg: "rgba(239, 68, 68, 0.12)", fg: "var(--color-tq-danger-deep)" },
    green: {
      bg: "rgba(16, 185, 129, 0.12)",
      fg: "var(--color-tq-success-deep)",
    },
    yellow: {
      bg: "rgba(250, 204, 21, 0.18)",
      fg: "var(--color-tq-yellow-deep, #ca8a04)",
    },
    info: {
      bg: "rgba(156, 163, 175, 0.18)",
      fg: "var(--color-tq-neutral-deep, #4b5563)",
    },
  };
  const s = sem[tone] || sem.info;
  return (
    <div
      role={tone === "red" ? "alert" : "status"}
      className={`p-3 rounded-md text-sm ${className}`}
      style={{ background: s.bg, color: s.fg }}
    >
      {children}
    </div>
  );
}

export function Pill({ children, tone = "ink" }) {
  // Brand tones use Tailwind utilities; semantic ones go through the
  // design tokens (`--color-tq-success/danger/neutral`) so a palette
  // change reaches every pill in one edit.
  if (tone === "ink" || tone === "yellow") {
    const cls =
      tone === "yellow"
        ? "bg-tq-yellow text-tq-ink"
        : "bg-tq-ink/10 text-tq-ink";
    return (
      <span
        className={`inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full ${cls}`}
      >
        {children}
      </span>
    );
  }
  // Pills sit on white card backgrounds in the staff panel. The
  // foreground uses the *-deep tokens (AA on white at small text);
  // the background is a soft tint of the same hue. Hardcoded hex
  // here would break the design-system rule, so we go through the
  // mm-design CSS variables.
  const sem = {
    green: {
      bg: "rgba(16, 185, 129, 0.18)",
      fg: "var(--color-tq-success-deep)",
    },
    red: { bg: "rgba(239, 68, 68, 0.18)", fg: "var(--color-tq-danger-deep)" },
    gray: {
      bg: "rgba(156, 163, 175, 0.25)",
      fg: "var(--color-tq-neutral-deep)",
    },
  };
  const s = sem[tone] || sem.gray;
  return (
    <span
      className="inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full"
      style={{ background: s.bg, color: s.fg }}
    >
      {children}
    </span>
  );
}

/* Button — the unified rd canon button. The staff surface keeps its
   historical default (`tone="primary"`) and delegates to the canon
   `Btn`, so existing staff call-sites (incl. the many that rely on the
   implicit primary) stay pixel-identical. */
export function Btn({ tone = "primary", ...rest }) {
  return <CanonBtn tone={tone} {...rest} />;
}

export function Input(props) {
  return (
    <input
      {...props}
      className={
        "text-sm px-2.5 py-1.5 rounded border border-tq-ink/20 bg-white text-tq-ink placeholder-tq-ink/40 focus:outline-none focus:ring-2 focus:ring-tq-yellow " +
        (props.className || "")
      }
    />
  );
}

export function Textarea(props) {
  return (
    <textarea
      {...props}
      className={
        "text-sm px-2.5 py-1.5 rounded border border-tq-ink/20 bg-white text-tq-ink placeholder-tq-ink/40 focus:outline-none focus:ring-2 focus:ring-tq-yellow resize-y min-h-[8rem] font-normal leading-snug " +
        (props.className || "")
      }
    />
  );
}

export function Select({ children, ...props }) {
  return (
    <select
      {...props}
      className={
        "text-sm px-2.5 py-1.5 rounded border border-tq-ink/20 bg-white text-tq-ink focus:outline-none focus:ring-2 focus:ring-tq-yellow " +
        (props.className || "")
      }
    >
      {children}
    </select>
  );
}

export function Pagination({ meta, onPage }) {
  if (!meta || meta.num_pages <= 1) return null;
  return (
    <div className="flex items-center gap-2 px-3 py-2 text-xs text-tq-ink/75">
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
  );
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
  );
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
  );
}
