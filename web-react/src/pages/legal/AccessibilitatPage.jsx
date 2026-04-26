import { LegalPage } from './LegalLayout'

export default function AccessibilitatPage() {
  return (
    <LegalPage
      titol="Accessibilitat"
      intro="Compromís d'accessibilitat de TopQuaranta i com reportar barreres."
    >
      <h2>Estat actual</h2>
      <p>
        TopQuaranta està desenvolupat per complir el nivell{' '}
        <strong>WCAG 2.1 AA</strong>. No n'estem obligats per llei
        (no som una entitat del sector públic), però el considerem
        un requisit del propi projecte cultural: si la mesura és
        pública, l'accés a la mesura també ho ha de ser.
      </p>

      <h2>Què fem activament</h2>
      <ul>
        <li>
          <strong>Auditoria automàtica</strong> amb axe-core (Deque
          Systems) després de cada canvi visual significatiu, sobre
          totes les pàgines públiques. La barra d'acceptació interna
          és <strong>0 violacions</strong>.
        </li>
        <li>
          <strong>Contrast de color</strong> verificat ≥ 4.5:1 per a
          text normal i ≥ 3:1 per a text gran i elements UI. Els
          colors de marca usats sobre blanc passen tots els
          llindars.
        </li>
        <li>
          <strong>Navegació per teclat</strong> — tot el lloc és
          operable sense ratolí. "Skip to content" disponible com a
          primer focus a cada pàgina.
        </li>
        <li>
          <strong>Estructura semàntica</strong> — landmarks ARIA
          correctes (header, main, nav, footer), jerarquia coherent
          d'encapçalaments, formularis amb labels associats.
        </li>
        <li>
          <strong>Imatges</strong> amb <code>alt</code> apropiat;
          imatges decoratives marcades amb <code>alt=""</code> o
          <code>aria-hidden</code>.
        </li>
        <li>
          <strong>Indicador de focus visible</strong> a cada element
          interactiu, dissenyat amb prou contrast.
        </li>
      </ul>

      <h2>Límits coneguts</h2>
      <p>
        El mapa interactiu (<code>/mapa</code>) és principalment
        visual. La informació equivalent està disponible a la pàgina
        d'<a href="/artistes">artistes</a> amb filtres per territori,
        comarca i municipi.
      </p>

      <h2>Reporta una barrera</h2>
      <p>
        Si has trobat un punt que no és accessible amb una tecnologia
        d'assistència o no compleix WCAG AA, escriu-nos a{' '}
        <a href="mailto:info@topquaranta.cat">info@topquaranta.cat</a>{' '}
        explicant la pàgina, el problema i la teva configuració. Hi
        donarem prioritat.
      </p>
    </LegalPage>
  )
}
