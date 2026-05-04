import { LegalPage } from './LegalLayout'

export default function LlicenciesPage() {
  return (
    <LegalPage
      titol="Llicències i propietat intel·lectual"
      intro="Què hi ha d'obert i què hi ha de tercers a TopQuaranta."
    >
      <h2>El codi de TopQuaranta</h2>
      <p>
        El codi font de TopQuaranta es publica sota la llicència{' '}
        <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noopener">
          GNU Affero General Public License v3.0 (AGPL-3.0)
        </a>. Repositori:{' '}
        <a href="https://github.com/Top-Quaranta/TopQuaranta" target="_blank" rel="noopener">
          github.com/Top-Quaranta/TopQuaranta
        </a>.
      </p>

      <h2>Les dades del rànquing</h2>
      <p>
        Els rànquings setmanals i les mètriques publicades es lliuren
        sota la llicència{' '}
        <a href="https://creativecommons.org/licenses/by/4.0/deed.ca" target="_blank" rel="noopener">
          Creative Commons Attribution 4.0 International (CC BY 4.0)
        </a>. Pots reusar-les, redistribuir-les i adaptar-les
        gratuïtament, fins i tot per a fins comercials, amb un únic
        requeriment: <strong>citar-nos com a font</strong> (e.g.
        "Font: TopQuaranta, CC BY 4.0").
      </p>
      <p>
        Detall complet: vegeu <code>LICENSE-DATA.md</code> al
        repositori.
      </p>

      <h2>El contingut que publiques</h2>
      <p>
        El contingut que pubiques al lloc (publicacions, comentaris,
        missatges, biografies dels artistes que gestiones, propostes,
        correccions) és teu. Mantens els drets d'autor.
      </p>
      <p>
        En publicar-lo, ens dónes una <strong>llicència no
        exclusiva, gratuïta i mundial</strong> per a allotjar-lo,
        servir-lo als usuaris destinataris i moderar-lo en el marc
        del servei. La llicència decau quan retires el contingut o
        esborres el compte.
      </p>

      <h2>Material de tercers</h2>
      <p>
        TopQuaranta consumeix dades públiques de:
      </p>
      <ul>
        <li>
          <strong>Last.fm</strong> — estadístiques d'escolta
          (playcounts, listeners). API pública oberta a usos no
          comercials.
        </li>
        <li>
          <strong>Deezer</strong> — metadades d'àlbums, ISRC, links
          a previews i caràtules. Les caràtules s'embeben directament
          des dels CDN de Deezer (no n'allotgem cap al nostre
          servidor).
        </li>
        <li>
          <strong>MusicBrainz</strong> — MBID, dates de vida,
          discografia, idioma de lletres. Dades sota CC0/CC BY.
        </li>
      </ul>
      <p>
        Si ets titular dels drets d'algun material referenciat al
        lloc i creus que cal retirar-lo, escriu-nos a{' '}
        <a href="mailto:info@topquaranta.cat">info@topquaranta.cat</a>{' '}
        amb la URL i el detall i actuarem dins els 7 dies feiners.
      </p>

      <h2>La marca i el logotip TopQuaranta</h2>
      <p>
        El nom "TopQuaranta", el logotip i la identitat visual són
        marca del projecte. No estan coberts per la llicència del
        codi ni la de les dades. Pots citar-nos lliurement; per a
        usos del logotip o de la marca en altres contextos,
        contacta'ns abans.
      </p>

      <h2>Marc DSA — notificació de continguts il·lícits</h2>
      <p>
        D'acord amb el Reglament UE 2022/2065 (Digital Services Act),
        si trobes contingut que considera il·lícit pots notificar-nos-el
        a <a href="mailto:info@topquaranta.cat">info@topquaranta.cat</a>{' '}
        amb (a) la URL exacta, (b) una explicació del motiu pel qual
        consideres que és il·lícit, (c) la teva identitat o un mitjà
        per contactar-te. El revisarem dins els 7 dies feiners
        següents i et notificarem la decisió.
      </p>
    </LegalPage>
  )
}
