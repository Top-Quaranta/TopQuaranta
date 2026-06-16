# Correu electrònic — topquaranta.cat + cercol.team

## Resum d'arquitectura (estat 2026-04-27)

Mailbox + IMAP servits per **Stalwart Mail Server** v0.16.1 al servidor
Hetzner. Outbound delivery va per dos relays externs perquè Hetzner bloca
port 25 outbound:

```
            ┌─────────── Hetzner Cloud Firewall ──────────┐
inbound  →  │ port 25 (SMTP) ─→ Stalwart receives        │
            │ port 993 (IMAPS) ←─ clients (Spark, Mail…) │
            │ port 465 (SMTPS) ←─ clients submission     │
            └─────────────────────────────────────────────┘
                                   │
                  Stalwart accepts authenticated submission
                  for either domain, queues it, then routes:
                                   │
              ┌────────────────────┼────────────────────┐
              ↓                    ↓                    ↓
       sender ends in        sender ends in       (no match)
       @topquaranta.cat     @cercol.team
              │                    │                    │
              ↓                    ↓                    ↓
       smtp-relay.brevo.com  smtp.resend.com         dropped
       (Brevo, port 587)     (Resend, port 587)
              │                    │
              └────────────────────┴──→ Gmail / Outlook / etc.
```

## Per què aquest setup

Hetzner Cloud bloqueja el port 25 outbound a totes les VMs durant els
primers ~30 dies (i sovint també després — política anti-spam). Sense 25
outbound, Stalwart no pot entregar directament als MX dels destinataris.
Tres opcions:

1. Demanar el desbloqueig + arreglar reputació IP (4-8 setmanes de
   warm-up + risc de blacklist).
2. Usar un relay extern. ← **adoptat**
3. Allotjar Stalwart en un altre proveïdor sense bloqueig.

Brevo + Resend són gratis fins a 300/dia (Brevo) i 3.000/mes (Resend),
suficient per a la mida actual.

## Infraestructura

| Component | Detall |
|-----------|--------|
| Servidor | Hetzner CX22 — `188.245.60.20` |
| Software | Stalwart Mail Server v0.16.1 |
| Binari | `/usr/local/bin/stalwart` |
| Config | `/etc/stalwart/config.json` (RocksDB a `/var/lib/stalwart/`) |
| Env vars | `/etc/stalwart/stalwart.env` |
| Cert TLS | Let's Encrypt copiat de Caddy via systemd `path-watch` |
| Servei | `systemctl {start,restart,status} stalwart` |
| Reverse proxy | Caddy — `mail.topquaranta.cat` (admin UI + autoconfig) |

## Ports oberts

A la VM (i autoritzats al **Hetzner Cloud Firewall** `firewall-1`):

| Port | Protocol | Funció |
|------|----------|--------|
| 25 | SMTP | Recepció de correu (inbound) |
| 465 | SMTPS | Submission per a clients (Spark, Apple Mail) |
| 587 | SMTP submission | (deshabilitat — Stalwart 0.16 no l'aixeca per defecte) |
| 993 | IMAPS | Lectura via clients |
| 995 | POP3S | Lectura via POP3 (rarament usat) |
| 8080 | HTTP | Admin web UI (només `localhost`, exposat via Caddy a 443) |

Si en el futur cal port 587, configurar al panell Stalwart → Network →
Listeners.

## Comptes de correu

Definits a Stalwart com a "principals". Contrasenyes guardades al
gestor de passwords del Miquel.

| Compte | Funció | Avatar a Gmail (Google Acc.) |
|--------|--------|------------------------------|
| `admin@topquaranta.cat` | Administrador | pendent |
| `noreply@topquaranta.cat` | App Django (no humà) | n/a |
| `info@topquaranta.cat` | Contacte públic | pendent |
| `miquel@topquaranta.cat` | Personal Miquel | ✓ |
| `hello@cercol.team` | Bústia Cèrcol | n/a |

## Smarthost routing (Stalwart)

Configurat al panell Stalwart → MTA → Routing.

**Rutes** (`/admin/` → MTA → Routing → Routes):

| ID | Type | Address | Port | Auth |
|----|------|---------|------|------|
| `local` | Local Delivery | — | — | — |
| `default` | Remote Delivery (MX) | — | — | — |
| `brevo-relay` | Relay Host | `smtp-relay.brevo.com` | 587 | `a97491001@smtp-brevo.com` + Brevo SMTP key |
| `resend-relay` | Relay Host | `smtp.resend.com` | 587 | `resend` + Resend API key |

**Outbound Delivery Strategy → Routing**:

```
IF  is_local_domain(rcpt_domain)        →  'local'
IF  sender_domain == 'cercol.team'      →  'resend-relay'
ELSE                                    →  'brevo-relay'
```

Avaluació top-down. Domini local cau a 'local'; cercol.team va per
Resend; tot el demés (incloent topquaranta.cat) per Brevo.

⚠️ **Després de qualsevol canvi al panell** Stalwart → cal `sudo
systemctl restart stalwart`. Reload SIGHUP no està suportat (`Job type
reload is not applicable`).

## DNS (CDMON, gestionat via API)

Estat actual de `topquaranta.cat`:

```
A     @          188.245.60.20            apex (web)
A     www        188.245.60.20            web SPA
A     mail       188.245.60.20            Stalwart
A     legacy     188.245.60.20            redirects legacy
MX    @          mail.topquaranta.cat     inbound
TXT   @          brevo-code:…             Brevo domain verification
TXT   @          v=spf1 mx include:spf.brevo.com -all  SPF amb Brevo
TXT   _dmarc     v=DMARC1; p=reject; rua=mailto:postmaster@topquaranta.cat
TXT   v1-ed25519-20260427._domainkey  v=DKIM1; …  Stalwart DKIM (no usat actualment)
TXT   default._bimi  v=BIMI1; l=https://www.topquaranta.cat/static/brand/bimi.svg
CNAME brevo1._domainkey  b1.topquaranta-cat.dkim.brevo.com  DKIM Brevo
CNAME brevo2._domainkey  b2.topquaranta-cat.dkim.brevo.com  DKIM Brevo
CAA   @          0 issue "letsencrypt.org"
```

DKIM Brevo via CNAME → Brevo signa amb les seves claus, manteniment
zero. Si en algun moment migrem fora de Brevo, els CNAMEs es poden
treure. El DKIM ed25519 propi de Stalwart és backup per si en algun
moment passem a delivery directe (Hetzner desbloca 25).

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
| Password | SMTP key generada al panell Brevo, guardada a Stalwart `resend-relay` route |
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

## TLS de Stalwart (cert Let's Encrypt via Caddy)

Caddy gestiona el cert per a `mail.topquaranta.cat`. Stalwart no parla
ACME directament, però llegeix el cert de fitxer:

```
/etc/stalwart/certs/mail.topquaranta.cat.{crt,key}
```

Aquests fitxers són còpia dels de Caddy a
`/var/lib/caddy/.local/share/caddy/certificates/.../mail.topquaranta.cat/`.

**Sync automàtic**: hi ha una systemd `path` unit que vigila el cert
de Caddy i, quan canvia (renovacions cada ~60 dies), copia els fitxers
a `/etc/stalwart/certs/` + reinicia Stalwart:

* `/etc/systemd/system/stalwart-cert-sync.path`
* `/etc/systemd/system/stalwart-cert-sync.service`
* `/usr/local/sbin/stalwart-cert-sync.sh`

La primera vegada el cert s'ha de carregar manualment via panell
Stalwart → TLS → Certificates (admet path o paste de PEM). Després el
sync automàtic n'agafa les renovacions.

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

## Configuració de clients de correu

Tots els clients (Apple Mail, Spark, K-9, Thunderbird) amb la
**mateixa estructura per a tots els 4 + 1 comptes**:

| Camp | Valor |
|------|-------|
| IMAP server | `mail.topquaranta.cat` |
| IMAP port | 993 SSL/TLS |
| SMTP server | `mail.topquaranta.cat` |
| SMTP port | 465 SSL/TLS |
| Username (per a tots dos) | el correu sencer |
| Password (per a tots dos) | la del compte (mateixa per IMAP i SMTP) |

⚠️ Cal **configuració manual** a cada client. L'autoconfig Mozilla
està servit a `https://mail.topquaranta.cat/.well-known/autoconfig/mail/config-v1.1.xml`
(Caddy bloc `mail.topquaranta.cat`) però alguns clients fan autoconfig
heurístic que pot agafar `imap.<domain>` (no existent) primer i errar.

Ports/credencials Brevo i Resend no s'introdueixen mai al client —
Stalwart els usa internament.

## Newsletter (Django + Brevo)

L'app Django envia la newsletter setmanal via Brevo directament (no via
Stalwart smarthost) perquè la quantitat justifica anar pel relay
directament. Configuració a `topquaranta/settings/production.py`:

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
(aquest últim és el remitent de `mail_admins`, p.ex. el digest setmanal).
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

Dades Stalwart a `/var/lib/stalwart/` (RocksDB). Backup amb el binari:

```bash
systemctl stop stalwart
/usr/local/bin/stalwart --config /etc/stalwart/config.json --export /path/backup/
systemctl start stalwart
```

A automatitzar al cron amb el patró del `tq-backup` script.

## Manteniment

| Tasca | Comanda | Freqüència |
|-------|---------|------------|
| Reiniciar Stalwart després d'editar al panell | `sudo systemctl restart stalwart` | Després de cada canvi |
| Logs de Stalwart | `tail -f /var/log/stalwart/stalwart.log.YYYY-MM-DD` o `journalctl -u stalwart` | Quan investiguis |
| Estat dels relays | `tail /var/log/stalwart/*.log \| grep delivery.delivered` | Setmanal |
| Renovació DKIM Stalwart (si es passa a directe) | Stalwart ho fa cada 90 dies, cal actualitzar DNS via API CDMON | Trimestral |
| Verificar BIMI | https://bimigroup.org/bimi-generator/ | Quan canvies SVG |

## Pendents documentats

* Verificar `cercol.team` a Resend (panell Resend → Domains).
* Crear bústia (o alias) `postmaster@topquaranta.cat` per rebre informes
  DMARC. Ara mateix els reports queden en cua sense destinació real;
  no és greu però és la pràctica recomanada.
* Habilitar port 587 STARTTLS a Stalwart per si algun client mòbil futur
  ho necessita (Spark/Apple Mail funcionen amb 465, no és urgent).
* Google Accounts addicionals per a `info@`, `admin@` (limitació de
  verificació telefònica de Google: cal esperar 30-60 dies o usar un
  altre número).
