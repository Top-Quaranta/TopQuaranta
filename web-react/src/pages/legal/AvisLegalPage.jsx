import { LegalPage } from './LegalLayout'

export default function AvisLegalPage() {
  return (
    <LegalPage
      titol="Avís legal"
      intro="Qui hi ha darrere de TopQuaranta i com contactar-nos."
    >
      <h2>Titular del lloc</h2>
      <p>
        TopQuaranta està gestionat per una entitat registrada a Dinamarca
        amb número de registre <strong>CVR 46414683</strong>.
      </p>
      <p>
        Domicili registrat al registre fiscal danès. No el publiquem
        aquí: per a notificacions formals, fes-nos arribar la sol·licitud
        per correu i et farem arribar les dades concretes.
      </p>

      <h2>Contacte</h2>
      <p>
        Per a qualsevol comunicació, escriu-nos a:{' '}
        <a href="mailto:info@topquaranta.cat">info@topquaranta.cat</a>.
      </p>

      <h2>Naturalesa del projecte</h2>
      <p>
        TopQuaranta és un projecte cultural sense ànim de lucre que
        publica un top setmanal de música en català mesurat a partir
        d'escoltes públiques de Last.fm. No venem cap producte ni
        servei. No fem publicitat de tercers.
      </p>

      <h2>Marc legal</h2>
      <p>
        L'activitat de TopQuaranta està subjecta a la legislació danesa
        i a la normativa europea aplicable: Reglament (UE) 2016/679
        (RGPD), Directiva 2002/58/CE (e-Privacy), Reglament (UE)
        2022/2065 (Digital Services Act). Els usuaris consumidors
        residents a la UE conserven els drets imperatius del seu país
        de residència.
      </p>

      <h2>Allotjament</h2>
      <p>
        El servidor que serveix la web és de Hetzner Online GmbH
        (Alemanya). El correu surt a través de cdmon (Espanya). Cap
        dada surt de l'Espai Econòmic Europeu.
      </p>
    </LegalPage>
  )
}
