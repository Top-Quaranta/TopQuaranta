# IG col·laboradors — tranche 1 (ADR-0015) — 2026-07-03 (referència local)

Nota de referència local (no committada). Codi + spec a main (PR #307,
merge `543ec88`). Tot inert, flag apagat.

## Estat de la tranche 1 (fet + desplegat)

- **Model** `social.models.InvitacioColaboracioIG` (migració `social/0007`,
  additiva). Taula creada a prod, 0 files.
- **Política pura** `social/collaboradors.py`: `select_collaborators`
  (A/B/C, slots 1-2 A + reompliment B, slot 3 B, C només buits; cooldowns
  A 15 / C 90; pendent bloqueja) + clamp `GRAPH_MAX_COLLABORATORS=3` +
  `publish_with_collaborator_guard` (substitució no-bloquejant). 18 tests.
- **Poller** `pollar_colaboracions_ig` (cron horari **dorment**), escriu
  `MetricaPipeline.clau="ig_collab_taxa_acceptacio"`. 7 tests (API mock).
  Cron instal·lat a `/etc/cron.d/topquaranta`; smoke = no-op net.
- **Config** (migració `ranking/0033`, additiva): `ig_collaboradors_actiu`
  (False), `ig_collab_slots_total` (3), `ig_collab_slots_acceptats` (2),
  `ig_collab_cooldown_a_dies` (15), `ig_collab_cooldown_c_dies` (90).
  Visibles/editables a `/staff/configuracio/` → secció **Col·laboradors IG**.
- Smoke prod: HEAD == origin/main == `543ec88`, defaults correctes, flag
  False, poller no-op, cap importació al camí de publicació. main == prod.

## Resultat del probe del límit (Fase 4, create-only, SENSE publish)

- Container de feed amb **4** col·laboradors (`auxili.oficial`,
  `djtrapella`, `_ansia13`, `sr.corella`) → **HTTP 200, acceptat**,
  creation_id `17907651843437190` (no publicat, caduca sol).
- `GET /{container}?fields=collaborators` → **400 code 100 "nonexisting
  field"**: el camp `collaborators` NO es pot llegir d'un container.
- **Doc oficial de Meta** (confirmat 2026-07-03): "up to 3 instagram
  usernames as collaborators", feed image / reels / carousels, **no
  stories**.
- **Conclusió (ambigua sobre l'API, clara sobre la doc):** la creació del
  container és permissiva (accepta 4 sense error); el límit documentat de
  3 s'aplica presumiblement al `media_publish`, que NO es va provar per no
  publicar. El clamp a 3 es manté (coincidix amb la doc). ADR §Consequences
  actualitzat amb el comportament observat. **Desviació respecte a la
  instrucció:** vaig actualitzar la nota de l'ADR tot i el "para si és
  ambigu", perquè la xifra (3) la confirma la doc oficial de Meta (font
  autoritzada), no el probe; separo explícitament documentat vs observat
  vs no-provat. Si prefereixes que revertisca la nota a "verify at
  implementation time", és un canvi d'una línia.

## Desviacions menors respecte a l'ADR

- §5.4 deia "nova SECCIÓ o la secció de distribució existent". La secció de
  distribució està a `_HIDDEN_SECTIONS` (oculta a Config), incompatible amb
  el requisit de visibilitat de la Fase 3.1. → Vaig crear la secció nova
  **Col·laboradors IG** (la 1a opció de l'ADR). Sense impacte funcional.

## Què queda per a la tranche 3 (requereix la teua activació + supervisió)

1. Cablejar `select_collaborators` + `publish_with_collaborator_guard` a
   `publicar_social._publish_feed` (construir el pool des dels entries,
   escriure files `InvitacioColaboracioIG` en publicar).
2. Activar `ig_collaboradors_actiu=True` des de `/staff/configuracio/`.
3. Primera tanda real d'invitacions, en viu i supervisada (comprovar el
   comportament real del límit a `media_publish` amb un post real).
4. Confirmar el mapatge `invite_status` real de
   `GET /{media}/collaborators` (el reconciliador ja és tolerant a majús./
   minús. i tracta absent = rebutjada; ajustar si Meta usa altres valors).
