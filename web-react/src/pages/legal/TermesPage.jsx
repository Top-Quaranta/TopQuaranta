import { LegalPage } from './LegalLayout'

export default function TermesPage() {
  return (
    <LegalPage
      titol="Termes i condicions d'ús"
      intro="Les regles del joc del lloc i del compte d'usuari."
    >
      <h2>Què és el servei</h2>
      <p>
        TopQuaranta publica un top setmanal de música en català per als
        Països Catalans, calculat a partir d'escoltes públiques de
        Last.fm i metadades de Deezer i MusicBrainz. El lloc és
        gratuït, no té anuncis i no requereix registre per a llegir-lo.
      </p>
      <p>
        El registre dóna accés a funcions addicionals: proposar i
        gestionar artistes, participar al directori de la comunitat,
        publicar al feed, comentar i enviar missatges directes.
      </p>

      <h2>Edat mínima</h2>
      <p>
        Per crear compte cal tenir <strong>14 anys o més</strong>. Si
        ets menor, no creïs compte; si volies només llegir, pots
        fer-ho lliurement sense registre.
      </p>

      <h2>Compromisos teus</h2>
      <ul>
        <li>
          La informació que dones (correu, perfil, propostes) és
          veraç i no suplanta cap altra persona.
        </li>
        <li>
          Mantens la confidencialitat de la teva contrasenya. Ens
          avises si sospites que algú ha accedit al teu compte.
        </li>
        <li>
          Respectes el <a href="/legal/codi-conducta">codi de conducta</a> a
          les publicacions, comentaris i missatges.
        </li>
        <li>
          No fas servir el lloc per fer spam, distribuir programari
          maliciós, o vulnerar la propietat intel·lectual de tercers.
        </li>
      </ul>

      <h2>Compromisos nostres</h2>
      <ul>
        <li>
          Mantenir el servei disponible amb la millor diligència
          raonable per a un projecte cultural petit. No prometem un
          uptime concret ni garantim absència de bugs.
        </li>
        <li>
          Comunicar-te canvis materials als termes o a la política de
          privacitat per correu i amb un avís a la pàgina abans que
          siguin efectius.
        </li>
        <li>
          Tractar les teves dades segons la{' '}
          <a href="/legal/privacitat">política de privacitat</a>.
        </li>
        <li>
          Mai vendre les teves dades, mai posar publicitat de tercers,
          mai usar el teu compte per a finalitats que no t'haguem
          explicat. Vegeu el <a href="/">manifest</a> per al detall del
          que no farem mai.
        </li>
      </ul>

      <h2>Contingut que publiques</h2>
      <p>
        Mantens els drets d'autor del que publiques (publicacions,
        comentaris, missatges, biografies, propostes, correccions).
        En publicar-ho, ens dónes una <strong>llicència no
        exclusiva, gratuïta i mundial</strong> per a allotjar-ho,
        servir-lo als usuaris destinataris i moderar-lo. La llicència
        decau quan retires el contingut o esborres el compte.
      </p>
      <p>
        Si publiques contingut que infringeix drets de tercers o el
        codi de conducta, podem retirar-lo. Si ho fem repetidament,
        podem suspendre el teu compte.
      </p>

      <h2>Suspensió i tancament</h2>
      <ul>
        <li>
          <strong>Tu pots tancar el compte</strong> en qualsevol
          moment des del teu compte, amb confirmació per email.
        </li>
        <li>
          <strong>Nosaltres podem suspendre o tancar un compte</strong>{' '}
          si infringeix repetidament els termes o el codi de conducta,
          o si rebem una ordre legal vinculant. Et notificarem
          l'acció i el motiu per correu, llevat que la notificació
          mateixa estigui prohibida per la mateixa ordre.
        </li>
      </ul>

      <h2>Limitació de responsabilitat</h2>
      <p>
        El servei es presta tal com és. No som responsables de:
      </p>
      <ul>
        <li>
          Errors o inexactituds als rànquings causats per dades
          incorrectes a Last.fm, Deezer o MusicBrainz (corregibles
          via el botó "Corregir" de cada pàgina).
        </li>
        <li>
          Pèrdues indirectes derivades d'una indisponibilitat puntual
          del servei.
        </li>
        <li>
          Contingut publicat per altres usuaris.
        </li>
      </ul>
      <p>
        Aquesta limitació no afecta les responsabilitats imperatives
        per a consumidors recollides al país de residència de l'usuari
        a la UE.
      </p>

      <h2>Llei aplicable i jurisdicció</h2>
      <p>
        Aquests termes es regeixen pel <strong>dret danès</strong>{' '}
        (TopQuaranta està registrat a Dinamarca, CVR 46414683). Les
        controvèrsies se sotmetran als tribunals competents de
        Dinamarca.
      </p>
      <p>
        Si ets consumidor i resideixes a un altre país de la UE, els
        teus drets imperatius com a consumidor (incloent el dret a
        litigar al teu país de residència sota el Reglament Brussel·les
        Ia art. 17–19) no es veuen afectats per aquesta clàusula.
      </p>

      <h2>Canvis a aquests termes</h2>
      <p>
        Si modifiquem materialment aquests termes, et demanarem una
        nova acceptació la propera vegada que entris al teu compte.
        Per a canvis menors (typos, aclariments) actualitzem la data al
        capdamunt sense demanar nova acceptació.
      </p>

      <h2>Contacte</h2>
      <p>
        Per a qualsevol qüestió:{' '}
        <a href="mailto:info@topquaranta.cat">info@topquaranta.cat</a>.
      </p>
    </LegalPage>
  )
}
