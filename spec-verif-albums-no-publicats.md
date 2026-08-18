# Finding 3 — Artist pages link albums that album_detail 404s

## Hypothesis (as given)
Artist pages link albums that 404 because the albums are discarded or
have no public songs.

## Verdict: **CONFIRMED** (cause is `descartat`, not the inactive-song path)

The artist-page discografia list uses a LOOSER gate than the
`album_detail` endpoint, so it paints albums whose detail page 404s.
Quantified on prod: **11** of 1266 painted albums currently 404. All 11
are `descartat=True`. (The "all songs inactive" sub-case exists in theory
but is currently 0 albums.)

---

## Evidence

### 1. The artist-page albums queryset (the loose gate)

`web/api/artistes_views.py:268-273` (inside `artista_detail`):
```
268    discografia = list(
269        artista.albums.filter(cancons__verificada=True)
270        .prefetch_related("cancons")
271        .distinct()
272        .order_by("-data_llancament")
273    )
```
Filter = `cancons__verificada=True` only. It does NOT filter on
`activa=True` and does NOT exclude `descartat=True`. Each row emits
`{"slug": a.slug, ...}` (line 276) — the SPA links `/album/<slug>`.

### 2. The album_detail endpoint (the tight gate it links to)

`web/api/album_views.py:83-90`:
```
83    album = get_object_or_404(
84        Album.objects.select_related("artista")
85        .filter(cancons__verificada=True, cancons__activa=True)
86        .distinct(),
87        slug=slug,
88        descartat=False,
89        artista__aprovat=True,
90    )
```
Comment at lines 79-82 spells out the contract: "parent artiste approved,
album not discarded, and at least one verified active cançó." Any album
failing this → `get_object_or_404` → **404**.

So the link target requires `descartat=False` AND `≥1 (verificada AND
activa)` cançó; the artist-page list requires neither → mismatch → broken
links.

### 3. Field semantics

- `Album.descartat` (`music/models.py:892-896`): help_text "True if all
  tracks were rejected. Skipped by obtenir_novetats."
- `Canco.objects.public()` (`music/models.py:965-967`): `verificada=True,
  activa=True` — the canonical "visible to the public site / counted by
  the ranking" pair. `album_detail`'s gate matches `.public()`; the
  artist-page list omits `activa`. (Note: neither view actually calls the
  `.public()` manager — both hand-roll the filter; the list just hand-rolls
  a weaker one.)

### 4. Quantification (prod, read-only)

Scope: approved artists (artist pages only exist for approved artists).

ORM run:
```python
painted   = Album.objects.filter(artista__aprovat=True,
                                 cancons__verificada=True).distinct()
servable  = Album.objects.filter(artista__aprovat=True, descartat=False,
                                 cancons__verificada=True,
                                 cancons__activa=True).distinct()
would_404 = set(painted.values_list('id',flat=True)) \
          - set(servable.values_list('id',flat=True))
```
Raw output:
```
painted (loose list):    1266
servable (tight detail): 1255
painted but would 404:   11
  of which descartat=True:                                 11
  of which (not descartat) all verified songs inactive:     0
```
The tightened LIST filter (`descartat=False` + `Count(verificada&activa)>0`)
returns exactly **1255** — i.e. exactly the servable set, no over-hiding.

Reproduction of the 404 for one affected album (`Vèrtic`, id 8695):
```
slug: vertic   descartat: True
album_detail would find it? False  (False => 404)
```

The 11 affected albums:
```
id=6766 descartat=True verif=1 verif+activa=1 'La Balada de David Y Jonatán'
id=7568 descartat=True verif=2 verif+activa=2 'La Dansa de les Flors + Conte'
id=8698 descartat=True verif=6 verif+activa=6 'Retrotopia'
id=8695 descartat=True verif=7 verif+activa=7 'Vèrtic'
id=4975 descartat=True verif=2 verif+activa=2 'Intimate'
id=6898 descartat=True verif=1 verif+activa=1 'Que Le Vaya Bien'
id=5203 descartat=True verif=1 verif+activa=1 'She Can Wait'
id=5210 descartat=True verif=1 verif+activa=1 'Volum a 100'
id=5215 descartat=True verif=1 verif+activa=1 'Hometown'
id=5217 descartat=True verif=1 verif+activa=1 'Naomi Campbell'
id=6933 descartat=True verif=1 verif+activa=1 'Maneres de Viure'
```

---

## Edge cases / risk of over-hiding (honest assessment)

- **"All songs pending" albums**: NOT a regression. The current loose list
  already requires `cancons__verificada=True`, so an album with only
  pending tracks is already not painted. Tightening does not newly hide
  them.
- **Compilations / multi-guest**: the list filter is on this artist's
  `albums` FK (main-artist albums); collaborations are handled separately
  (`artistes_views.py:291-296`) and are unaffected.
- **No over-hiding observed**: tightened list = 1255 = the servable set
  exactly. Every album the tightened rule drops is one album_detail
  already 404s, so the only behavioural change is removing dead links.

### Data-consistency note (flag, not part of the fix)
All 11 affected albums are `descartat=True` YET still carry verified+active
songs (`verif+activa ≥ 1`) — contradicting the field's help_text ("all
tracks were rejected"). So those songs remain public elsewhere (e.g. the
ranking) while their album link 404s. The list-filter fix removes the
broken links; it does NOT reconcile this underlying inconsistency
(album flagged discarded while owning public tracks). That reconciliation
is a separate data-quality question, out of scope for this finding.

---

## Verified spec (do NOT implement)

Tighten the artist-page discografia filter in
`web/api/artistes_views.py:269` so it matches the `album_detail`
indexability gate — "album not discarded, with ≥1 verified+active cançó":

```python
discografia = list(
    artista.albums
    .filter(descartat=False,
            cancons__verificada=True, cancons__activa=True)
    .prefetch_related("cancons")
    .distinct()
    .order_by("-data_llancament")
)
```
(and, for internal consistency, the per-album `n_cancons` at line 282 —
`a.cancons.filter(verificada=True).count()` — should arguably also gate on
`activa=True` to match, though that only affects a displayed count, not a
link.)

Risk: low. Confirmed it drops exactly the 11 albums that already 404 and
nothing else (1266 → 1255 = the servable set). No legitimate album is
hidden by this change.
