# Investigació — «La cançó del dia»: sonda de receptivitat via story

> Nota local (untracked), 2026-08-13. NOMÉS investigació; cap canvi.
> Objectiu demanat pel Miquel: els dies sense publicació, una story de
> «la cançó del dia» — cançó mai al top, artista amb Instagram conegut,
> mai invitat a col·laborar — maximitzant la diversitat de contactes
> per a omplir el registre d'artistes receptius a col·laboracions.

## 1. Tesi (i per què té sentit ara)

El registre real d'invitacions feed (`InvitacioColaboracioIG`) diu
avui: **45 artistes invitats → 2 acceptades, 33 caducades, 17 pendents**.
Taxa d'acceptació sobre resoltes: **~6%**. Invitar a cegues no
funciona; cal saber *abans* qui és receptiu. La story-menció és la
sonda perfecta: cost zero de relació (una menció no demana res),
l'artista rep notificació, i la seua reacció (reshare/resposta) és el
senyal. Els receptius passen a una cua prioritària d'invitació feed.

**Restricció de plataforma que fixa el disseny** (ja documentada a
memòria): les stories **no admeten col·laboradors** — només `user_tags`
(mencions). La col·laboració formal és feed-only. Per tant el flux és
necessàriament en dos temps: sonda story → invitació feed.

## 2. Què podem mesurar — AUDITAT contra el codi (2026-08-13, 2a passada)

| Senyal | Com | Realitat |
|---|---|---|
| **replies** per story (recompte) | insights `reach,replies,impressions` — l'únic set que l'API accepta per a stories (`instagram_client.get_post_metrics`) | **Automàtic.** Només el NOMBRE; el contingut del DM no és llegible (Standard Access) |
| ~~shares per story~~ | — | **NO EXISTEIX per a stories.** El camp que desa `recollir_metrics_social` és sempre 0 en stories (l'API no l'ofereix; només feed) |
| reach / impressions per story | mateix endpoint | Automàtic, però és VISIBILITAT, no reacció. Finestra: els insights caduquen ~24h després que la story expire — el cron nocturn (00:30) hi arriba a temps per a les dues franges |
| Reshare de la nostra story per l'artista | Graph API no ho exposa; tampoc llegeix story-tags | **NOMÉS MANUAL** (notificacions a l'app d'IG) |
| Acceptació d'invitació feed | `estat=acceptada` — **la marca STAFF a mà** (`social_invitacio_acceptar`) quan ho veu a l'app; l'API NO reporta la resolució | Semi-manual però fiable (l'acceptació és visible a l'app). Les 2 acceptades actuals són marques manuals |
| Rebuig d'invitació feed | `estat=rebutjada` — estat manual d'staff; **mai usat** (0 files a prod) | Teòric fins avui: a la pràctica el "no" es manifesta com a `caducada` |
| Caducitat d'invitació (14 dies) | `pollar_colaboracions_ig` — **l'únic estat automàtic** | Automàtic ✓ |

**Dades reals (37 story-posts amb mètriques, jul-ago 2026):**
- `impressions`: SEMPRE 0 — Meta la va deprecar per a stories; el
  fallback del client acaba en `reach,replies`. Columna morta.
- `reach`: mitjana ~30, stdev ~12, rang 9-53 (slide final del set).
- `replies`: 0 de 37 — però NO perquè ningú responga: **Meta retorna
  sempre 0 en `replies` per a comptes europeus** des del 2020-12-01
  (regulació de privadesa; documentat). El Miquel confirma replies
  reals a l'app que l'API mai reportarà. Mètrica MORTA per a
  nosaltres, com impressions.
- El cron polla NOMÉS `instagram_media_id` = l'ÚLTIMA slide del set;
  per a sondes d'una sola slide, 1 SocialPost = 1 story = mètrica
  pròpia i neta.

**Detector de reacció 100% automàtic (hipòtesi del Miquel, validada
amb la distribució real):** amb la base tan estreta (30±12), un
reshare de l'artista — que aboca els seus seguidors a la story —
produeix un outlier clar (un compte de 500-2000 seguidors pot afegir
30-100 visualitzacions → 3-8σ). Regla: línia base rodant de les
SONDES (mediana + MAD de les últimes N; les stories de top no valen
de base, són una altra classe de contingut) i bandera automàtica quan
`reach > mediana + 3·MAD`. El detector és REACH-ONLY: replies està
morta per a comptes UE (vegeu dalt). Amb un sol artista mencionat,
l'atribució al mencionat és el supòsit més probable.

Quirk de recollida trobat de pas (2026-08-13): quan els insights
d'una story ja han caducat, l'API respon 200 amb `{"data": []}` i el
cron desa una fila de ZEROS silenciosa (no un error). L'anàlisi ha
d'ignorar files amb raw buit — i valdria la pena que `recollir_
metrics_social` no escriguera res en eixe cas (fix menut, tasca
apuntada).

Límits del proxy, assumits: no distingeix el reshare de l'artista del
d'un tercer ni d'un caprici de l'algorisme. Cost del fals positiu:
una invitació feed de més (barat). Fals negatiu: l'artista queda al
funnel per a re-sonda (esglaó 2). CAP PAS MANUAL al bucle de sondes;
l'única acció manual que queda en tot el sistema és la que el Miquel
ja fa i accepta: marcar l'acceptació d'una col·laboració quan la veu
a l'app (ocasional per naturalesa).

## 3. El pool (prod, 2026-08-13)

- Aprovats amb `instagram_url`: **602**
- ...amb alguna cançó al top (ja els mencionem cada setmana): 170
- ...ja invitats a col·laborar: 45
- **POOL: 421 amb IG, mai al top, mai invitats; 304 amb cançó
  pública viva** (`verificada=True, activa=True`)
- Per territori: CAT 270 · BAL 17 · VAL 16 · AND 1

El pool creix sol: el workflow staff «Artistes sense Instagram» va
afegint `instagram_url`, i cada artista nou aprovat que no arriba al
top hi entra.

## 4. Cadència — quins dies són «buits»

Calendari actual (`social/calendari.py::CALENDARI`):

| Dia | Feed | Story |
|---|---|---|
| Dilluns | top territorial B | ✓ |
| Dimarts | nous àlbums | — |
| Dimecres | top territorial A | ✓ |
| Dijous | moviment (GATED per `moviment_actiu`) | — |
| Divendres | nous singles | — |
| Dissabte | top PPCC | ✓ |
| Diumenge | — | — |

**Ritme triat pel Miquel (2026-08-13): els 4 dies sense story
(dt/dj/dv/dg), amb DUES sondes per dia — una de matí i una de
vesprada — = 8 sondes/setmana (~416/any).**

Implicacions del ritme:

- **Runway**: 304 candidats a 8/setmana ≈ **9 mesos** (menys el
  creixement del pool: aprovacions noves + backfill d'IG del workflow
  staff). Cap a los 6-9 mesos caldrà una vàlvula: (i) re-sondar amb
  cooldown de 12 mesos els que no van reaccionar, (ii) ampliar
  elegibilitat (p.ex. els 33 amb invitació caducada, passats 90 dies),
  o (iii) abaixar a 4/setmana. Decisió per a quan arribe; el selector
  ha de degradar EN ORDRE (primer re-sondes, després caducades) i mai
  quedar-se mut.
- **Efecte col·lateral positiu**: el perfil passa a tindre story
  activa pràcticament cada dia (les de top duren 24h i cobreixen
  ds-dg/dl-dt/dc-dj) — presència contínua, cosa que l'algorisme d'IG
  premia.
- Variant màxima (2 sondes TOTS els dies, també els de top):
  14/setmana → runway ~5 mesos; no recomanada d'inici — deixa'l com a
  segona marxa si el senyal és molt bo i el pool creix.

## 5. Selecció: elegibilitat + diversitat

**Elegibilitat** (tot verificable amb camps existents):
- `Artista.aprovat=True`, `instagram_url != ""`,
  `instagram_rebutjat_at IS NULL`
- Cap cançó a `TopSetmanal` (com a artista principal)
- Cap fila a `InvitacioColaboracioIG`
- Cap sonda prèvia (§6 — el registre nou)
- ≥1 `Canco(verificada=True, activa=True)` amb portada

**Algorisme de diversitat** (l'objectiu és cobrir el màxim d'artistes
diferents, no optimitzar engagement):
1. **Mai repetir artista** — la regla dura; per si sola garanteix
   diversitat màxima a llarg termini.
2. **Round-robin per `Artista.genere`** (el camp canònic d'inferir_
   genere) — evita ratxes del mateix circuit/escena, que és com es
   percep la monotonia.
3. **Quota suau territorial**: VAL/BAL són escassos (33 en total);
   a 8/setmana amb round-robin pur s'esgoten en un mes. Proposta: 1
   slot no-CAT cada ~6 sondes (≈1.3/setmana) → duren ~6 mesos, en
   línia amb el runway global.
4. **Dins del tram, prioritat a activitat recent** (llançament <90d):
   més probabilitat de resposta i contingut més fresc.
5. **Tiebreak determinista** per data (hash de `data+artista_id`), no
   `random` — reproducible i idempotent al re-run del cron.

**La cançó de l'artista**: la més escoltada del catàleg viu, llegint
l'últim `SenyalDiari.lastfm_playcount` per cançó (VERIFICAT: el camp
existeix per cançó/dia; cap camp agregat a `Canco`, es consulta el
senyal). Fallbacks necessaris: cançons sense cap senyal (artistes sota
llindar, col·laboracions que perden el senyal — nota de memòria) → la
més recent per data de llançament. Empat → la més recent. (Excepcions
per esglaó: vegeu §5bis.)

## 5bis. L'escala de prioritat (explicitada 2026-08-13)

Cada run agafa candidats de l'esglaó més alt no buit; dins de cada
esglaó s'aplica la maquinària de diversitat del §5 (gènere round-robin
+ quota territorial + activitat recent + tiebreak determinista).

**Esglaó 1 — Mai contactats.** Mai sondejats, mai invitats, mai al
top (els 304). Cançó: la més escoltada del catàleg viu.

**Esglaó 2 — Re-sondes de silenci (cooldown 12 mesos).** Sondejats fa
≥12 mesos amb `reaccio=cap` I mètriques automàtiques a zero; encara
mai invitats ni al top. Un silenci no és un no. Ordre intern: (a)
primer els que tenen llançament NOU des de la sonda — i la story
presenta la cançó nova, mai la mateixa; (b) després per antiguitat de
la sonda. Regla dura: mai repetir la mateixa cançó a un mateix artista.

**Esglaó 3 — Invitacions caducades (cooldown 90 dies, coherent amb la
categoria C de la política de col·laboradors).** Van ignorar la
demanda pesada (invitació feed); la sonda és el re-contacte lleuger.
Molts han estat al top: ací el criteri «mai al top» s'aplica a la
CANÇÓ, no a l'artista — la story és el deep cut d'un artista conegut.
Ordre intern: llançament nou des de la invitació primer, després
resolució més antiga primer.

**Ixen del funnel permanentment** (amb la naturalesa real de cada
estat, vegeu §2):
- reacció positiva a una sonda (marca staff a la card, o `replies>0`
  pendent de revisió) → cua d'invitació feed;
- invitació acceptada (marca manual staff en veure-ho a l'app) →
  registre; reben col·laboracions reals;
- invitació rebutjada (estat manual, mai usat fins ara — si staff no
  marca, un "no" apareix com a caducada i cau a l'esglaó 3 amb el seu
  cooldown; acceptable) → es respecta;
- invitació pendent en vol → mai dos contactes simultanis;
- `instagram_rebutjat_at` estampat → handle mort.

**Decisió oberta (recomanació: NO incloure'ls):** els ~125 topats mai
invitats ni sondejats. Ja reben mencions setmanals quan entren al top
(senyal confós) i el seu canal natural és la invitació feed directa
als posts del top. L'objectiu del funnel és diversitat: els que mai
toquem.

Efecte: l'esglaó 1 dura ~9 mesos; en esgotar-se, el 2 comença a tindre
candidats (els sondejats fa 12 mesos) i el 3 en té des del primer dia
— el selector mai es queda mut i la degradació és per valor esperat
decreixent.


## 5ter. Especificació del selector (estil WHERE/ORDER BY, 2026-08-13)

Selecció d'ARTISTA:

```
WHERE  (elegibilitat dura)
  aprovat = TRUE
  AND instagram_url != ''
    -- NOTA: sense condició sobre instagram_rebutjat_at — el refús de
    -- Meta ja BUIDA instagram_url (i retorna l'artista a la cua
    -- staff); si staff hi posa una URL nova, l'artista reentra ací
    -- encara que el timestamp de refús quede estampat.
  AND NOT EXISTS invitacio(estat = 'pendent')          -- contacte en vol
  AND NOT EXISTS invitacio(estat = 'acceptada')        -- ja al registre
  AND NOT EXISTS invitacio(estat = 'rebutjada')
    -- defensiu: estat manual amb 0 usos històrics; fora de la
    -- taxonomia (§5quater) però es respectaria si mai s'usara
  AND NOT EXISTS sonda(reaccio_auto = TRUE)            -- receptiu → cua feed
  AND NOT EXISTS sonda(data > avui - 12 mesos)         -- cooldown re-sonda
  AND (mai_top OR EXISTS invitacio(estat='caducada'))  -- topats: sols esglaó 3
  AND NOT EXISTS invitacio(estat='caducada'
                           AND data_resolucio > avui - 90 dies)
  AND EXISTS canco(verificada AND activa
                   AND album.deezer_id IS NOT NULL AND mai_al_top)

ORDER BY
  esglao ASC
    -- 1 = mai contactat · 2 = sonda >12m sense reaccio · 3 = caducada >90d
  (torn_no_cat AND territori_principal != 'CAT') DESC
    -- quota: torn_no_cat = (n_sondes_totals % 6 == 0); estat extern
  data_ultima_sonda_del_meu_genere ASC NULLS FIRST
    -- round-robin de gènere; mai sondejats primer
  te_llancament_ultims_90_dies DESC
  te_llancament_posterior_a_ultim_contacte DESC        -- esglaons 2-3
  data_ultim_contacte ASC NULLS FIRST                  -- esglaons 2-3
  md5(data_avui || franja || artista_id) ASC           -- tiebreak determinista
LIMIT 1
```

Selecció de CANÇÓ (de l'artista guanyador):

```
WHERE
  verificada AND activa
  AND album.deezer_id IS NOT NULL
  AND NOT EXISTS topsetmanal(canco)                    -- criteri de cançó
  AND NOT EXISTS sonda(canco)                          -- mai repetir cançó

ORDER BY
  (esglao IN (2,3) AND data_llancament > data_ultim_contacte) DESC
  ultim_senyal_lastfm_playcount DESC NULLS LAST        -- SenyalDiari recent
  data_llancament DESC
LIMIT 1
```

Notes d'implementació: `torn_no_cat` i el round-robin de gènere
necessiten estat extern (comptador de sondes + última sonda per
gènere, derivables de `SondaStoryIG`) → el selector és un service
Python, no una única query. Els `NULLS FIRST/LAST` són deliberats i
asimètrics (mai-contactat primer; sense-senyal últim).

## 5quater. Taxonomia resultant: actitud de l'artista cap a nosaltres

Estats DERIVATS dels camps que ja existeixen o que la sonda crea —
cap columna nova "actitud"; tot és computable:

| # | Estat | Com es detecta (senyal real) | Acció del sistema |
|---|-------|------------------------------|-------------------|
| 1 | **Col·laborador** | `invitacio.estat='acceptada'` (marca manual en veure-ho a l'app) | Registre d'or; rep col·laboracions reals a cada aparició |
| 2 | **Receptiu probable** | `sonda.reaccio_auto=TRUE` (reach > mediana+3·MAD) | Cua prioritària d'invitació feed al proper post on aparega |
| 3 | **En observació** | sonda <48h (mètriques en finestra) o `invitacio.estat='pendent'` | Esperar; cap nou contacte |
| 4 | **Verge** | cap sonda, cap invitació, mai al top | Esglaó 1 del funnel |
| 5 | **Silenciós** | sondejat, cap outlier de reach | Re-sonda a 12 mesos (esglaó 2), preferentment amb novetat |
| 6 | **No-responedor** | `invitacio.estat='caducada'` (timeout 14d, automàtic) | Re-contacte lleuger a 90 dies (esglaó 3) |
| 7 | **Sense Instagram** | `instagram_url = ''` — mai coneguda O buidada per `_marca_handles_rebutjats` quan Meta refusa (l'antiga queda a `instagram_rebutjat_url`) | Apareixen a la cua staff `/staff/artistes/sense-instagram`; en posar-hi URL reentren al funnel |

Els topats amb IG que mai han sigut invitats ni sondejats queden fora
de la taxonomia del funnel (reben mencions passives setmanals; el seu
camí és la invitació feed directa als posts del top).

Transicions clau: 4→3→(2|5) via sonda · 2→3→(1|6) via invitació ·
5→3 via re-sonda · 6→3 via re-sonda lleugera · qualsevol→7 quan Meta
refusa el handle · 7→4 quan staff posa URL des de la cua. L'únic
estat terminal és l'1 (col·laborador); el 7 és reversible pel
workflow staff existent. El rebuig explícit d'invitació NO és cap
estat: no es registra a la pràctica (0 usos) — un "no" real es
manifesta com a caducada (estat 6).

## 6. El registre — com s'apunta la receptivitat

Ja tenim el ground truth final (`InvitacioColaboracioIG`). Falta el
graó intermedi. Proposta: **model nou lleuger** `SondaStoryIG`:

- `artista` FK, `data`, `story_media_id`, `canco` FK
- `reach` (snapshot; és l'ÚNICA mètrica viva per a stories de
  comptes UE — shares/impressions no existeixen i replies retorna
  sempre 0 per privadesa; copiat a T+48h)
- `reaccio_auto` (calculada pel detector §2: outlier de reach o
  replies>0) + els valors de la línia base usada (mediana/MAD) per a
  auditar el criteri a posteriori
- `reaccio_manual` (OPCIONAL, si un dia es vol matisar des d'una card
  staff; el bucle NO en depén)

La **cua prioritària d'invitació feed** es forma automàticament amb
els `reaccio_auto=True`. La conversió en invitació real usa el flux
existent de col·laboradors: es materialitza quan l'artista apareix al
següent post de feed (típicament nous singles/àlbums amb la seua
novetat). Nota honesta: un artista sondejat-reactiu que no traga mai
més música pot no tindre moment natural d'invitació — acceptem el
degoteig o s'invita a mà puntualment.

Per què model propi i no camps a `Artista`: la sonda és un esdeveniment
amb data i mètriques (historial, cooldowns futurs, anàlisi de cohorts),
no un estat de l'artista.

## 7. El bucle complet

```
[pool 304] --2/setmana--> story «cançó del dia» amb menció
     |                          |
     |            automàtic: replies/shares/reach (cron existent)
     |            manual: reshare/DM vist a l'app → card staff
     |                          |
     v                          v
 mai repetit              SondaStoryIG.reaccio != cap
                                |
                                v
                  cua prioritària d'invitació feed
                  (InvitacioColaboracioIG — flux existent)
                                |
                                v
              KPI: % acceptació cohort sondejada-receptiva
                   vs el ~6% de línia base actual
```

## 8. Contingut i renderer

- Nova slide de story (1080×1920): gramàtica del **hero** reutilitzable
  (caràtula gran + títol Bricolage + artista) amb kicker propi — p.ex.
  «LA CANÇÓ DEL DIA» + subtítol editorial «fora del top» (coherent amb
  el kicker «FORA DEL TOP · ESTRENES» que ja usa la slide de novetats).
  Tokens nous a `story-tokens.json`; un builder o paràmetres del hero.
- Menció: `user_tags` amb la maquinària existent (`_norm_tag` +
  guard de substitució). **De pas**: si el guard descarta el handle
  (perfil privat/invàlid), estampar `instagram_rebutjat_at` com ja fa
  el feed (`_marca_handles_rebutjats`) — cada sonda fallida neteja el
  pool.
- Nou `SocialPost.TIPUS_CANCO_DIA` + slots dt/dj/dv/dg ×2 + toggle
  `ConfiguracioGlobal.canco_dia_actiu` (patró moviment_actiu: inert
  fins que s'activa) + gate a la MatriuPublicacio.

**Dues costures d'infraestructura que el ritme 2/dia obliga a tocar**
(verificades al codi, ambdues additives):

1. **Clau d'idempotència**: `SocialPost.unique_together = (platform,
   tipus, territori, setmana)` és SETMANAL — 8 sondes/setmana del
   mateix tipus xocarien. Fix: afegir un camp discriminador
   `slot_key` (CharField, default `""`) a la unique_together; les
   files existents queden amb `""` → clau idèntica, zero canvi de
   comportament. Les sondes usen `slot_key="<data>-mati|vesprada"`.
   Migració additiva sense backfill.
2. **Cron intradia**: `publicar_social` corre UNA vegada al dia
   (11:30 UTC). Les franges demanen: camp `franja` a `CalendarSlot`
   (`""` per als existents) + argument `--franja` al command (default
   `""` = run principal, no toca les sondes) + dues línies de cron
   noves (p.ex. 07:00 UTC ≈ 09:00 CEST matí; 16:00 UTC ≈ 18:00 CEST
   vesprada) + entrades a cron-meta. El run de les 11:30 queda
   byte-idèntic.
- Caption/overlay: cap caption a stories; el text va a la imatge.
  Enllaç «topquaranta.cat» al footer com la resta.

## 9. Riscos i mitigacions

| Risc | Mitigació |
|---|---|
| Semblar spam per a Meta | 1 menció/story, 2/setmana — molt per davall de qualsevol cap; el guard ja tolera rebuigs |
| Handle privat/invàlid | guard existent publica sense menció + estampar rebutjat (pool es neteja sol) |
| Cançó «fluixa» fa quedar malament la marca | tria per playcount màxim del catàleg de l'artista; el marc editorial «fora del top» posa expectatives |
| Esgotar VAL/BAL | quota suau §5.3 |
| Falsos positius del detector d'outliers | cost = una invitació de més; llindar 3·MAD ajustable amb les primeres setmanes de dades |
| El pool s'esgota (~9 mesos) | vàlvules ordenades del §4: re-sondes 12m → caducades +90d → abaixar ritme |
| Diumenge sense cron de publicació? | `publicar_social` corre CADA dia (cron diari 11:30 UTC) — només cal el slot al calendari |

## 10. Mesura d'èxit

- **Primari**: taxa d'acceptació d'`InvitacioColaboracioIG` de la
  cohort «sondejada amb reacció» vs la línia base (~6% actual). Si no
  la supera clarament en ~2 mesos de dades, la sonda no prediu i cal
  repensar.
- Secundaris: % de sondes amb reacció (qualsevol); creixement del
  registre; reach de les stories-sonda vs stories de top (salut del
  format).

## 11. Esbós d'implementació (quan es vulga)

1. **PR 1 — motor**: model `SondaStoryIG` + migració; selector
   (service amb tests de diversitat/elegibilitat); tipus nou +
   calendari + toggle; renderer slide + tokens; tagger + rebutjats.
   És el gros (~1 sessió).
2. **PR 2 — registre visible**: card staff de sondes + snapshot de
   mètriques T+48h + cua prioritària visible a la vista de
   col·laboracions.
3. **Activació**: toggle on; primera sonda el diumenge següent.

Dependència externa: cap — tot amb la Graph API que ja usem.
