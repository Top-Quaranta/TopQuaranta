import { LegalPage } from './LegalLayout'

export default function CodiConductaPage() {
  return (
    <LegalPage
      titol="Codi de conducta"
      intro="Què esperem de tu i d'altres usuaris a la comunitat. I com retirem contingut quan calgui."
    >
      <h2>L'esperit</h2>
      <p>
        TopQuaranta és un espai per a gent que estima la música en
        català. Tracta'ls com voldries que et tractessin: amb
        respecte, sense judicis a les persones, sense agressivitat,
        sense pressuposar coses que no sabem.
      </p>

      <h2>Què està prohibit</h2>
      <ul>
        <li>
          <strong>Discurs d'odi</strong>: insults i amenaces basades
          en orígen, ètnia, religió, gènere, orientació sexual,
          identitat de gènere, discapacitat o qualsevol condició
          personal.
        </li>
        <li>
          <strong>Assetjament</strong>: missatges repetits no desitjats,
          intimidació, doxxing (revelar dades personals d'algú sense
          el seu consentiment).
        </li>
        <li>
          <strong>Contingut sexual</strong> explícit o que involucri
          menors.
        </li>
        <li>
          <strong>Promoció de violència</strong> o autolesió.
        </li>
        <li>
          <strong>Spam i estafes</strong>: enllaços a esquemes
          piramidals, contingut comercial no sol·licitat, missatges
          massius idèntics.
        </li>
        <li>
          <strong>Suplantació</strong> d'un altre artista, persona o
          entitat.
        </li>
        <li>
          <strong>Vulneració de drets d'autor</strong> de tercers.
        </li>
        <li>
          <strong>Activitat il·legal</strong>: publicació de material
          il·lícit sota el dret danès o de la UE.
        </li>
      </ul>

      <h2>Com reportar contingut</h2>
      <p>
        Si veus alguna cosa que infringeix aquestes regles:
      </p>
      <ul>
        <li>
          A les pàgines d'artista, àlbum i cançó: botó <strong>"Corregir"</strong>{' '}
          al peu de la pàgina.
        </li>
        <li>
          A publicacions, comentaris i missatges directes: escriu-nos
          a <a href="mailto:info@topquaranta.cat">info@topquaranta.cat</a>{' '}
          amb un enllaç al contingut i una breu explicació.
        </li>
      </ul>

      <h2>Procés de retirada</h2>
      <ol>
        <li>
          Rebem el report i el revisem dins els 7 dies feiners
          següents.
        </li>
        <li>
          Si el contingut infringeix el codi, el retirem i avisem
          l'autor pel motiu. Si és contingut clarament il·legal, el
          retirem immediatament i, si la llei ho exigeix, ho
          comuniquem a les autoritats.
        </li>
        <li>
          Cada retirada queda registrada al log d'auditoria intern.
        </li>
      </ol>

      <h2>Apel·lacions</h2>
      <p>
        Si creus que t'hem retirat contingut injustament, escriu-nos
        a <a href="mailto:info@topquaranta.cat">info@topquaranta.cat</a>{' '}
        explicant per què. Tornarem a revisar-ho i et respondrem dins
        els 7 dies següents.
      </p>

      <h2>Sancions</h2>
      <p>
        Per infraccions lleus retirem el contingut i avisem. Per
        infraccions greus o repetides podem suspendre o tancar el
        compte. Vegeu els{' '}
        <a href="/legal/termes">termes d'ús</a> per al detall.
      </p>
    </LegalPage>
  )
}
