import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** Allow only safe URL schemes on links + images. Relative URLs and
 *  fragments are kept; http/https/mailto are kept; everything else
 *  (javascript:, data:, vbscript:, …) is dropped to an empty string so
 *  it never renders as an executable href/src. Belt-and-braces on top of
 *  react-markdown's own default sanitization. Exported for unit testing. */
export function safeUrl(url) {
  const u = (url || '').trim()
  if (!u) return ''
  // Relative or anchor: safe.
  if (u.startsWith('/') || u.startsWith('#') || u.startsWith('.')) return u
  const m = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(u)
  if (!m) return u // no scheme -> relative-ish, safe
  const scheme = m[1].toLowerCase()
  return ['http', 'https', 'mailto'].includes(scheme) ? u : ''
}

/** Renders user-supplied markdown. react-markdown never emits raw HTML,
 *  so this is XSS-safe without extra sanitization.
 *
 *  Heading levels are shifted down one step: markdown `#` becomes `<h2>`,
 *  `##` becomes `<h3>`, etc. The page that embeds the post already has a
 *  real `<h1>` (the post title), so this keeps semantics clean AND makes
 *  `#` render as a visibly big-but-not-page-title heading. */
export default function Markdown({ children, className = '' }) {
  return (
    <div
      className={
        'leading-relaxed ' +
        '[&_h2]:text-2xl [&_h2]:font-display [&_h2]:font-bold [&_h2]:mt-5 [&_h2]:mb-2 [&_h2]:leading-tight ' +
        '[&_h3]:text-xl [&_h3]:font-display [&_h3]:font-bold [&_h3]:mt-4 [&_h3]:mb-2 [&_h3]:leading-tight ' +
        '[&_h4]:text-lg [&_h4]:font-semibold [&_h4]:mt-3 [&_h4]:mb-1 ' +
        '[&_h5]:text-base [&_h5]:font-semibold [&_h5]:uppercase [&_h5]:tracking-wide [&_h5]:mt-3 [&_h5]:mb-1 ' +
        '[&_h6]:text-sm [&_h6]:font-semibold [&_h6]:uppercase [&_h6]:tracking-wide [&_h6]:opacity-70 [&_h6]:mt-3 [&_h6]:mb-1 ' +
        '[&_p]:mb-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:mb-3 ' +
        '[&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:mb-3 ' +
        '[&_li]:mb-1 ' +
        '[&_code]:bg-black/10 [&_code]:px-1 [&_code]:rounded [&_code]:text-[0.9em] ' +
        '[&_pre]:bg-black/10 [&_pre]:p-3 [&_pre]:rounded [&_pre]:overflow-x-auto [&_pre]:mb-3 ' +
        '[&_pre_code]:bg-transparent [&_pre_code]:p-0 ' +
        '[&_blockquote]:border-l-4 [&_blockquote]:border-tq-yellow [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:opacity-80 [&_blockquote]:my-3 ' +
        '[&_strong]:font-bold [&_em]:italic ' +
        '[&_hr]:my-4 [&_hr]:border-black/20 ' +
        '[&_img]:max-w-full [&_img]:h-auto [&_img]:rounded-lg [&_img]:my-3 [&_img]:block ' +
        '[&_table]:border-collapse [&_table]:my-3 ' +
        '[&_th]:border [&_th]:border-black/20 [&_th]:px-2 [&_th]:py-1 [&_th]:bg-black/5 ' +
        '[&_td]:border [&_td]:border-black/20 [&_td]:px-2 [&_td]:py-1 ' +
        className
      }
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={safeUrl}
        components={{
          // Shift every heading down one level. `#` (h1 in md) renders
          // as h2 in the DOM, `##` as h3, … `######` stays at h6.
          h1: ({ node, ...props }) => <h2 {...props} />,
          h2: ({ node, ...props }) => <h3 {...props} />,
          h3: ({ node, ...props }) => <h4 {...props} />,
          h4: ({ node, ...props }) => <h5 {...props} />,
          h5: ({ node, ...props }) => <h6 {...props} />,
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" className="underline" />
          ),
          img: ({ node, alt, ...props }) => (
            // `loading=lazy` keeps feed scrolling light; alt stays
            // meaningful for screen readers.
            <img alt={alt || ''} loading="lazy" {...props} />
          ),
        }}
      >
        {children || ''}
      </ReactMarkdown>
    </div>
  )
}
