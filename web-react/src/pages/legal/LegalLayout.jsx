/**
 * LegalLayout — shared chrome for every /legal/* page.
 *
 * Editorial style: white surface, Playfair title, "última actualització"
 * line, "Tornar a Legal" link at the top. Same primitive used by
 * /legal index and each individual subpage so the package reads as
 * a coherent corpus.
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Section } from '../../components/editorial'

export const LEGAL_VERSIO = '2026-04-26'

const SECCIONS = [
  ['avis-legal',     'Avís legal'],
  ['privacitat',     'Política de privacitat'],
  ['cookies',        'Política de cookies'],
  ['termes',         'Termes i condicions'],
  ['codi-conducta',  'Codi de conducta'],
  ['llicencies',     'Llicències i propietat intel·lectual'],
  ['accessibilitat', 'Accessibilitat'],
]

export function LegalIndex() {
  useEffect(() => { document.title = 'Legal — TopQuaranta' }, [])
  return (
    <div className="space-y-0">
      <Section tone="ink">
        <p className="text-[10px] uppercase tracking-widest text-tq-yellow">Legal</p>
        <h1 className="text-3xl md:text-5xl font-bold font-display mt-1.5 leading-tight">
          Lletra petita, en gran
        </h1>
        <p className="text-sm md:text-base text-white/80 mt-3 max-w-2xl leading-relaxed">
          Tot el que un visitant, usuari o autoritat hauria de poder
          consultar sobre TopQuaranta: qui som, què guardem, què hi pots
          fer, i com exercir els teus drets. En català planer.
        </p>
        <p className="text-xs text-white/50 mt-2">
          Última actualització: {LEGAL_VERSIO}
        </p>
      </Section>

      <Section tone="white">
        <ul className="grid sm:grid-cols-2 gap-3">
          {SECCIONS.map(([slug, titol]) => (
            <li key={slug}>
              <Link
                to={`/legal/${slug}`}
                className="block p-4 border border-tq-ink/10 rounded-md hover:border-tq-ink/30 transition-colors"
              >
                <p className="font-bold font-display text-base">{titol}</p>
                <p className="text-xs text-tq-ink/60 mt-1">/legal/{slug}</p>
              </Link>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  )
}

/* Wrapper for individual sub-pages. Renders a small breadcrumb +
 * the page title in the editorial style + the body underneath in a
 * reading-friendly column. */
export function LegalPage({ titol, intro, children }) {
  useEffect(() => { document.title = `${titol} — Legal — TopQuaranta` }, [titol])
  return (
    <div className="space-y-0">
      <Section tone="ink">
        <p className="text-[10px] uppercase tracking-widest text-tq-yellow">
          <Link to="/legal" className="underline hover:text-white transition-colors">
            Legal
          </Link>
        </p>
        <h1 className="text-3xl md:text-4xl font-bold font-display mt-1.5 leading-tight">
          {titol}
        </h1>
        {intro && (
          <p className="text-sm md:text-base text-white/80 mt-3 max-w-2xl leading-relaxed">
            {intro}
          </p>
        )}
        <p className="text-xs text-white/50 mt-2">
          Última actualització: {LEGAL_VERSIO}
        </p>
      </Section>

      <Section tone="white">
        <article
          className="max-w-3xl mx-auto text-tq-ink text-sm leading-relaxed
                     [&_h2]:text-xl [&_h2]:font-bold [&_h2]:font-display
                     [&_h2]:mt-8 [&_h2]:mb-3
                     [&_h3]:text-base [&_h3]:font-bold [&_h3]:font-display
                     [&_h3]:mt-5 [&_h3]:mb-2
                     [&_p]:my-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:my-3
                     [&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:my-3
                     [&_li]:my-1
                     [&_a]:underline [&_a]:hover:text-tq-yellow-deep
                     [&_strong]:font-semibold"
        >
          {children}
        </article>
      </Section>
    </div>
  )
}
