# Correu — arquitectura

> Estat 2026-08-18. **Stalwart s'ha retirat**; les bústies viuen a
> Purelymail. Els blocs de DNS, relays d'enviament, BIMI i newsletter
> continuen vigents i no han canviat.

## Resum

| | topquaranta.cat | cercol.team |
|---|---|---|
| Bústies (rebre) | Purelymail | Purelymail |
| MX | `mailserver.purelymail.com` | `mailserver.purelymail.com` |
| Enviament automàtic | Brevo | Resend |
| SPF | `purelymail + brevo` | `purelymail + resend` |

**Els comptes**: IMAP `imap.purelymail.com:993` (SSL) i SMTP
`smtp.purelymail.com:465` (SSL), tots dos amb la **contrasenya de la
bústia**. Una sola contrasenya per a rebre i per a enviar.

**L'enviament automàtic va a part**: la newsletter i els correus
transaccionals surten de Django per Brevo, i els de Cercol per Resend.
No passen per Purelymail — són volums i necessitats distintes (plantilles,
mètriques d'obertura, llistes de baixa), i per això els SPF inclouen les
dues fonts.

## Per què les bústies ja no són nostres

Van estar a **Stalwart Mail Server**, a la mateixa caixa de Hetzner, des
de l'abril del 2026 fins al 18 d'agost. El motiu de retirar-ho és el de
sempre amb els serveis autoallotjats: el cost d'operar-lo no era el
disc ni la CPU, sinó **estar-hi a sobre**. Dos exemples reals del temps
que va durar:

- El certificat TLS. Caddy el renovava i una unitat `systemd path` el
  copiava a `/etc/stalwart/certs/`, però Stalwart no el rellegia: el 26
  de juliol servia encara el d'abril, caducat, amb el bo al disc des de
  feia un mes. Post-mortem a
  [`post-mortems/2026-07-26-stalwart-cert-expirat.md`](post-mortems/2026-07-26-stalwart-cert-expirat.md).
- L'enviament. Hetzner bloqueja el port 25 d'eixida, així que Stalwart
  no podia entregar res pel seu compte i calia encaminar-ho tot per un
  smarthost. Eixa restricció **continua sent certa**, i és la raó per la
  qual no es tornarà a allotjar correu en eixa màquina.

Res d'això és culpa de Stalwart. És el preu d'allotjar correu, i el
projecte no en treia cap avantatge que compensara.

## Què queda a la nostra màquina

Només l'**autoconfig** per als clients de correu. `mail.topquaranta.cat`
continua apuntant a la caixa perquè el registre DNS serveix eixe fitxer,
i qualsevol altra petició respon **410** amb els paràmetres de Purelymail.

El fitxer és [`deploy/autoconfig-topquaranta.xml`](../deploy/autoconfig-topquaranta.xml),
i l'instal·la `bin/tq-sync-infra` com qualsevol altre fitxer que viu fora
de l'arbre de treball. Es publica **només** al camí `.well-known` de
`mail.topquaranta.cat`: Thunderbird prova abans
`autoconfig.<domini>`, però eixe subdomini mai no va apuntar ací —resol a
CDMON— i durant quatre mesos els clients ja el trobaven per aquesta via.
El bloc que l'esperava es va llevar el 2026-08-18.

**Va viure només al servidor fins al 2026-08-18, i es va desincronitzar
exactament per això**: en retirar Stalwart es va corregir a mà el servidor
d'entrada i el de d'eixida es va quedar apuntant al relay de Brevo, amb
una clau d'API compartida com a contrasenya —publicada en obert dins de
l'XML—, de manera que qui es configurara la bústia podia rebre i no
enviar. Ara hi ha **una sola còpia** a disc i Caddy reescriu els dos
camins que prova Thunderbird cap a ella; abans n'hi havia dues, que és
com es van poder separar.

## Comptes

Les altes, baixes i contrasenyes es gestionen al panell de Purelymail.
No hi ha cap comanda ni script nostre que les toque.

L'única adreça amb significat dins del codi és `admin@topquaranta.cat`:
és on arriben les alertes de `tq-health`, els avisos de moderació i el
correu de l'usuari pseudònim `admin` de la comunitat (vegeu
[`architecture/comptes.md`](architecture/comptes.md)).

## DNS (CDMON, gestionat via API)

Estat actual de `topquaranta.cat`:

```
A     @          188.245.60.20            apex (web)
A     www        188.245.60.20            web SPA
A     mail       188.245.60.20            només l'autoconfig; la resta respon 410
A     legacy     188.245.60.20            redirects legacy
MX    @          mailserver.purelymail.com  bústies a Purelymail
TXT   @          brevo-code:…             Brevo domain verification
TXT   @          v=spf1 include:_spf.purelymail.com include:spf.brevo.com -all
TXT   _dmarc     v=DMARC1; p=reject; rua=mailto:postmaster@topquaranta.cat
TXT   v1-ed25519-20260427._domainkey  v=DKIM1; …  DKIM de Stalwart, mort (es pot llevar)
TXT   default._bimi  v=BIMI1; l=https://www.topquaranta.cat/static/brand/bimi.svg
CNAME brevo1._domainkey  b1.topquaranta-cat.dkim.brevo.com  DKIM Brevo
CNAME brevo2._domainkey  b2.topquaranta-cat.dkim.brevo.com  DKIM Brevo
CAA   @          0 issue "letsencrypt.org"
```

DKIM Brevo via CNAME → Brevo signa amb les seves claus, manteniment
zero. Si en algun moment migrem fora de Brevo, els CNAMEs es poden
treure.

El registre `v1-ed25519-20260427._domainkey` era el DKIM propi de
Stalwart i **ja no signa res**. Es conserva perquè llevar un DKIM és
gratis d'ajornar i arriscat de fer amb presses (si alguna cosa encara
signara amb ell, els correus passarien a fallar la verificació); quan es
lleve, que siga a consciència i comprovant abans que cap capçalera
`DKIM-Signature` el referencie.

### CDMON API

Token guardat a `.env` com a `CDMON_API_KEY`. Endpoint base:
`https://api-domains.cdmon.services/api-domains/`. Auth: header
`apikey:` (lowercase). Suporta CRUD per a A/CNAME/TXT (no SRV).

Hi ha un script estable: `dns-backup/cdmon_clean.py` per a operacions
massives (els 21 esborrats inicials que vam fer). El backup del DNS
abans de canvis està a `/home/topquaranta/dns-backup/topquaranta.cat-*.json`.

⚠️ L'endpoint `dnsrecords/create` rebutja A apex (`host="@"`) amb el
missatge enganyós `"Destination to redirect not valid"`. Workaround
documentat: aquesta entrada cal afegir-la manualment al panell web. La
resta d'operacions van bé via API.

## Brevo (relay outbound per `@topquaranta.cat`)

| Camp | Valor |
|------|-------|
| Console | https://app.brevo.com |
| SMTP host | `smtp-relay.brevo.com` |
| Port | 587 (STARTTLS) |
| Login | `a97491001@smtp-brevo.com` (compte SMTP, no email humà) |
| Password | SMTP key del panell Brevo, a `.env` (`EMAIL_HOST_PASSWORD`) |
| Quota gratuïta | 300 emails/dia (per recipient) |

## Resend (relay outbound per `@cercol.team`)

| Camp | Valor |
|------|-------|
| Console | https://resend.com |
| SMTP host | `smtp.resend.com` |
| Port | 587 (STARTTLS) |
| Login | `resend` (literal) |
| Password | API key (`re_…`) generada al panell Resend |
| Quota gratuïta | 100/dia, 3.000/mes |

⚠️ **`cercol.team` ha de ser verificat al panell Resend** (Domains →
Add Domain) abans que els correus surtin. Sense verificació, Resend
respon `550 The cercol.team domain is not verified`.

## BIMI (avatar a clients de correu)

| Camp | Valor |
|------|-------|
| TXT record | `default._bimi.topquaranta.cat` |
| Valor | `v=BIMI1; l=https://www.topquaranta.cat/static/brand/bimi.svg` |
| SVG | `/var/www/brand/bimi.svg` (servit per Caddy a `/static/brand/*`) |
| Format SVG | SVG Tiny PS (`baseProfile="tiny-ps"`, `version="1.2"`) |
| VMC certificat | **Sense** (cost ~$1500/any) |

Conseqüència del "sense VMC": Yahoo, Fastmail, AOL, La Poste mostren
l'avatar BIMI; Gmail no (requereix VMC des del 2024). Per al cas de
Gmail, l'avatar es pot aconseguir registrant un Google Account amb
l'adreça (verificació via codi al correu) i posant foto de perfil al
Google Account — mètode oficial sense pagar VMC.

## Newsletter (Django + Brevo)

L'app Django envia la newsletter setmanal per Brevo directament. Configuració a `topquaranta/settings/production.py`:

```python
EMAIL_HOST = "smtp-relay.brevo.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "<brevo SMTP login>"
EMAIL_HOST_PASSWORD = "<brevo SMTP key>"
DEFAULT_FROM_EMAIL = "Josep Quaranta <noreply@topquaranta.cat>"
```

El nom mostrat («Josep Quaranta») s'aplica a **tot** el correu sortint
de la bústia `noreply@` — es fixa a `DEFAULT_FROM_EMAIL` i `SERVER_EMAIL`
(aquest últim és el remitent de `mail_admins` i també del digest
setmanal, que l'usa directament via `EmailMultiAlternatives`).
L'adreça nua segueix autenticant i formant l'envelope via
`EMAIL_HOST_USER`; el nom només afecta la capçalera `From` visible. Si
`.env` defineix `DEFAULT_FROM_EMAIL`, ha d'incloure el nom o sobreescriu
el default.

Valors a `.env`. Comanda: `publicar_canal --channel newsletter`.
Plantilla: `comptes/templates/comptes/email_newsletter_top.html`.
Codi sender: `comptes/newsletter.py`. Unsub URL signada amb
`signing.dumps(salt="newsletter-baixa")`, endpoint
`/api/v1/compte/baixa-newsletter/`.

## Còpies de seguretat

**Res a copiar.** Les bústies viuen a Purelymail i les còpia ell; nosaltres
no en tenim cap dada. `tq-backup` fa la base de dades i prou.

Fins al 2026-08-18 ací hi havia el procediment d'exportar la base RocksDB
de Stalwart, que mai es va arribar a automatitzar. Al retirar-lo, la
tasca desapareix en lloc de quedar pendent — que és l'única cosa bona de
deixar d'allotjar un servei.
