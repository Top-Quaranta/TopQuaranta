# Self-hosted covers (`portades`)

> Status: **Fase 1 — ingestion only** (2026-05-30). Caddy serving,
> SPA consumption and SSR head wiring are later phases and are NOT
> live yet. Nothing reads these files in production today.

## Why

Album/cançó/artista covers come from Deezer's CDN
(`cdn-images.dzcdn.net`) as 1000×1000 JPEGs. Serving those — even
resized via the `WxH` URL trick — still means a third-party hop and
JPEG-only bytes, a measurable share of mobile LCP (see the LCP audit,
Task 1). Self-hosting lets us serve small **webp/avif** variants from
our own origin and, later, preload the LCP cover.

This phase builds the **download + transcode pipeline only**.

## Layout (state = filesystem, no DB column)

```
<PORTADES_ROOT>/<entitat>/<deezer_id>-<mida>.<format>
e.g.  /var/topquaranta/portades/album/12345-500.webp
```

- `entitat` ∈ `album` | `cancio` | `artista`
- `mida` ∈ `PORTADES_VARIANTS` (250, 500 px — square)
- `format` ∈ `PORTADES_FORMATS` (avif, webp, jpg)

A cover is "present" iff its **500 px webp** sentinel exists. There is
deliberately **no model field**: presence is derived from disk, so the
pipeline is idempotent and needs no migration.

## Settings (`topquaranta/settings/base.py`)

| Setting | Default | Meaning |
|---|---|---|
| `PORTADES_ROOT` | `/var/topquaranta/portades` | filesystem root |
| `PORTADES_VARIANTS` | `[250, 500]` | square sides generated |
| `PORTADES_FORMATS` | `["avif", "webp", "jpg"]` | per variant |
| `PORTADES_DEEZER_SOURCE_SIZE` | `1000` | source size pulled from Deezer (cover_xl) |

## Source URL per entity

The stored Deezer URL is normalised to the source size by rewriting
its `WxH` segment (`/\d+x\d+-/ → /1000x1000-/`), so we always transcode
from the largest cover even if only a 500px URL was stored.

| Entity | deezer_id | image URL |
|---|---|---|
| album | `Album.deezer_id` | `Album.imatge_url` |
| cancio | `Canco.deezer_id` | `Canco.album.imatge_url` (the album cover) |
| artista | `Artista.deezer_id_principal` | `Artista.imatge_url` |

Note: `Artista.imatge_url` is the *custom/uploaded* image — Deezer
artist pictures are not stored on the model, so artistes without a
stored image (or without a principal Deezer id) are skipped.

## Module — `ingesta/portades/`

`manager.py` (filesystem-backed, generic over entity):

- `path_for(entitat, deezer_id, mida, fmt) -> Path` — deterministic
  path; raises `ValueError` on an unknown entitat.
- `exists(entitat, deezer_id) -> bool` — True iff the 500px webp
  sentinel is on disk.
- `download_and_convert(entitat, deezer_id, source_url) -> bool` —
  downloads once, writes every variant×format **atomically**
  (`*.tmp` + rename). Returns True only if ALL variants succeed; on
  any failure cleans up everything it touched and returns False.
  Qualities: avif 70, webp 85, jpg 85; cover-fit via `ImageOps.fit`.
- `delete(entitat, deezer_id) -> None` — purge every variant.

## Command — `descarregar_portades`

```
tq-run descarregar_portades --entitat {album,cancio,artista,all} --limit N [--force]
```

- `--entitat all` iterates album → cancio → artista.
- Skips entities whose 500px webp already exists (disk check, **no
  download**) unless `--force`.
- `--limit` caps the number PROCESSED this run (across entitats).
- Throttles ~0.4 s between downloads; logs progress every 50 and a
  final `found/failed/skipped` line.

### Cron

`deploy/cron.topquaranta`: `0 2 * * * … descarregar_portades --entitat
all --limit 200` → `/var/log/topquaranta/portades.log`. Metadata in
`deploy/cron-meta.json`. (Activated on the next deploy; first run
02:00 UTC.)

## Dependencies

- **Pillow** — already pulled by `qrcode[pil]` / `cairosvg`.
- **`pillow-avif-plugin`** — added to `requirements.txt`; registers
  the AVIF encoder on import. The manylinux wheel bundles libavif, so
  no system package is normally required. If building from source
  (no wheel), install `libaom-dev libavif-dev` first.

## Not in this phase

Caddy serving (Fase 2), SPA consumption (Fase 3), SSR head/`og:image`
(Fase 4), model changes. See `pipeline.md` for the broader ingest map.
