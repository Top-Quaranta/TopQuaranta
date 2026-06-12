/**
 * rd/Footer — single-line dark footer (#060608) with the kicker, the legal/
 * GitHub links, the context-aware "Corregir" button (FeedbackContext) and
 * the "DISSENY mm." credit (decision 8 — ships as the handoff describes it).
 */
import { Link } from 'react-router-dom'
import FeedbackButton from '../FeedbackButton'
import { useFeedbackContext } from '../../context/FeedbackContext'

export default function Footer() {
  const { target } = useFeedbackContext()
  return (
    <footer className="rd-foot">
      <div className="rd-foot-inner">
        <span className="rd-kicker">topquaranta.cat · música en català · dades obertes</span>
        <div className="rd-foot-links">
          <Link to="/com-funciona">Com funciona</Link>
          <span aria-hidden="true">·</span>
          <Link to="/legal">Legal</Link>
          <span aria-hidden="true">·</span>
          <a href="https://github.com/Top-Quaranta/TopQuaranta" target="_blank" rel="noopener">GitHub</a>
          {target && (
            <>
              <span aria-hidden="true">·</span>
              <FeedbackButton
                targetType={target.targetType}
                targetPk={target.targetPk}
                targetSlug={target.targetSlug}
                targetLabel={target.targetLabel}
              />
            </>
          )}
          <span aria-hidden="true">·</span>
          <a
            href="https://miquelmatoses.github.io/portfolio/"
            target="_blank"
            rel="noopener"
            className="rd-foot-credit"
            aria-label="Disseny: mm — portfolio de Miquel Matoses"
          >
            <span className="fc-word">disseny</span>{' '}
            <span className="fc-mm">mm</span><span className="fc-dot">.</span>
          </a>
        </div>
      </div>
    </footer>
  )
}
