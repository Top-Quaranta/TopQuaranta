import { LegalPage } from './LegalLayout'

export default function CookiesPage() {
  return (
    <LegalPage
      titol="Política de cookies"
      intro="Llistat complet de cookies que TopQuaranta posa al teu navegador. Cap és de tercers."
    >
      <h2>En clar</h2>
      <p>
        Només fem servir cookies <strong>estrictament necessàries</strong>{' '}
        per fer funcionar el lloc i mantenir la sessió. Cap cookie de
        publicitat, de tracking, de Google, de Meta ni de cap altre
        tercer.
      </p>
      <p>
        Per llei, les cookies estrictament necessàries no requereixen
        consentiment previ (Directiva e-Privacy art. 5.3, excepció
        2). Mostrem un avís informatiu la primera visita perquè ho
        sàpigues; pots tancar-lo i no et tornarà a apareixer.
      </p>

      <h2>Llistat exhaustiu</h2>

      <h3>Cookies de sessió i seguretat (servidor)</h3>
      <ul>
        <li>
          <strong><code>sessionid</code></strong> — manté la sessió
          mentre estàs identificat. Caduca a les 2 setmanes o al
          tancar sessió. HttpOnly, Secure, SameSite=Lax.
        </li>
        <li>
          <strong><code>csrftoken</code></strong> — protecció contra
          atacs CSRF (Cross-Site Request Forgery). Caduca a 1 any.
          Secure, SameSite=Lax.
        </li>
        <li>
          <strong><code>axes_*</code></strong> (django-axes) —
          comptador d'intents fallits de login per protegir el lloc
          d'atacs de força bruta. Vida curta, eliminada en cas
          d'autenticació exitosa.
        </li>
      </ul>

      <h3>localStorage (navegador)</h3>
      <ul>
        <li>
          <strong><code>data-theme</code></strong> i <strong><code>cookie-banner-dismissed</code></strong>{' '}
          — preferències UI desades al teu propi navegador, mai
          enviades al servidor. No són cookies en sentit estricte:
          formen part del localStorage del teu navegador.
        </li>
      </ul>

      <h2>Tercers</h2>
      <p>
        <strong>Cap.</strong> No carreguem scripts d'analytics, ni
        widgets socials que estableixin cookies, ni embeds que
        comparteixin la teva visita amb cap empresa externa. Les
        caràtules d'àlbums es serveixen des dels CDN de Deezer,
        però són imatges estàtiques sense capacitat de tracking.
      </p>

      <h2>Com gestionar-les</h2>
      <p>
        Pots esborrar totes les cookies de TopQuaranta des de la
        configuració del teu navegador en qualsevol moment. Si
        esborres la <code>sessionid</code> mentre estàs identificat,
        et tancarà la sessió.
      </p>
      <p>
        Si bloqueges totes les cookies, no podràs identificar-te al
        lloc però sí que podràs llegir-lo lliurement.
      </p>
    </LegalPage>
  )
}
