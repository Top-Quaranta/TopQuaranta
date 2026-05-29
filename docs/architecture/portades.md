# Self-hosted covers (`portades`)

> Status: **Fase 2 — ingestion + provisioning + serving** (2026-05-30).
> The pipeline downloads/transcodes covers (Fase 1) and Caddy now
> serves them at `/portades/*`. SPA consumption (Fase 3) and SSR head
> wiring (Fase 4) are still pending — no page references these URLs in
> production yet.

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

### `--limit` semantics

`--limit N` caps the number of **new downloads** per run, NOT the
number of candidates scanned: an already-present cover (its 500px webp
sentinel exists) is skipped **without consuming the budget**. So a
re-run does NOT do nothing — it advances to the next N covers that
still need generating. This is intentional: the nightly cron drains
the backlog ~N/night, never reprocessing what's done. `--force`
bypasses the skip (re-downloads + overwrites atomically) and DOES
consume budget. (Surfaced in the Fase 1 manual validation, where a
plain re-run with the same `--limit` fetched the next batch rather
than reporting all-skipped.)

## Provisioning

`PORTADES_ROOT` (`/var/topquaranta/portades`) lives under `/var`, which
the `topquaranta` user cannot create itself, so the cron would fail
with `EACCES` on first write. It is created **automatically on deploy**
by `bin/tq-sync-infra` (idempotent `install -d -o topquaranta -g
topquaranta -m 755`), alongside the Caddyfile/cron/systemd sync — no
manual `mkdir` required. World-readable (755) so Caddy can serve it.

## Serving

Caddy (`deploy/Caddyfile`, host `www.topquaranta.cat`) serves the
covers from disk:

```
https://www.topquaranta.cat/portades/<entitat>/<deezer_id>-<mida>.<format>
e.g. https://www.topquaranta.cat/portades/album/12345-500.webp
```

- `handle @portades` (`path /portades/*`) → `root */var/topquaranta` +
  `file_server`; the on-disk `portades/` subdir matches the URL prefix,
  so no rewrite.
- **`Cache-Control: public, max-age=31536000, immutable`** — filenames
  are content-addressed, so a generated variant never changes.
- Explicit `Content-Type` per extension (`image/avif|webp|jpeg`) — the
  global `X-Content-Type-Options: nosniff` makes the browser trust it,
  and Go's mime table doesn't reliably know `.avif`.
- **No compression**: images aren't in Caddy's default `encode`
  content-type allowlist, so the host-level `encode zstd gzip` leaves
  them untouched.
- **No directory listing** (no `browse`).
- **Native 404** when a variant hasn't been generated yet — the Fase 3
  frontend will fall back to the Deezer URL.

## Dependencies

- **Pillow** — already pulled by `qrcode[pil]` / `cairosvg`.
- **`pillow-avif-plugin`** — added to `requirements.txt`; registers
  the AVIF encoder on import. The manylinux wheel bundles libavif, so
  no system package is normally required. If building from source
  (no wheel), install `libaom-dev libavif-dev` first.

## Not in this phase

SPA consumption (Fase 3), SSR head/`og:image` (Fase 4), model changes.
See `pipeline.md` for the broader ingest map.
