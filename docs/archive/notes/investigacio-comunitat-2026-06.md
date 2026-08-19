# Investigació comunitat — estat, evidència i fets (2026-06-15)

> **Fase 1 de l'arc de comunitat. Document inert (read-only + spec).**
> Només estat actual amb evidència `file:line`, números reals de
> producció, make-or-breaks i superfície de canvi per a la fase 2. Cap
> recomanació d'implementació: el pla el fa en Miquel.
>
> Protocol d'escèptic: cada claim de capacitat porta l'output cru de la
> comanda que el prova. Números de prod via SSH
> (`sudo -u topquaranta`, `DJANGO_SETTINGS_MODULE=...production`,
> `apps.get_model`). Secció final d'*unknowns* i *decisions*.
>
> Nota: el codi viu a l'**arrel** del repo (no hi ha `app/`).

## TL;DR

El model JA és una plataforma de col·laboració musical (rol, instruments,
"obert a col·laboracions"), no un directori genèric. El problema NO és el
model: és que **gairebé ningú arriba a fer-se visible ni es declara
músic**, no hi ha gairebé activitat, i **falten eines de seguretat
bàsiques** (report/block d'usuari, moderació de DM) que són prerequisit
per fer créixer una comunitat oberta.

Funnel real: **19 registrats → 10 completen onboarding → 3 visibles al
directori → 1 obert a col·laboracions / 1 que es declara músic.**

---

## A. Model de participació

### Estat actual (evidència)

**`PerfilUsuari`** (`comptes/models.py:263-374`), 1:1 amb `Usuari`
(`:286`). Camps rellevants:

- Identitat: `nom_public` `:289`, `localitat` (FK Municipi) `:290-295`,
  `imatge_url` `:297`, `bio` (TextField, 2000) `:298`.
- 11 URLs socials `:303-313`.
- **Intenció col·laborativa (MAKE-OR-BREAK: SÍ existeix):**
  - `rol_musical` (choices) `:315-317` — `ROL_ESCOLTADOR/ROL_MUSIC/
    ROL_PRODUCTOR/ROL_ALTRE` (`:275-284`).
  - `instruments` (CharField 255) `:318`.
  - `obert_colaboracions` (Boolean, default False) `:321`.
- **Visibilitat/consentiment:** `visible_directori` (Boolean,
  **default False**, db_index) `:320` — porta del directori, **opt-in**.
  Consentiment de termes: `consent_termes_at`/`consent_termes_versio`
  `:337-346`.
- Notificacions: `notificar_missatges_email` `:324`,
  `notificar_comentaris_email` `:325` (default True, opt-out).
- Onboarding: `onboarding_complet` (default False) `:330`.

**Altres models de comunitat** (`comptes/models.py`): `Publicacio`
`:377-441` (post amb `estat` esborrany/pendent/publicat/rebutjat,
`visibilitat` interna/publica), `Missatge` `:449-477` (DM 1-a-1),
`Comentari` `:485-506` (comentari pla sobre Publicacio).
`UserArtista` (gestor↔artista) viu al mateix mòdul.

### Números reals (prod, output cru)
```
PerfilUsuari total: 19
  visible_directori=True: 3   (+ usuari actiu: 3)
  obert_colaboracions=True: 1
  onboarding_complet=True: 10
  bio no buida: 3 | instruments no buit: 2 | imatge: 2 | localitat: 2
rol_musical: escoltador 18 · music 1
```

### Make-or-break A
- **La intenció col·laborativa existeix al model però NO s'usa.** 18 de
  19 perfils són `escoltador`, 1 `music`, 1 `obert_colaboracions`. El
  directori no és genèric, però el contingut que el faria útil (rol +
  instruments + obertura) està buit. No és un problema d'esquema sinó
  d'adopció.

### Superfície de canvi (fase 2)
- Model: `comptes/models.py` (PerfilUsuari `:263-374`).
- Edició/lectura de perfil: `web/api/comunitat_views/perfil.py`.

### Unknowns A
- No verificat si hi ha índexs/consultes que permetin filtrar el
  directori per `rol_musical`/`instruments` de manera eficient a escala
  (avui el volum és trivial).

---

## B. El funnel real

### Estat actual (evidència — camí complet)
1. **Registre:** `POST /api/v1/auth/register/`
   (`web/api/auth_views.py:185-289`) crea `Usuari` (`is_active=False`,
   `:241-248`) i estampa consentiment de termes (`:251-266`).
2. **Creació de perfil:** automàtica via signal
   `comptes/signals.py:14-23` (`post_save` → `PerfilUsuari.get_or_create`).
   Cada usuari té perfil des del minut zero.
3. **Onboarding:** `web-react/src/pages/OnboardingPage.jsx:1-243`
   (ruta `/onboarding`, `App.jsx:185`). PATCH a `/comunitat/perfil/`
   amb `rol_musical`, `instruments`, `visible_directori`,
   `obert_colaboracions`, etc. (`OnboardingPage.jsx:56-80`). **Es pot
   saltar** ("Saltar" → `onboarding_complet=True` sense omplir res).
4. **Fer-se visible:** `visible_directori` editable per PATCH a
   `web/api/comunitat_views/perfil.py:76-84` (checkbox a l'onboarding i
   al perfil). Default False.
5. **Directori:** `GET /api/v1/comunitat/directori/`
   (`web/api/comunitat_views/perfil.py:102-183`); gate
   `visible_directori=True` per a no-staff (`:119-121`), staff veu tot.

### Números reals (prod, output cru)
```
Usuaris: 19 total · 18 actius · 1 staff   (primer registre 2025-08-25)
onboarding_complet=True: 10
visible_directori=True: 3
Registres/setmana (recents): 3, 2, 1, 0, 3, 0, 0, 0, 1, 0
```
**Funnel:** 19 registrats → 10 onboarding complet (53%) → 3 visibles
(16% dels usuaris; 30% dels qui completen onboarding) → 1 obert a
col·laboracions.

### Make-or-break B (on és la fuga)
Tres fuites acumulades expliquen els "3 visibles de ~18":
1. **~47% no acaba l'onboarding** (10/19) i es pot **saltar** sense
   omplir res (`OnboardingPage.jsx`).
2. **`visible_directori` és opt-in (default False)** `:320`: dels 10 que
   acaben l'onboarding, només 3 marquen la casella de visibilitat.
3. **Quasi ningú es declara músic/col·laborador** (1 `music`, 1
   `obert_colaboracions`): fins i tot els 3 visibles no són
   necessàriament l'audiència col·laboradora.

### Superfície de canvi (fase 2)
- `web/api/auth_views.py` (registre), `comptes/signals.py` (perfil auto),
  `web-react/src/pages/OnboardingPage.jsx`,
  `web/api/comunitat_views/perfil.py`.

### Unknowns B
- No hi ha cap event d'analytics que mesuri abandó dins de l'onboarding
  (quants arriben a `/onboarding` i no el completen). Només tenim
  `registre_complet` i el flag final `onboarding_complet`.

---

## C. Descobriment del directori

### Estat actual (evidència)
- Ruta SPA: `/comunitat/directori` → `ComunitatDirectoriPage`
  (`web-react/src/App.jsx:197`).
- Enllaçat des de la nav de comunitat (`ComunitatLayout.jsx:25-31`), del
  feed (`ComunitatPage.jsx`) i de Missatges (`MissatgesPage.jsx`).
- **NO** està enllaçat des de les superfícies públiques d'alt trànsit:
  la nav principal del lloc, les fitxes d'artista, el rànquing o la
  home. La comunitat viu darrere de `/comunitat/*` (zona autenticada).
- **Analytics:** l'event `directori_filter`
  (`web/api/analytics_ingest.py:39`) es dispara a **`/artistes`** (el
  directori públic d'artistes), NO a `/comunitat/directori`
  (`web-react/src/pages/ArtistesPage.jsx:125-128`). La pàgina de
  directori de comunitat **no té instrumentació d'analytics**.

### Make-or-break C
- El directori de comunitat és **descobrible només des de dins de la
  zona `/comunitat`** (un usuari ja registrat i navegant la comunitat).
  No hi ha cap pont des del trànsit públic (fitxes d'artista, rànquing)
  cap a la comunitat. No es pot mesurar el seu ús perquè no està
  instrumentat.

### Unknowns C
- No verificat si la nav principal de la SPA (capçalera global) inclou
  cap enllaç a `/comunitat` per a usuaris no autenticats (cal mirar el
  component de capçalera global; no confirmat en aquesta investigació).

---

## D. Mecanisme de connexió (DM)

### Estat actual (evidència)
- `Missatge` `comptes/models.py:449-477`: `remitent` (SET_NULL),
  `destinatari` (CASCADE), `assumpte`, `cos` (10000), `llegit_at`,
  `created_at`. **Sense threading** (les converses es reconstrueixen
  aparellant remitent/destinatari) i **sense camp d'estat, soft-delete
  ni report** (grep cru: els únics camps són els 6 anteriors).
- Enviament: `missatge_crear`
  (`web/api/comunitat_views/missatgeria.py:113-143`), throttled
  (`_DMSendThrottle`). **MAKE-OR-BREAK: qualsevol usuari autenticat pot
  escriure a qualsevol altre** via `get_object_or_404(_U, pk=dest_pk)`;
  l'únic gate és no escriure's a un mateix. No hi ha llista de
  bloqueig, ni opt-in de recepció, ni consentiment.
- Notificació email: `_enviar_notificacio_missatge`
  (`web/api/comunitat_views/_common.py:159-229`) respecta
  `notificar_missatges_email` (`:199`).
- Relay admin (Fase 1.5.B): pseudo-usuari `admin`
  (`comptes/migrations/0016_admin_pseudouser.py`, `is_staff=False`),
  `ADMIN_INBOX_USERNAME` (`settings/base.py:99`); un DM a `admin`
  s'envia per email a tot l'staff actiu (`_common.py:179-194`).

### Números reals (prod, output cru)
```
Missatges total: 6  (últims 30d: 4)
  dirigits a admin (inbox staff): 2
  DM real entre membres: 4
  remitents distints: 2 | parelles de conversa distintes: 3
```

### Make-or-break D
- El DM **funciona** però amb ús mínim (6 missatges, 2 remitents) i
  **sense cap control de consentiment ni bloqueig**: a escala, qualsevol
  pot escriure a qualsevol sense que el receptor ho pugui impedir. És un
  risc de seguretat per a una comunitat oberta.

### Superfície de canvi (fase 2)
- `web/api/comunitat_views/missatgeria.py`, `._common.py`,
  `comptes/models.py` (Missatge).

### Unknowns D
- No verificat si el throttle `_DMSendThrottle` té un límit prou baix
  per frenar abús (no s'ha llegit el rate exacte).

---

## E. Confiança i seguretat / moderació

### Estat actual (evidència)
**Present:**
- Moderació de posts públics: `staff_publicacio_decidir`
  (`web/api/comunitat_views/staff_moderacio.py:54-80`) —
  publicar/rebutjar/despublicar (no hard-delete). Cua d'aprovació:
  posts `publica` de no-staff van a `pendent`
  (`publicacions.py:26-55`).
- Esborrar comentari: `comentari_esborrar`
  (`publicacions.py:182-211`) — autor, propietari del post o staff.
- Toggle de visibilitat al directori per staff:
  `staff_directori_toggle_visible`
  (`staff_moderacio.py:135-141`).
- Plantilles d'email de moderació: `comptes/email_missatge.html`,
  `comptes/email_comentari.html`.

**Absent (MAKE-OR-BREAK, grep cru mostrat):**
- **Report/denúncia d'usuari:** cap model ni endpoint (els "report" del
  codi són `Feedback` de pàgina pública, `comptes/models.py:192`).
- **Bloquejar un usuari:** cap model `Block`/`BlockedUser` ni endpoint.
- **Report d'un post o comentari:** cap.
- **Esborrar/ocultar un Missatge** (ni staff ni usuari): cap endpoint;
  `Missatge` no té camp d'estat ni soft-delete.

### Make-or-break E
- **Falten les eines de seguretat bàsiques d'una comunitat oberta**
  (report, block, moderació de DM). Avui la moderació es limita a
  aprovar posts públics, esborrar comentaris i amagar perfils del
  directori. Per créixer cal almenys report + block d'usuari i control
  de DM.

### Superfície de canvi (fase 2)
- `comptes/models.py` (nous models de report/block),
  `web/api/comunitat_views/` (endpoints), `web/api/comunitat_views/
  staff_moderacio.py`.

### Unknowns E
- No verificat si hi ha cap rate-limit o captcha al registre que freni
  comptes massius (rellevant per a abús a escala).

---

## F. Proposta de valor end-to-end

### Estat actual (evidència)
Pàgines de comunitat (`web-react/src/App.jsx:189-205`,
zona `/comunitat/*` autenticada):

| Pàgina | Ruta | Què pot fer un membre |
|---|---|---|
| ComunitatPage | `/comunitat/` | Veure el feed de posts interns + propis |
| PerfilUsuariPage | `/comunitat/perfil` | Editar perfil (rol, instruments, visibilitat, socials) |
| ComunitatDirectoriPage | `/comunitat/directori` | Veure membres visibles, filtrar, missatjar |
| MissatgesPage | `/comunitat/missatges` | DM 1-a-1 amb qualsevol usuari |
| ComunitatPublicarPage | `/comunitat/publicar` | Crear/editar post (intern publica directe; públic va a cua) |
| ComunitatPublicaPage | `/comunitat/public` | Veure el feed públic |
| ComunitatDetailPage | `/comunitat/:pk` | Llegir post + comentar |

Onboarding (`OnboardingPage.jsx`) guia rol/instruments/visibilitat però
és saltable.

### Números reals (activitat, prod)
```
Publicacio total: 1 (estat=publicat) · Comentari total: 0
Missatges: 6 (4 entre membres) · perfils visibles: 3
```

### Make-or-break F (on es trenca l'experiència)
- El recorregut tècnic és complet (registre → onboarding → perfil →
  directori → DM), però **l'experiència es trenca per buidor**: 3
  perfils visibles, 1 post, 0 comentaris. Un membre nou que arriba al
  directori troba 3 persones (i, com a no-staff, no veu ningú més). No
  hi ha massa crítica ni pont des del trànsit públic (que sí existeix:
  ~the SEO/artist pages) cap a la comunitat.

---

## UNKNOWNS GLOBALS
1. La capçalera global de la SPA (no `/comunitat`) enllaça la comunitat
   per a anònims? No confirmat (cal llegir el component de nav global).
2. Abandó dins de l'onboarding: no instrumentat; no es pot quantificar.
3. Rate exacte de `_DMSendThrottle` i del registre (anti-abús).
4. Ús del directori de comunitat: sense analytics (el `directori_filter`
   mesura `/artistes`, no `/comunitat/directori`).
5. Retenció: no s'ha mesurat last-login ni recurrència (el model
   `Usuari` té `last_login` de Django, no analitzat aquí).

## DECISIONS PER A EN MIQUEL
1. **Visibilitat opt-in vs opt-out** (`visible_directori` default False):
   és la fuga #2 del funnel. Decisió de producte/RGPD, no de codi.
2. **Audiència objectiu de la comunitat:** avui 18/19 són "escoltadors".
   Cal decidir si la comunitat és per a músics (col·laboració) o per a
   oients (fandom), perquè canvia tota la fase 2.
3. **Prerequisit de seguretat:** report + block d'usuari i moderació de
   DM abans d'obrir/promoure la comunitat (avui absents).
4. **Pont des del trànsit públic:** decidir si s'enllaça la comunitat
   des de les superfícies d'alt trànsit (fitxes d'artista, rànquing) o
   es manté com a zona tancada.
5. **Instrumentació:** sense events al funnel d'onboarding ni al
   directori de comunitat, la fase 2 no podrà mesurar si millora.

---

*Investigació read-only. Cap canvi de codi ni escriptura a prod. Únics
fitxers escrits: aquest doc + scratch de treball.*
