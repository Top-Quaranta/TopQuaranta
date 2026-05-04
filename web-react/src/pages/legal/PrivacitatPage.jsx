import { LegalPage } from './LegalLayout'

export default function PrivacitatPage() {
  return (
    <LegalPage
      titol="Política de privacitat"
      intro="Quines dades teves guardem, per què, fins quan, i com pots exercir els teus drets."
    >
      <h2>En clar</h2>
      <p>
        TopQuaranta no fa tracking. No hi ha Google Analytics, ni
        píxels de Meta, ni cap altre script de tercers que t'observi.
        Si visites el lloc sense crear compte, no sabem qui ets.
      </p>
      <p>
        Sí que tenim mètriques agregades pròpies per a entendre què
        funciona i què no (quantes visites rep cada pàgina, quants
        registres es completen, quins enllaços a xarxes socials
        funcionen…), però són <strong>només números, mai dades
        individuals</strong>. Vegeu la secció «Mètriques agregades»
        més avall per al detall complet.
      </p>
      <p>
        Si crees un compte, guardem just el necessari perquè el servei
        funcioni: el teu correu, una contrasenya xifrada, el teu
        perfil públic (si l'omples), les propostes i correccions que
        envies, i el contingut que publiques a la comunitat.
      </p>

      <h2>Responsable del tractament</h2>
      <p>
        TopQuaranta · CVR 46414683 (Dinamarca) ·{' '}
        <a href="mailto:info@topquaranta.cat">info@topquaranta.cat</a>.
        Per al volum d'activitat actual no estem obligats a designar
        un Delegat de Protecció de Dades; les sol·licituds RGPD les
        atén el mateix equip a través del correu de contacte.
      </p>

      <h2>Quines dades guardem</h2>
      <h3>Per a tots els visitants (inclosos no registrats)</h3>
      <ul>
        <li>
          <strong>Logs d'accés del servidor</strong>: IP, user-agent,
          URL i moment, conservats 30 dies per a diagnòstic i seguretat.
          No es comparteixen amb ningú.
        </li>
        <li>
          <strong>Cookies funcionals</strong>: vegeu la{' '}
          <a href="/legal/cookies">política de cookies</a>.
        </li>
      </ul>

      <h3>Per a usuaris registrats</h3>
      <ul>
        <li><strong>Correu electrònic</strong> (identificador de compte).</li>
        <li><strong>Contrasenya</strong>, xifrada amb Argon2 — mai la veiem.</li>
        <li>
          <strong>Perfil de comunitat</strong>: nom públic, biografia,
          rol musical, instruments, localitat, imatge, xarxes socials,
          i si vols ser visible al directori. Tot opcional excepte el
          nom públic.
        </li>
        <li>
          <strong>Activitat al sistema</strong>: propostes d'artistes,
          sol·licituds de gestió, correccions enviades, publicacions a
          la comunitat, comentaris, missatges directes.
        </li>
        <li>
          <strong>Consentiments</strong>: registrem quan vas acceptar
          els termes i si vas activar la newsletter, amb data i versió
          dels documents. Això és per poder demostrar el consentiment
          si fos requerit per una autoritat.
        </li>
        <li>
          <strong>Esdeveniments de seguretat</strong>: intents fallits
          de login (django-axes), conservats 6 mesos.
        </li>
      </ul>

      <h2>Mètriques agregades</h2>
      <p>
        Per a poder millorar el servei sense espiar ningú, comptem
        esdeveniments anònims agregats per dia. Concretament:
      </p>
      <ul>
        <li>
          <strong>Pageviews per ruta</strong> — quantes vegades s'ha
          visitat cada pàgina pública (p. ex. <code>/top</code>,
          <code>/artistes</code>). No registrem qui l'ha visitada,
          ni la IP, ni el navegador, ni la pàgina d'origen.
        </li>
        <li>
          <strong>UTM landings</strong> — si arribes amb un enllaç
          marcat (per exemple des d'un post nostre a Mastodon),
          comptem la combinació (font, campanya). Així sabem si la
          newsletter porta més gent que Telegram. No es vincula a
          cap visitant concret.
        </li>
        <li>
          <strong>Esdeveniments del producte</strong> — comptadors
          tipus «registre completat», «proposta enviada»,
          «feedback enviat», «clic a Spotify/Deezer/YouTube». Tot
          en agregat, sense identificadors d'usuari.
        </li>
        <li>
          <strong>Estat del catàleg</strong> — instantànies diàries
          dels totals (cançons verificades, artistes aprovats,
          cobertura de metadades…). Són dades del sistema, no
          relacionades amb cap visitant.
        </li>
        <li>
          <strong>Mètriques de les nostres xarxes socials</strong> —
          els nostres comptes a Instagram, Mastodon, Bluesky i
          Telegram exposen comptadors públics (followers, likes,
          reaccions a cada post). Els recollim diàriament per a
          gràfiques internes; són dades dels nostres comptes, no
          dels nostres seguidors.
        </li>
      </ul>
      <p>
        Cap d'aquestes mètriques s'envia a tercers, ni s'utilitza
        per identificar-te ni per oferir-te publicitat. Cap script
        de tracking corre al teu navegador. Tot el codi és obert i
        es pot auditar al nostre repositori públic.
      </p>

      <h2>Per a què les fem servir</h2>
      <ul>
        <li>Donar accés al teu compte i mantenir la sessió.</li>
        <li>
          Mostrar el teu perfil al directori (només si has marcat
          "vull aparèixer al directori").
        </li>
        <li>
          Permetre que envïïs missatges a altres usuaris i que en rebis.
        </li>
        <li>
          Notificar-te per correu d'esdeveniments rellevants (missatge
          rebut, comentari nou, decisió sobre proposta). Pots desactivar
          aquestes notificacions des del teu perfil.
        </li>
        <li>
          Donar visibilitat a la teva proposta d'artista o correcció
          dins el panell intern d'staff.
        </li>
      </ul>

      <h2>Base legal</h2>
      <p>
        El tractament de les dades del compte té com a base legal
        l'<strong>execució del servei</strong> que has demanat (RGPD
        art. 6.1.b). El tractament d'esdeveniments de seguretat i
        logs té com a base l'<strong>interès legítim</strong> en la
        seguretat del sistema (art. 6.1.f). La newsletter, si t'hi
        subscrius, té com a base el teu <strong>consentiment</strong>{' '}
        explícit (art. 6.1.a + Directiva e-Privacy art. 13).
      </p>

      <h2>Decisions automatitzades</h2>
      <p>
        Tenim un model de classificació automàtica que pre-prioritza
        la cua de cançons noves a revisar (decideix què mira primer
        l'staff humà). El model <strong>no decideix sol</strong> sobre
        cap usuari ni sobre cap propietat dels usuaris: cada decisió
        d'aprovació o rebuig la pren una persona. Per tant, l'article
        22 del RGPD (decisions automatitzades amb efectes jurídics) no
        s'aplica.
      </p>

      <h2>Edat mínima</h2>
      <p>
        Per crear compte cal tenir 14 anys o més. Si descobrim un
        compte d'una persona menor de 14 anys, el desactivem i
        n'esborrem les dades.
      </p>

      <h2>Quant temps les guardem</h2>
      <ul>
        <li><strong>Dades del compte</strong>: mentre el compte estigui actiu.</li>
        <li>
          <strong>Si esborres el compte</strong>: eliminem les dades
          personals immediatament. Conservem només l'historial
          anonimitzat de les decisions staff que vas prendre (si eres
          staff) per a integritat de l'auditoria.
        </li>
        <li><strong>Logs de servidor</strong>: 30 dies.</li>
        <li><strong>Logs de seguretat (django-axes)</strong>: 6 mesos.</li>
        <li><strong>Subscripció a la newsletter</strong>: fins que et donis de baixa + 1 any per a justificar enviaments si calgués.</li>
      </ul>

      <h2>Amb qui les compartim</h2>
      <p>
        Només amb els proveïdors estrictament necessaris per fer
        funcionar el servei:
      </p>
      <ul>
        <li>
          <strong>Hetzner Online GmbH</strong> (Alemanya) — allotjament
          del servidor. Encarregat de tractament; cap accés a les dades
          aplicatives.
        </li>
        <li>
          <strong>cdmon</strong> (Espanya) — proveïdor de correu
          electrònic per als emails que t'enviem (verificació, baixa
          de compte, notificacions).
        </li>
      </ul>
      <p>
        Cap dada surt de l'Espai Econòmic Europeu. No venem dades
        a tercers, no les compartim amb anunciants, no les fem servir
        per perfilar-te per a publicitat.
      </p>

      <h2>Els teus drets</h2>
      <ul>
        <li>
          <strong>Accés</strong> — pots demanar una còpia de tot el
          que sabem de tu. Des del teu compte tens el botó "Exportar
          les meves dades" que t'envia un JSON complet per correu.
        </li>
        <li>
          <strong>Rectificació</strong> — pots editar el teu perfil i
          el teu correu en qualsevol moment.
        </li>
        <li>
          <strong>Supressió</strong> — pots esborrar el teu compte
          des del teu compte amb confirmació per email.
        </li>
        <li>
          <strong>Oposició i limitació</strong> — escriu-nos a{' '}
          <a href="mailto:info@topquaranta.cat">info@topquaranta.cat</a>.
        </li>
        <li>
          <strong>Portabilitat</strong> — l'exportació t'arriba en
          format JSON estàndard.
        </li>
        <li>
          <strong>Retirar el consentiment</strong> de la newsletter en
          qualsevol moment des del teu perfil o amb el link de baixa
          de cada email.
        </li>
      </ul>

      <h2>Reclamacions</h2>
      <p>
        Si creus que no estem tractant les teves dades correctament i
        no n'estàs satisfet de la nostra resposta, pots presentar
        reclamació davant l'autoritat de protecció de dades danesa
        (Datatilsynet, autoritat principal): <a href="https://www.datatilsynet.dk/" target="_blank" rel="noopener">datatilsynet.dk</a>.
      </p>
      <p>
        Si vius a Espanya, també pots presentar la reclamació davant
        l'<a href="https://www.aepd.es/" target="_blank" rel="noopener">Agència Espanyola
        de Protecció de Dades (AEPD)</a>; el mecanisme europeu de
        finestreta única coordinarà la teva queixa amb Datatilsynet.
      </p>
    </LegalPage>
  )
}
