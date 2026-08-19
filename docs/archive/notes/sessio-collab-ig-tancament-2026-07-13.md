# Col·laboradors IG — tancament del cicle · 2026-07-13 (referència local)

> Nota local (untracked), regenerada en la sessió de seguiment del
> 12/13-07 al Mac. Consolida la sessió remota del 06-07 (contenidor,
> sense accés al Mac ni a prod-write) i esta. Substituïx com a estat
> vigent `nota-observacio-collab-ig-2026-07-06.md` i complementa
> `collab-ig-tranche*.md` i `sessio-stories-novetats-2026-07-03.md`
> (històrics).

## Estat final (2026-07-13, tot desplegat i verificat)

- **ADR-0015: Accepted.** Cicle definitiu: convidar per API en publicar
  → acceptacions marcades manualment per Miquel quan les observa a
  l'app (staff) → `caducada` als 14 dies com a únic terminal automàtic
  (cobrix silenci i rebuig; els dos són categoria C, cooldown 90 dies).
- **main == prod == `6db2439`.** Migració `music/0092` aplicada. Suite
  1502 passed / 10 skipped.
- PRs de la seqüència: #314 (fail-safe) → #318 (fre temporal + docs) →
  #319 (exit non-zero + alerta token, Miquel) → #320 (tancament empíric
  als docs) → #321 (cicle definitiu als docs) → **#322 (implementació:
  poller expirador + UI staff)** → **#323 (mencions user_tags a totes
  les stories)**.

### Què hi ha ara en producció

- `pollar_colaboracions_ig` (horari) = **expirador pur**: cap crida a
  Graph; caducitat `pendent→caducada` >14d + mètrica
  `ig_collab_taxa_acceptacio` derivada del registre. Verificat en viu:
  `Caducades 0 · taxa acceptació 0.000 (0/0)`.
- **Staff** `/staff/social/instagram`: taula del registre d'invitacions
  + botó únic "Marcar acceptada" (`estat=acceptada` + `data_resolucio`;
  idempotent; permés des de `caducada`; audit
  `collab_invitacio_acceptada`). Endpoints
  `GET/POST /staff/social/invitacions[/acceptar]/`. Sense rebuig manual
  (deliberat).
- **Mencions a stories (#323)**: els sets del cron (PPCC amb slide de
  novetats, territorials) porten `user_tags` per story — només els
  artistes (principals + col·laboradors) de les cançons visibles a
  cada story, ancorats prop del seu ítem; guard de no-bloqueig
  reutilitzat (`max_slots=20`); una story que falla no bloqueja la
  resta (fallada parcial → `metadata.stories_fallides` + exit
  non-zero). Cap canvi d'imatge; cap knob nou.

### Rellotges

- Les **3 invitacions del 06-07** (Fades `fadesfadesfades`, Triquell
  `_triquell`, Maria Jaume `mariajaume_`; media `18094840829027683`,
  post <https://www.instagram.com/topquaranta/p/DackzKGAmsf/>)
  continuen `pendent` (verificat per Miquel a l'app el 13-07: cap
  acceptada). **Caduquen automàticament el 2026-07-20 ~09:31 UTC** si
  no es marquen abans des de staff.
- **Dimecres 15-07 09:30 UTC**: primera tanda real de stories amb
  mencions (top_territorial) — ullada visual a les bombolles.

## Incident token IG (2026-07-07 → 2026-07-11) i recuperació

- Meta va invalidar la sessió del token entre les 04:00 i les 05:00 UTC
  del 07-07 (OAuthException **code 190**, "user changed their password
  or Facebook has changed the session"; la fila `InstagramAuth` no
  havia canviat des del 15-06 → invalidació del costat Meta).
- Impacte: **publicacions IG del 08-07 (top_territorial VAL) i de
  l'11-07 (top_ppcc) fallides** (feed + stories); Mastodon/Bluesky/
  Telegram/Newsletter van eixir normals. Cap alerta aleshores
  (publicar_social eixia 0) → **#319** ho tanca: exit non-zero en
  fallada parcial + health-check d'expiració del token.
- Recuperació: Miquel va reautoritzar dissabte nit 11-07 (token nou del
  dashboard desat via staff, validació 200, id `26757745223916689`).
  Dilluns 13-07 09:31 UTC el post va eixir amb normalitat, stories
  incloses. (Els posts fallits del 08 i 11-07 NO es van republicar —
  decisió pendent només si Miquel ho vol.)

## Diagnòstic A2 del poller — amb el cru

Timeline dels errors del poller sobre el media `18094840829027683`
(logs del box en **CEST**; el "tick de les 10:00 UTC" apareix com a
12:00):

1. **29 ticks** (06-07 10:00 → 07-07 04:00 UTC, token viu):
   `IG API 400: {"error":{"message":"Tried accessing nonexisting field
   (collaborators)","type":"IGApiException","code":100}}`
2. **136+ ticks** (des del 07-07 05:00 UTC): el code 190 del token
   (incident de dalt), que va emmascarar l'A2 fins a la reautorització.

Repro de les 3 variants (12-07, token encara invalidat — totes 190;
l'única senyal estructural: graph.facebook ni parseja el token IGAA):

- graph.instagram v19.0 → 400 code 190 (fbtrace `AEyp6qNN…`)
- graph.instagram v23.0 → 400 code 190 (fbtrace `AsSmT9hs…`)
- graph.facebook v23.0 → 400 code 190 **"Cannot parse access token"**

**Tancament empíric (13-07, Miquel al Graph API Explorer)**: amb token
d'usuari sabor Facebook (v25.0), `GET /<media>/collaborators` → **200
amb `data` buida** mentre l'app mostrava les 3 invitacions PENDENTS;
el token de pàgina és inaccessible al tipus d'app (`pages_show_list`
no disponible). → Lectura programàtica d'acceptacions **inviable per
dos motius independents** (IG Login: l'edge no existix; FB Login user
token: edge buit per a pendents; page token: inaccessible). Registrat
a l'ADR-0015 §5.5 (#320) i resolt amb el disseny definitiu (#321/#322).

## Informe d'auditoria B1-B7 — RECONSTRUCCIÓ

> ⚠️ **Reconstrucció marcada com a tal.** L'informe original de la
> sessió remota del 06-07 (contenidor claude.ai/code,
> session_01VHE3aB973cL3pVHkgMoFYR) no era accessible des del Mac i no
> està en cap fitxer del repo; la numeració i el wording exactes
> s'han perdut. Esta llista reconstruïx les 7 narratives pendents a
> partir del mandat de la sessió de seguiment (FASES 1-3 del prompt
> del 12-07) i del PR #318. Totes 7 queden **RESOLTES**.

| # | Narrativa pendent (reconstruïda) | Estat | Evidència |
|---|---|---|---|
| B1 | Les files d'`InvitacioColaboracioIG` coincidixen amb la taula aprovada (3 files: Fades/Triquell/Maria Jaume, top_territorial, 06-07, media `…683`) | ✅ RESOLTA (12-07) | Query a prod: coincidència exacta, totes `pendent`, `data_invitacio` 09:31:32 UTC |
| B2 | El cron de les 09:30 del 06-07 va publicar net: container amb collaborators, guard de substitució no activat, media_publish OK | ✅ RESOLTA (12-07) | social.log.1: 12 containers ready, `publicat → media_id=…683`, 0 línies de guard; les 3 files escrites post-publish (només s'escriuen si els collaborators s'han enviat) |
| B3 | Verificació visual del post real (permalink + estat de les invitacions a l'app) | ✅ RESOLTA (12/13-07) | Permalink `instagram.com/topquaranta/p/DackzKGAmsf/`; Miquel 13-07: 3 invitacions PENDENTS a l'editor, cap co-autor a la capçalera |
| B4 | El pitjor cas real del poller amb el fre actiu és warning + tot pendent + mètrica neta | ✅ RESOLTA (12-07) | Execució manual: error logat, cap estat tocat, 3 `pendent`, mètrica 0.0 idempotent |
| B5 | `ig_collaboradors_actiu=True` és l'únic flag sensible canviat recentment; la resta de gates inerts | ✅ RESOLTA (12-07) | Dump complet de ConfiguracioGlobal + audit config_update 30d: només `landing_editorial_veu` (14-06) i el flag (04-07 10:44 UTC, miquelmatoses) |
| B6 | Cap publicació fora de les autoritzades des del 03-07 (3 stories manuals + calendari) | ✅ RESOLTA (12-07) | SocialPost 03→12-07: tot calendari; úniques anomalies els 2 errors IG del token (08/11-07) |
| B7 | L'error del poller (A2): /collaborators és accessible amb el nostre sabor d'API? | ✅ RESOLTA I TANCADA (13-07) | Cru de dalt: code 100 sota IG Login (29 ticks); FB user token 200 buit; page token inaccessible → via tancada, disseny definitiu implementat |

## Altres coses fetes en la sessió de seguiment

- Branques residuals mergejades esborrades d'origin:
  `newsletter-top40-redesign` (PR #246) i `worktree-backup-offsite-recon`
  (PR #311); verificat abans que el PR #312 obert penja de
  `feat/newsletter-gmail-compat`. **No tocades**: `redisseny-tail`,
  `legacy`, `feat/routine-esborrany-setmana`. La branca
  `claude/collaborators-verify-audit-sw6b5l` (mergejada com a #318)
  també es va esborrar en el cicle normal.
- Worktree de treball: `~/Claude/TopQuaranta-wt-seguiment` (detached a
  main; reutilitzable o esborrable amb `git worktree remove`).
- **Els 11 PRs oberts (9 dependabot + #312 newsletter + #287 portada)
  NO s'han tocat** — triatge de Miquel en sessió a banda. Dependabot
  seguix avisant de 4 vulnerabilitats a main (1 high) — part d'eixe
  triatge.

## Referències

- ADR: `docs/decisions/0015-ig-collaborator-invitations.md` (Accepted)
- Docs: `docs/architecture/social-collaboradors.md`,
  `docs/architecture/social-stories.md` (§ Story mentions),
  `docs/architecture/social.md`, `docs/architecture/staff.md`
- Notes històriques locals: `nota-observacio-collab-ig-2026-07-06.md`,
  `collab-ig-tranche{1,3a,3b}-*.md`, `sessio-stories-novetats-2026-07-03.md`
