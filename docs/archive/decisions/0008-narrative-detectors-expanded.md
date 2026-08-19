# ADR-0008 — Quatre detectors narratius nous (a9–a12) i slot terciari al composer d'IG

- **Status:** Accepted
- **Date:** 2026-05-21
- **Authors:** Miquel

## Context

El motor narratiu de Fase 4 oferia 8 detectors (`a1–a8`) que
cobrien les notícies fortes: nou #1, ratxa, caiguda del cim, debut
fort, artista multi-cançó, cançó recent, llarga durada, pujada
forta. La conseqüència és que les setmanes "tranquil·les" (sense
canvi al cim, sense debut a top 3) queien al `fallback_no_event`
amb un text genèric. Això xocava amb la realitat editorial: cada
setmana hi ha moviments al cos del top (debuts a posicions
mitjanes, primers cops absoluts d'un artista, caigudes des de
posicions altes que no eren #1, reaparicions després d'una
absència). El composer s'havia de quedar amb una sola història o
caure al fallback.

Auditat el cicle del 17/05 (post-mortem
`2026-05-20-narrative-engine-collapsed.md`) la conclusió va ser
que el sistema "col·lapsava" a fallback en aproximadament 30 % de
les setmanes/territoris — i això pintava als 5 canals
simultàniament.

## Decision

### 4 detectors nous

| Codi | Resum | Severity | Notes |
|---|---|---|---|
| `a9_debut_anywhere` | Cançó nova a top 4–40 (a4 cobreix top 1–3) | `max(1, (41 - pos) // 8)` (1–5) | Notícia secundària/terciària, no headline |
| `a10_artista_first_ever` | Artista mai abans al top del territori | 8 | Headline candidate quan no hi ha A1/A2 |
| `a11_top5_drop_generic` | Cançó al top 5 (no #1) cau fora del top 10 | 4 + (1 si era al 2n) | Complement d'A3, que només cobreix sortides des del #1 |
| `a12_artista_emerging` | Artista amb cançons aquesta setmana, cap la setmana anterior, però sí en setmanes anteriors | 3 | Diferent d'A10 (first-ever) i d'A9 (és per cançó, no per artista) |

Cada detector segueix el contracte de `Scenario.data`:
preposicions pre-renderitzades, `posicio_ordinal` (ADR-0006),
`territori_label` (PPCC → "Global" per a usuari final).

### Banc de plantilles

Quatre nous bancs (A9, A10, A11, A12) × 3 tiers (short/medium/
long) × 15 entrades cadascuna = **180 plantilles noves**. Mateixa
convenció editorial que els bancs anteriors:

- Català col·loquial periodístic.
- 1–2 emojis per entrada; cap emoji repetit > 2 cops per tier (test
  `test_no_emoji_repeats_more_than_twice_per_bank`).
- Tier `short` ≤ 120 chars després d'interpolar (Bluesky / stories).
- Variables preposicionals ja renderitzades (`{de_artista}`,
  `{per_a_artista}`, `{per_artista}`).
- Cap `#N` (ADR-0006).

### Slot terciari al composer d'IG feed

`social/narrative/composers/instagram_feed.py::compose` accepta ara
**fins a 3 escenes** quan la llista d'escenaris d'entrada en porta
3+:

- **Hero** — `pick_phrase(long)`.
- **Secondary** — `pick_phrase(medium)` (com abans).
- **Tertiary** — `pick_phrase(short)`, escenari nou.

Tots tres s'apliquen el reescriut `@handle` d'ADR-0007. El connector
entre secundari i terciari és independent del primer connector
(`connectors_bank.pick_connector(rng=rng)` per cada slot) per evitar
repetició dins el mateix text.

L'ordre de truncament (quan el text excedeix `MAX_CHARS=2200`) és:

1. Drop tertiary
2. Drop secondary
3. Drop top-5 detail
4. Drop hashtags (un a un)

Els altres composers (Mastodon, Bluesky, Telegram, Newsletter)
**no** reben slot terciari: els seus budgets són massa estrets
(Mastodon 500, Bluesky 300, Telegram 1024) i el cost de mantenir
12 escenaris fits sense col·lisions al registry no compensa per
xarxes amb canvi visual menor.

## Alternatives considerades

- **Slot terciari a tots els canals** — descartat per l'argument
  de budget i registry-saturation anterior.
- **Detectors basats en moviment sumat (climb_total per territori)** —
  útil però redundant amb A2/A4/A8 quan està pluviós i amb
  fallback quan està calmós. Descartat per ara.
- **Detectors basats en festius/efemèrides** — fora d'abast del
  signal Last.fm. Possible Sprint futur amb un Editor manual.
- **Augmentar `fallback_no_event` amb més plantilles** — la
  cobertura editorial millora però la diversitat real (una cara
  nova al top, una caiguda forta des del 2n) no es pot inferir
  des d'un fallback. Calen detectors específics.

## Consequences

- ✅ El motor té ara 12 detectors actius; les setmanes
  "tranquil·les" pugen una notícia A9/A10/A11/A12 abans de caure
  al fallback.
- ✅ Composer d'IG mostra fins a 3 escenes en lloc de 2 —
  riquesa editorial real, no genèric.
- ✅ 180 plantilles noves; `test_each_scenario_has_exactly_three_length_tiers_with_15_entries_each`
  ja valida la simetria.
- ⚠️ La query d'A10 fa un `EXISTS` per cada candidat fila×
  setmana — cost acotat (40 × ~30 ms = 1.2 s al pitjor cas;
  acceptable als sàbats de publicació un cop per territori).
- ⚠️ Severitat d'A11 és relativament baixa per evitar competir
  amb A3 al headline; en setmanes on l'únic moviment és una
  caiguda des del 5è, A11 emergerà com a hero.
- ✅ Anti-regressió: tests verifiquen que els nous bancs no
  contenen `#N` (ADR-0006) i que el composer continua funcionant
  amb només 1 o 2 escenaris (back-compat amb el flux pre-ADR-0008).

## Related

- ADR-0006 — Ordinals catalans (mateix sprint)
- ADR-0007 — `@username` restituït a IG (mateix sprint)
- Post-mortem `docs/post-mortems/2026-05-20-narrative-engine-collapsed.md`
  — motivació editorial original.
