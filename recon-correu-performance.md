# Recon — Correu setmanal de performance (Setmanari)

> Recon només-lectura. Data: 2026-07-05. Cap canvi de codi, cap commit,
> cap fix. Prod tocat només en lectura (logs + config + status).

## TL;DR

**El correu SÍ s'envia i SÍ s'entrega correctament.** L'última execució
prevista (dilluns 29 de juny, 08:00 UTC) va córrer amb `exit_code=0`, va
sortir per Brevo, i Stalwart la va rebre de tornada a `admin@topquaranta.cat`
classificada com a **ham** (no spam) i ingerida a la bústia INBOX.

**Cap de les quatre hipòtesis es confirma.** (a) cron absent → refutada,
(b) spam per From no confiat → refutada (classificada ham, INBOX),
(c) comandament falla → refutada (exit 0), (d) mai cablejat → refutada
(cablejat i funcionant, evidència d'entrega real).

Nota sobre la premissa: el correu NO corre dissabte. Corre **dilluns 08:00
UTC**. No hi ha res a arreglar.

---

## 1. Mecanisme (repo)

| Element | Valor |
|---|---|
| Comandament | `enviar_digest_setmanal` (app `analytics`) |
| Fitxer | [analytics/management/commands/enviar_digest_setmanal.py](analytics/management/commands/enviar_digest_setmanal.py) |
| Cron | `0 8 * * 1` → **dilluns 08:00 UTC** ([deploy/cron.topquaranta:255](deploy/cron.topquaranta)) |
| Wrapper | `/home/topquaranta/bin/tq-run enviar_digest_setmanal` → log a `/var/log/topquaranta/analytics.log` |
| From | `settings.SERVER_EMAIL` = `Josep Quaranta <noreply@topquaranta.cat>` ([enviar_digest_setmanal.py:527](analytics/management/commands/enviar_digest_setmanal.py)) |
| To | `settings.ADMINS` = `["admin@topquaranta.cat"]` ([base.py:257](topquaranta/settings/base.py)) |
| Enviament | `EmailMultiAlternatives(...).send(fail_silently=False)` — HTML + text fallback |
| Backend | Brevo SMTP (`smtp-relay.brevo.com:587`, TLS), login `a97491001@smtp-brevo.com` ([production.py:61-74](topquaranta/settings/production.py)) |

Contingut: 6 seccions (audiència humana, referrers, pipeline del catàleg,
ranking per territori, SEO, distribució social) + frescor de dades.
Assumpte: `[TopQuaranta] Setmanari · Setmana N · dd/mm – dd/mm`.

**Discrepància menor (doc, no bug):** el comentari del cron diu «Usa
`mail_admins` → Brevo SMTP». En realitat el codi no fa servir
`mail_admins()`; construeix un `EmailMultiAlternatives` amb From=`SERVER_EMAIL`
i To=`ADMINS`. Mateix destinatari (`admin@`) i mateix relay, però el
comentari és lleugerament obsolet. Sense impacte funcional.

## 2. Crontab viva vs repo

- L'usuari `topquaranta` **no té crontab d'usuari** (`no crontab for
  topquaranta`) — és l'esperat: el projecte usa `/etc/cron.d/topquaranta`.
- `diff /etc/cron.d/topquaranta` vs `deploy/cron.topquaranta` → **IDÈNTIC**
  (només 2 línies en blanc de marge; contingut igual).
- La línia del Setmanari existeix a la crontab viva:
  `/etc/cron.d/topquaranta:255` → `0 8 * * 1 topquaranta ... enviar_digest_setmanal`.

**No hi ha deriva repo↔prod** en aquesta línia (a diferència del precedent
`tq-recover`). Hipòtesi (a) refutada.

## 3. Evidència d'execució

Fitxer d'estat de `tq-run`:
`/var/log/topquaranta/status/enviar_digest_setmanal.status`

```
command=enviar_digest_setmanal
last_run=2026-06-29T08:00:01+00:00
exit_code=0
attempts=1
status=OK
consecutive_skips=0
consecutive_failures=0
last_output<<EOF
[2026-06-29 10:00:02,998] INFO axes.apps: AXES: BEGIN ...
Setmanari enviat: [TopQuaranta] Setmanari · Setmana 43 · 23/06 – 29/06
EOF
```

Log de l'app (`analytics.log` + rotats):
- `Setmanari enviat: ... Setmana 43 · 23/06 – 29/06` (dl 29 juny) ✓
- `Setmanari enviat: ... Setmana 42 · 16/06 – 22/06` (dl 22 juny) ✓

Dues setmanes consecutives, totes dues `exit 0`. Cap error SMTP als logs.

**Sobre «esta setmana»:** avui és diumenge 5 juliol. La propera execució
és **dilluns 6 juliol 08:00 UTC** (demà) — encara no ha tocat. No és un
fallo; és el calendari. L'última execució prevista (29 juny) va anar bé.

Hipòtesis (c) i (d) refutades.

## 4. Evidència d'enviament (entrega real)

El comandament reporta `Setmanari enviat` només si `send(fail_silently=False)`
no llança — és a dir, Brevo va acceptar el missatge. A més, tenim la prova
d'entrega **inbound** al log de Stalwart (`/var/log/stalwart/stalwart.log.2026-06-29`):

```
2026-06-29T08:00:13Z Queued message for delivery
   remoteIp = 77.32.148.25   (IP de Brevo/Sendinblue)
   from = bounces-468910438-433893045@gy.d.sender-sib.com   (envelope Brevo)
   to = ["admin@topquaranta.cat"]   size = 36933
   messageId = ...@smtp-relay.sendinblue.com

2026-06-29T08:00:13Z Message ingested (message-ingest.ham)
   to = admin@topquaranta.cat, accountId = 1, mailboxId = [0]

2026-06-29T08:00:13Z DSN success ... code = 250, details = "OK"
2026-06-29T08:00:13Z Delivery completed
```

Lectura:
- **From efectiu:** capçalera `Josep Quaranta <noreply@topquaranta.cat>`;
  envelope-from de Brevo (`bounces-...@gy.d.sender-sib.com`). Domini
  `topquaranta.cat` verificat a Brevo amb DKIM.
- **Camí:** Django → Brevo SMTP relay → MX de `topquaranta.cat` (Stalwart,
  al mateix box) → bústia `admin@`.
- **Classificació `message-ingest.ham`** → NO spam. Va a INBOX
  (`mailboxId=[0]`), no a Junk.
- **`size = 36933`** → correu HTML complet (el digest ric), no un cos buit.

Hipòtesi (b) refutada: Stalwart el marca **ham** i el posa a la bústia
principal, no a spam.

> Nota: no s'ha accedit ni al compte de correu ni al dashboard de Brevo.
> L'evidència prové exclusivament de logs del servidor (Stalwart transit
> log + status file + analytics.log) i de la config viva de Django.

## 5. Conclusió

El circuit funciona de punta a punta: cron viu i idèntic al repo →
comandament corre setmanalment amb exit 0 → Brevo accepta → Stalwart
rep i ingesta com a ham a la INBOX de `admin@topquaranta.cat`.

Si el Miquel «no veu» el correu, la causa **no** és cap de les quatre
hipòtesis tècniques d'aquest recon. Pistes a mirar (fora d'abast, no
verificades aquí per no accedir a la bústia):
- Regla/carpeta al client IMAP que el mou fora d'INBOX.
- Confusió d'horari: arriba **dilluns ~08:00 UTC** (~10:00 CEST), no dissabte.
- Mirar a la bústia `admin@topquaranta.cat` (no la personal de gmail;
  `ADMINS` apunta a `admin@topquaranta.cat`).

**Cap fix aplicat. Cap proposta implementada.**
