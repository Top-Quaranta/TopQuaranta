/**
 * ComFuncionaPage — /com-funciona
 *
 * Public, divulgative page that answers "what is TopQuaranta and why
 * does it work this way?". Sourced from MANIFEST.md and
 * docs/product/definition.md but written in plain Catalan for visitors, not
 * contributors. Lives in-tree (no Markdown round-trip) so it stays
 * within the SPA's design system and doesn't need a CMS.
 *
 * Linked from the global footer (Layout.jsx).
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import MmIcon from '../components/MmIcon'

function Section({ icon, title, children, color = 'var(--color-tq-yellow)' }) {
  return (
    <section className="bg-white text-tq-ink rounded-lg p-6 md:p-7 shadow-md">
      <header className="flex items-center gap-3 mb-3">
        <span
          className="inline-flex items-center justify-center w-10 h-10 rounded-md text-white"
          style={{ backgroundColor: color }}
        >
          <MmIcon name={icon} className="h-5 w-5" />
        </span>
        <h2 className="text-xl md:text-2xl font-bold font-display">{title}</h2>
      </header>
      <div className="text-sm leading-relaxed text-tq-ink/85 space-y-3">
        {children}
      </div>
    </section>
  )
}

export default function ComFuncionaPage() {
  useEffect(() => {
    document.title = 'Com funciona — TopQuaranta'
  }, [])

  return (
    <article className="max-w-3xl mx-auto text-white space-y-6">
      <header className="text-center pb-2">
        <p className="text-[10px] uppercase tracking-widest text-tq-yellow">
          Com funciona
        </p>
        <h1 className="text-3xl md:text-4xl font-bold font-display mt-2">
          La música en català, viva i mesurable
        </h1>
        <p className="text-sm md:text-base text-white/80 mt-3 max-w-2xl mx-auto leading-relaxed">
          Una explicació honesta i directa de què és TopQuaranta, com
          decidim el top setmanal, i què no farem mai.
        </p>
      </header>

      <Section icon="info-circle" title="Què és TopQuaranta">
        <p>
          TopQuaranta és el top setmanal públic de música en llengua
          catalana per als Països Catalans. Cada dissabte publiquem un
          top 40 per territori a partir d'escoltes reals, amb el codi i
          les dades obertes perquè qualsevol pugui revisar-ho.
        </p>
        <p>
          Existim per provar — setmanalment, públicament, mesurablement
          — que la música en català és viva i creix. No és una opinió:
          és una mesura.
        </p>
      </Section>

      <Section icon="icon-ranking" title="Com funciona el top">
        <p>
          Cada nit baixem el nombre d'escoltes recents de cada cançó a
          Last.fm, els acumulem durant la setmana i el dissabte tanquem
          el rànquing. Quatre factors decideixen la posició:
        </p>
        <ol className="list-decimal pl-5 space-y-1.5">
          <li>
            <strong>Quantes escoltes té aquesta setmana</strong> — la
            base. Si una cançó té poques dades, l'extrapolem a partir
            de la seva mitjana de vida perquè no quedi penalitzada.
          </li>
          <li>
            <strong>Quants dies fa que es va publicar</strong> — les
            cançons noves pugen més fàcil; les que ja porten mesos al
            top van perdent pes lentament.
          </li>
          <li>
            <strong>Quantes vegades ja ha estat al top</strong> —
            penalitzem una mica les cançons que ja han ocupat
            posicions altes per donar oportunitat a les noves.
          </li>
          <li>
            <strong>Quantes cançons del mateix àlbum o artista</strong>{' '}
            ja apareixen — perquè un sol disc no monopolitzi el top
            de la setmana.
          </li>
        </ol>
        <p className="text-xs text-tq-ink/60">
          Els coeficients exactes són públics i tenen historial: la
          fórmula d'una setmana qualsevol es pot reproduir avui.
        </p>
      </Section>

      <Section icon="check" title="Què compta com a música en català">
        <p>
          La regla és curta: <strong>la veu principal de la cançó és en
          català</strong>. Qualsevol variant val (oriental, occidental,
          balear, alguerès…). Una paraula o frase en una altra llengua
          no descalifica. Un vers complet en una altra llengua, sí.
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li>Les cançons instrumentals no compten — no hi ha veu a mesurar.</li>
          <li>
            Una versió bilingüe simultània entra només si la versió
            catalana és la principal.
          </li>
          <li>
            Una col·laboració entra si la majoria de la veu és en
            català i el crèdit principal va a un artista en català.
          </li>
          <li>
            La cançó ha d'haver-se publicat en els últims 12 mesos.
          </li>
        </ul>
      </Section>

      <Section icon="user" title="Qui decideix">
        <p>
          Cada artista i cada cançó passa per <strong>revisió humana</strong>{' '}
          abans d'entrar al rànquing. L'equip d'staff llegeix la
          proposta, escolta la mostra i pren la decisió, que queda
          registrada al log d'auditoria.
        </p>
        <p>
          Tenim un model de classificació automàtica que prioritza la
          cua de revisió (què mirem primer), però <strong>mai
          decideix sol</strong>. Acelera el treball, no el substitueix.
          Cada decisió té un humà al darrere.
        </p>
      </Section>

      <Section icon="close" title="El que no farem mai" color="var(--color-tq-ink)">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>
            <strong>Vendre les dades del rànquing</strong> a discogràfiques,
            plataformes o tercers. Per això són CC BY: per evitar que
            ningú —incloent nosaltres— pugui construir un peatge al
            voltant.
          </li>
          <li>
            <strong>Acceptar diners per moure una cançó al top.</strong> La
            mesura és el producte. Si la mesura es compromet, el projecte
            no val res.
          </li>
          <li>
            <strong>Filtrar per qualitat artística.</strong> Si la cançó és
            en català, hi entra; el judici sobre què és "bona música"
            no ens correspon.
          </li>
          <li>
            <strong>Vigilància d'usuaris.</strong> No fem tracking, no hi ha
            píxels de tercers, no compartim logs amb ningú llevat d'una
            obligació legal.
          </li>
          <li>
            <strong>Canvis sobtats d'algorisme.</strong> Cada modificació
            queda registrada amb data, motiu i actor; els tops antics es
            poden reproduir amb la fórmula vigent en el moment.
          </li>
        </ul>
      </Section>

      <Section icon="icon-contribuir" title="Com participar">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>
            <strong>Proposa un artista</strong> que falti des del teu
            compte.{' '}
            <Link to="/compte" className="text-tq-ink underline hover:text-tq-yellow-deep">
              Anar al compte
            </Link>
          </li>
          <li>
            <strong>Demana la gestió</strong> del teu propi projecte si
            ja hi és, i actualitza biografia, gènere i xarxes
            directament.
          </li>
          <li>
            <strong>Activa el teu perfil al directori</strong> per
            connectar amb altres músics i col·laboradors.
          </li>
          <li>
            <strong>Corregeix una errada</strong> amb el botó "Corregir"
            present a cada pàgina d'artista, àlbum i cançó.
          </li>
          <li>
            <strong>Reporta un bug o proposa una millora</strong> al{' '}
            <a
              href="https://github.com/miquelmatoses/TopQuaranta"
              target="_blank"
              rel="noopener"
              className="text-tq-ink underline hover:text-tq-yellow-deep"
            >
              repositori de GitHub
            </a>.
          </li>
        </ul>
      </Section>

      <p className="text-center text-xs text-white/60 italic pt-2">
        «La música en català, viva i mesurable.»
      </p>
    </article>
  )
}
