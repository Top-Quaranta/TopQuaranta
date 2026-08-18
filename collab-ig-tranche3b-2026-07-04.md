# IG col·laboradors — tranche 3b (ADR-0015) — 2026-07-04 (referència local)

Nota local (no committada). Sessió supervisada amb Miquel.

## Fet en aquesta sessió

1. **Fix del forat dels pendents eterns** desplegat a main **`8fd104d`**
   (PR #309): estat `caducada` a `InvitacioColaboracioIG` (migració
   additiva `social/0008`); el poller marca com a caducada les pendents de
   fa >14 dies (amb `data_resolucio`); la política tracta `caducada` com
   `rebutjada` (categoria C, cooldown 90 dies); la taxa d'acceptació la
   compta com a no-acceptació. main == prod verificat.
2. **Flag activat**: `ig_collaboradors_actiu = True`, via el PATCH real de
   `/staff/configuracio/` (camí normal de staff). Persistit a prod (lectura
   fresca de DB = True) i **audit-logat**: `config_update` per
   `miquelmatoses` a **2026-07-04 10:44:22 UTC**, diff `False→True`.

## ⚠️ Realitat de temps (important) — la tanda de dissabte ja havia sortit

- El cron de dissabte (`30 9 * * 6`, **09:30 UTC**) va publicar el
  `top_ppcc` d'avui a **09:31:28 UTC** (media **`18056376584768251`**,
  setmana 2026-06-29), amb `delay_instagram_min=0`.
- El flag es va activar a **10:44 UTC**, ~75 min DESPRÉS. Per tant el post
  de dissabte va sortir **SENSE col·laboradors** (flag encara False a les
  09:31). `InvitacioColaboracioIG` continua amb **0 files**.
- La "primera tanda real" que esperàvem al cron de dissabte **no ha portat
  col·laboradors**. No s'ha disparat res manualment (correcte).

## Primera tanda real amb col·laboradors → propera publicació de feed

- Pròxim cron de feed després d'ara (Ds 10:44): **Dilluns 2026-07-06 09:30
  UTC** → `top_territorial` (feed). Serà el **primer post amb el flag
  actiu** i per tant el primer que portarà `collaborators`.
- Caveat: la selecció definitiva es calcularà sobre el chart de la setmana
  corresponent (i, per a territorial, sobre el top del territori que toque
  per rotació). La taula del preflight (rosalia.vt / fadesfadesfades /
  _triquell) era per a `top_ppcc` sobre el chart 2026-06-22 — orientativa.
- Calendari de feed (UTC): Dl/Dc 09:30 top_territorial · **Ds 09:30
  top_ppcc** · Dm 10:00 nous_albums · Dv 10:00 nous_singles.

## Estat tècnic (preflight)

- Token viu, **41 dies** de marge.
- Poller `pollar_colaboracions_ig` instal·lat, horari; ara **actiu** (flag
  on) — reconciliarà quan hi haja invitacions.
- `MetricaPipeline` llest (`ig_collab_taxa_acceptacio`, 0 files encara).
- Registre d'invitacions buit → cold start (tots categoria B) al primer post.

## Sessió d'observació (demà / propera) — reprén Fases 4 i 5 del pla

Quan corra el primer cron de feed amb el flag actiu (Dilluns 09:30 UTC):
- **Fase 4**: monitoritzar el command en viu (container amb `collaborators`,
  guard de substitució sí/no, `media_publish`, escriptura de files
  `InvitacioColaboracioIG`); consultar `GET /{media}/collaborators` del post
  real i **capturar els valors reals d'`invite_status`** i comparar-los amb
  el que espera `reconcile_estat` (si difereixen, reportar amb output cru,
  NO adaptar a cegues); observar si `media_publish` imposa el límit de 3;
  verificar el post visualment (col·laboradors com a pendents, user_tags OK,
  peu correcte).
- **Fase 5**: córrer el poller una vegada; docs si l'API revela res nou;
  passar l'ADR-0015 a **Accepted** si tot va bé; actualitzar aquests
  fitxers amb la primera tanda real; vigilar taxa d'acceptació i caducitats
  als 14 dies.

## ADR-0015: estat = **Proposed** (encara). Passa a Accepted després de la
primera tanda real observada (sessió d'observació).
