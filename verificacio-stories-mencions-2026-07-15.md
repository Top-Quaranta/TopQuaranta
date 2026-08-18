# Verificació stories user_tags — dc 2026-07-15 (PR #323, 1a run real)

> Nota local de referència (untracked), escrita 2026-07-15.
> Només-lectura sobre prod. PR #323 = mencions `user_tags` a TOTES les
> stories del pipeline. Primera execució real: cron `publicar_social`
> de dc 09:30 UTC → set territorial **BAL** (Illes Balears).

## Resultat: net ✅

- **6/6 stories publicades** (`status=publicat`, `error_msg=''`, cap
  `stories_fallides`). setmana DB `2026-07-06`, 6 slides (degradació
  territorial: intro · mosaic 40→11 · grid 10→4 · podi · hero · outro).
- **50 mencions construïdes** (`n_mencions=50` a metadata) =
  reconstrucció exacta via `payload.build_top('BAL', 2026-07-06)` +
  `_story_tags`. **49 efectives** (1 descart correcte del guard).
- Feed germà: media `18329142190283886`.

## Mencions per story (enviades vs esperades)

| # | Slide | media_id | Esperats | Enviats | |
|---|-------|----------|:--:|:--:|--|
| 0 | intro | 18171607861430043 | 0 | 0 | ✓ |
| 1 | mosaic (40→11) | 18614193295023025 | 20 | 20 | ✓ cap 20 saturat |
| 2 | grid (10→4) | 17898468840498969 | 8 | 8 | ✓ |
| 3 | podi (#3,#2) | 17902807065311010 | 20 | **19** | −1 wazooo descartat |
| 4 | hero (#1) | 17984889693040542 | 2 | 2 | ✓ |
| 5 | outro | 17942546406053862 | 0 | 0 | ✓ |

Cap menció fora de la seva slice (les tags surten de les mateixes
`entries` que dibuixa el renderer). On el cap de Meta (20/imatge)
satura — mosaic (26 caràtules dibuixades) i podi (#3 = megacol·labo La
Fúmiga + ~19 artistes) — alguns visibles queden sense menció, **per
disseny documentat**, no defecte.

## Guard: 1r descarte real de la història = @wazooo

- Log 11:32:50 CEST (podi story): 1r intent amb els 20 usernames →
  `IG API 400 code 110/2207018 "Cannot load user with a private
  profile or invalid"`. El guard identifica `wazooo`, el deixa caure,
  reintenta amb 19 → OK. Línia `menció descartada: wazooo (container
  rejected handle)`. Comportament esperat (perfil privat/invàlid).
- Cap altra fallada. `6 stories publicades` sense ⚠.

## Registre d'invitacions de col·laboració (feed, only-feed)

- **Tanda de hui (feed BAL, media 18329142190283886)** — 3, totes
  `pendent`, caduquen **2026-07-29**: @lafumiga (La Fúmiga),
  @abril.totlany (Abril.), @andreu_valor (Andreu Valor).
- **Tanda 06-07** — confirmat, les 3 seguixen `pendent` (`resol=None`),
  caduquen **2026-07-20**: @fadesfadesfades (Fades), @_triquell
  (Triquell), @mariajaume_ (Maria Jaume).
- Total `pendent` a la BD: 11 (06-07 ×3, 13-07 ×3, 14-07 ×2, 15-07 ×3).

## Millora de logging (implementada després de la verificació)

El log i la metadata **no** registraven els usernames enviats per
story (només `n_mencions` agregat + `story_ids`; usernames només en
fallada/descart). Va caldre reconstruir. PR d'observabilitat: una línia
INFO per story a `_publish_story` després de `publish_container`:

```
story 4/6 top_territorial BAL media=<sid> tags=[user1,user2,...]
```

A partir d'ara la verificació és un `grep "story .* tags=" social.log`
en lloc d'una reconstrucció. Cap canvi de payload; usernames només (les
dades ja les teníem). Test: `test_per_story_tags_logged` (amb i sense
mencions).
