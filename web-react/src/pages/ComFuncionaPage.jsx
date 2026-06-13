/**
 * ComFuncionaPage — /com-funciona (redisseny web).
 *
 * Divulgative page: what TopQuaranta is, how the weekly top is decided,
 * and what we'll never do. The TEXT is the real content (kept verbatim
 * except the product vocabulary veto — "el top", never the R-word);
 * restyled as a stack of glass cards on dark, max 820px, closing on the
 * centred italic quote.
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Band, Glow, Glass, Kicker, Crit } from '../components/rd/primitives'

function CfCard({ kicker, title, children }) {
  return (
    <Glass className="rd-cf-card">
      {kicker && <Kicker color="var(--color-tq-yellow)">{kicker}</Kicker>}
      <Crit as="h2" className="rd-cf-title">{title}</Crit>
      <div className="rd-prose">{children}</div>
    </Glass>
  )
}

export default function ComFuncionaPage() {
  useEffect(() => { document.title = 'Com funciona — TopQuaranta' }, [])

  return (
    <>
      <Band tone="top-hero">
        <Glow variant="a" />
        <div className="max-w-3xl">
          <Kicker className="block mb-2">transparència algorítmica</Kicker>
          <Crit as="h1" className="rd-top-h1">COM <span style={{ color: 'var(--color-tq-yellow)' }}>FUNCIONA</span></Crit>
          <p className="rd-hero-sub">
            Una explicació honesta i directa de què és TopQuaranta, com decidim
            el top setmanal, i què no farem mai.
          </p>
        </div>
      </Band>

      <Band tone="ink2">
        <div className="rd-cf-stack">
          <CfCard kicker="el projecte" title="QUÈ ÉS TOPQUARANTA">
            <p>
              TopQuaranta és el top setmanal públic de música en llengua catalana
              per als Països Catalans. Cada dissabte publiquem un top 40 per
              territori a partir d'escoltes reals, amb el codi i les dades obertes
              perquè qualsevol pugui revisar-ho.
            </p>
            <p>
              Existim per provar — setmanalment, públicament, mesurablement — que
              la música en català és viva i creix. No és una opinió: és una mesura.
            </p>
          </CfCard>

          <CfCard kicker="el mètode" title="COM ES DECIDEIX EL TOP">
            <p>
              Cada nit baixem el nombre d'escoltes recents de cada cançó a Last.fm,
              els acumulem durant la setmana i el dissabte tanquem el top. Cinc
              coses decideixen la posició:
            </p>
            <ol className="rd-cf-factors">
              <li><span className="rd-cf-fnum">1</span><p><strong>Quantes escoltes té aquesta setmana</strong> — la base. Si una cançó té poques dades, l'extrapolem a partir de la seva mitjana de vida perquè no quedi penalitzada.</p></li>
              <li><span className="rd-cf-fnum">2</span><p><strong>Quants dies fa que es va publicar</strong> — les cançons noves pugen més fàcil; les que ja porten mesos al top van perdent pes lentament.</p></li>
              <li><span className="rd-cf-fnum">3</span><p><strong>Quantes vegades ja ha estat al top</strong> — penalitzem una mica les cançons que ja han ocupat posicions altes per donar oportunitat a les noves.</p></li>
              <li><span className="rd-cf-fnum">4</span><p><strong>Quantes cançons del mateix àlbum o artista</strong> ja apareixen — perquè un sol disc no monopolitzi el top de la setmana.</p></li>
              <li><span className="rd-cf-fnum">5</span><p><strong>Un sostre suau per als pics</strong> — si una cançó té moltíssimes més escoltes que el que és habitual al seu territori (sovint un artista molt comercial), en comprimim l'excés perquè no aixafe la resta. Cada territori té el seu propi llindar i les cançons amb xifres normals no es toquen.</p></li>
            </ol>
            <p className="rd-cf-fine">
              Els coeficients exactes són públics i tenen historial: la fórmula
              d'una setmana qualsevol es pot reproduir avui.
            </p>
          </CfCard>

          <CfCard kicker="la regla" title="QUÈ COMPTA COM A CATALÀ">
            <p>
              La regla és curta: <strong>la veu principal de la cançó és en
              català</strong>. Qualsevol variant val (oriental, occidental, balear,
              alguerès…). Una paraula o frase en una altra llengua no descalifica.
              Un vers complet en una altra llengua, sí.
            </p>
            <ul className="rd-cf-list">
              <li>Les cançons instrumentals no compten — no hi ha veu a mesurar.</li>
              <li>Una versió bilingüe simultània entra només si la versió catalana és la principal.</li>
              <li>Una col·laboració entra si la majoria de la veu és en català i el crèdit principal va a un artista en català.</li>
              <li>La cançó ha d'haver-se publicat en els últims 12 mesos.</li>
            </ul>
          </CfCard>

          <CfCard kicker="qui mana" title="QUI DECIDEIX">
            <p>
              Cada artista i cada cançó passa per <strong>revisió humana</strong>
              {' '}abans d'entrar al top. L'equip d'staff llegeix la proposta,
              escolta la mostra i pren la decisió, que queda registrada al log
              d'auditoria.
            </p>
            <p>
              Tenim un model de classificació automàtica que prioritza la cua de
              revisió (què mirem primer), però <strong>mai decideix sol</strong>.
              Accelera el treball, no el substitueix. Cada decisió té un humà al
              darrere.
            </p>
          </CfCard>

          <CfCard kicker="els límits" title="EL QUE NO FAREM MAI">
            <ul className="rd-cf-list">
              <li><strong>Vendre les dades del top</strong> a discogràfiques, plataformes o tercers. Per això són CC BY: per evitar que ningú —incloent nosaltres— pugui construir un peatge al voltant.</li>
              <li><strong>Acceptar diners per moure una cançó al top.</strong> La mesura és el producte. Si la mesura es compromet, el projecte no val res.</li>
              <li><strong>Filtrar per qualitat artística.</strong> Si la cançó és en català, hi entra; el judici sobre què és «bona música» no ens correspon.</li>
              <li><strong>Vigilància d'usuaris.</strong> No fem tracking, no hi ha píxels de tercers, no compartim logs amb ningú llevat d'una obligació legal.</li>
              <li><strong>Canvis sobtats d'algorisme.</strong> Cada modificació queda registrada amb data, motiu i actor; els tops antics es poden reproduir amb la fórmula vigent en el moment.</li>
            </ul>
          </CfCard>

          <CfCard kicker="com participar" title="POSA-HI LA TEUA PART">
            <ul className="rd-cf-list">
              <li><strong>Proposa un artista</strong> que falti des del teu compte. <Link to="/compte" className="rd-prose-link">Anar al compte</Link></li>
              <li><strong>Demana la gestió</strong> del teu propi projecte si ja hi és, i actualitza biografia, gènere i xarxes directament.</li>
              <li><strong>Activa el teu perfil al directori</strong> per connectar amb altres músics i col·laboradors.</li>
              <li><strong>Corregeix una errada</strong> amb el botó «Corregir» present a cada pàgina d'artista, àlbum i cançó.</li>
              <li><strong>Reporta un bug o proposa una millora</strong> al <a href="https://github.com/Top-Quaranta/TopQuaranta" target="_blank" rel="noopener" className="rd-prose-link">repositori de GitHub</a>.</li>
            </ul>
          </CfCard>

          <p className="rd-cf-quote">«La música en català, viva i mesurable.»</p>
        </div>
      </Band>
    </>
  )
}
