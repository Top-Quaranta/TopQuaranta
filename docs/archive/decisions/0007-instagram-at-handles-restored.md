# ADR-0007 — Restituïr `@username` al text de la caption d'Instagram

- **Status:** Accepted
- **Date:** 2026-05-21
- **Authors:** Miquel

## Context

A la Fase 1 (2026-05-16) `social/captions.py::_artist_label(entry,
*, use_handle)` ja distingia el mode "long" d'Instagram (emet
`@handle` quan hi ha `artista_instagram_url`) del mode "short"
dels altres 4 canals (Mastodon, Bluesky, Telegram, Newsletter,
que emeten el nom pla). Aquell raonament continua sent vàlid: cada
xarxa té sintaxi de menció diferent (`@user@instance`,
`@user.bsky.social`, etc.) i no guardem handles per cada xarxa.

A la Fase 4 (motor narratiu, 2026-05-18) els composers per canal
s'apoyen ja no en `captions.py` sinó en els bancs de plantilles
(`social/narrative/banks/`), que reben les entrades del top en
brut amb `artista_nom` ja com a nom pla. La conseqüència és que
el composer d'Instagram va perdre el `@handle`: el text emès era
sempre amb nom pla. L'artista deixa de rebre la notificació
d'IG i no podem aprofitar el seu enllaç clicable.

## Decision

Modificar el composer `social/narrative/composers/instagram_feed.py`
per a:

1. Reescriure `Scenario.data["artista"]` (i les tres variants
   preposicionals `de_artista`, `per_a_artista`, `per_artista`) a
   `@handle` quan l'artista té `instagram_url`. La lookup és per
   match exacte de nom contra `entries` (que carreguen
   `artista_instagram_url`). Sense URL → no canvi.
2. Per a cada entry del top 5 que arriba al `top5_bank`, una
   còpia superficial amb `artista_nom` reescrit a `@handle` si
   està disponible.

Els bancs (`hero`, `top5`) queden agnòstics: només llegeixen
`artista_nom`/`{artista}`/`{de_artista}`. Cap canvi a `captions.py`
ni als altres composers.

`@handle` no contraeix ni elideix preposicions; emetem la forma
recta (`de @handle`, `per a @handle`, `per @handle`) directament.

## Alternatives considerades

- **Reescriure els bancs amb un paràmetre `mention_style`** —
  duplica plantilles i degrada la claredat dels bancs. Descartada.
- **Treure `@handle` també a IG i mantenir només noms plans** —
  perd la notificació a l'artista i un enllaç clicable que sí
  funciona. La Fase 1 ja havia validat el `@handle` a IG;
  desfer-ho seria una regressió.
- **Resoldre el handle a tots els canals via lookup per canal** —
  costa una nova taula `ArtistaHandleSocial(canal, handle)` per a
  un benefici marginal (cobertura d'IG handles avui = 8,2 %; les
  altres xarxes serien encara menys). Costa més del que aporta.

## Consequences

- ✅ El text de la caption d'IG torna a fer `@handle` quan l'artista
  el té; clicable + notifica l'artista.
- ✅ Tres tests nous (`social/tests/test_instagram_handles.py`):
  IG substitueix, IG retorna a nom pla sense handle, Mastodon i
  Bluesky no produeixen mai `@handle` (anti-regressió).
- ⚠️ El composer ara crea còpies de `Scenario` per al hero i el
  secondary. Memòria extra negligible (un dict superficial).
- ✅ Els bancs queden channel-agnostic — el canal-específic viu al
  composer, que és el lloc correcte.

## Related

- ADR-0006 — Ordinals catalans (mateix sprint)
- ADR-0008 — Detectors a9–a12 (mateix sprint)
- Decisió Fase 1 (2026-05-16) — `captions.py::_artist_label` amb
  `use_handle` parameter.
