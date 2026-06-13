/**
 * LegalLayout — shared chrome for every /legal/* page (redisseny web).
 *
 * Dark hero (Anton title + "última actualització") + a glass reading
 * card with the long-form prose in the new language. Restyling this one
 * file migrates the whole legal corpus (index + 7 subpages) at once.
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Band, Glow, Glass, Kicker, Crit } from '../../components/rd/primitives'

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
    <>
      <Band tone="top-hero">
        <Glow variant="a" />
        <div className="max-w-3xl">
          <Kicker className="block mb-2">la lletra petita</Kicker>
          <Crit as="h1" className="rd-top-h1">LEGAL</Crit>
          <p className="rd-hero-sub">
            Tot el que un visitant, usuari o autoritat hauria de poder consultar
            sobre TopQuaranta: qui som, què guardem, què hi pots fer, i com
            exercir els teus drets. En català planer.
          </p>
          <p className="text-xs text-white/45 mt-2">Última actualització: {LEGAL_VERSIO}</p>
        </div>
      </Band>
      <Band tone="ink2">
        <ul className="grid sm:grid-cols-2 gap-3 max-w-3xl">
          {SECCIONS.map(([slug, titol]) => (
            <li key={slug}>
              <Glass as={Link} to={`/legal/${slug}`} className="block p-4">
                <p className="font-extrabold text-white" style={{ fontFamily: 'var(--font-body)' }}>{titol}</p>
                <p className="text-xs text-white/50 mt-1">/legal/{slug}</p>
              </Glass>
            </li>
          ))}
        </ul>
      </Band>
    </>
  )
}

export function LegalPage({ titol, intro, children }) {
  useEffect(() => { document.title = `${titol} — Legal — TopQuaranta` }, [titol])
  return (
    <>
      <Band tone="top-hero">
        <Glow variant="a" />
        <div className="max-w-3xl">
          <Kicker className="block mb-2">
            <Link to="/legal" className="underline hover:text-white transition-colors" style={{ color: 'inherit' }}>← Legal</Link>
          </Kicker>
          <Crit as="h1" className="rd-cc-title" style={{ marginTop: 0 }}>{titol}</Crit>
          {intro && <p className="rd-hero-sub">{intro}</p>}
          <p className="text-xs text-white/45 mt-2">Última actualització: {LEGAL_VERSIO}</p>
        </div>
      </Band>
      <Band tone="ink2">
        <Glass className="rd-legal-card">
          <article
            className="rd-legal-prose
                       [&_h2]:font-crit [&_h2]:text-2xl [&_h2]:mt-8 [&_h2]:mb-3 [&_h2]:text-white
                       [&_h3]:font-bold [&_h3]:text-base [&_h3]:mt-5 [&_h3]:mb-2 [&_h3]:text-white
                       [&_p]:my-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:my-3
                       [&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:my-3 [&_li]:my-1
                       [&_a]:underline [&_a]:text-tq-yellow [&_strong]:font-semibold [&_strong]:text-white"
          >
            {children}
          </article>
        </Glass>
      </Band>
    </>
  )
}
