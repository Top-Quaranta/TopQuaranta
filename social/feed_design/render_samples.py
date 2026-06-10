"""Local sample/smoke generator for the feed redesign (NOT committed-for-merge;
lives only on the review branch under social/feed_design/samples via output).

Renders the three redesign builders with deterministic synthetic data, both
with a synthetic cover and with cover=None (fallback tile). No network, no
Spotify. Run: .venv/bin/python _gen_feed_samples.py
"""

import datetime
import os
import sys
from pathlib import Path

# Repo root on sys.path so this works from any cwd / nested location.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "topquaranta.settings.test")
import django  # noqa: E402

django.setup()

from PIL import Image  # noqa: E402

from social import cover_cache, feed_redesign  # noqa: E402

OUT = Path("social/feed_design/samples")
OUT.mkdir(parents=True, exist_ok=True)

SET = datetime.date(2026, 6, 8)  # Monday → TQ week label


def _swatch(seed):
    # Deterministic synthetic cover (no network).
    import numpy as np

    rng = np.random.default_rng(seed)
    base = rng.integers(40, 210, size=(3,))
    arr = np.zeros((300, 300, 3), dtype="uint8")
    arr[:] = base
    return Image.fromarray(arr, "RGB")


def with_cover(seed):
    return lambda url, *a, **k: (_swatch(seed) if url else None)


# Mirrors the Claude Design reference PNGs for side-by-side comparison.
ALBUM = {
    "nom": "Hivern a la Plana",
    "artista_nom": "Les Glaçades",
    "artista_territori": "VAL",
    "cover_url": "x",
}
ALBUM_NOCOVER = {
    "nom": "Camí de Tramuntana",
    "artista_nom": "Vent de Dalt",
    "artista_territori": "CNO",  # Catalunya Nord → fallback tile reference
    "cover_url": None,
}

# With a PPCC row (position 8) — proves the blinding (renders only 9 rows).
SINGLES = [
    {
        "nom": f"Cançó número {i}",
        "artista_nom": f"Artista {i}",
        "artista_territori": code,
        "cover_url": "x",
    }
    for i, code in enumerate(
        ["CAT", "VAL", "BAL", "CNO", "FRA", "AND", "ALG", "PPCC", "CAT", "VAL"], 1
    )
]
# 10 real territories, NO PPCC — full grid for 1:1 comparison with the
# reference singles.png (mirrors its CAT/VAL/BAL/NOR/BAL/FRA/AND/ALG/BAL/VAL).
SINGLES_10 = [
    {
        "nom": nom,
        "artista_nom": art,
        "artista_territori": code,
        "cover_url": "x",
    }
    for nom, art, code in [
        ("Foc d'estiu", "Marès", "CAT"),
        ("La rambla buida", "Quetzal", "CAT"),
        ("L'Albufera", "Nèstor Vidal", "VAL"),
        ("Tramuntana", "Cabanes", "CNO"),
        ("Sal i vent", "Aurora Blau", "BAL"),
        ("Camí de sirga", "Els Pèlags", "FRA"),
        ("Nit andorrana", "Mistral", "AND"),
        ("Carrer de l'Alguer", "Bruna", "ALG"),
        ("Onada curta", "Falç", "BAL"),
        ("Plana endins", "Verdic", "VAL"),
    ]
]
SINGLES_NOCOVER = [{**s, "cover_url": None} for s in SINGLES[:6]]


def main():
    orig = cover_cache.fetch
    saved = []
    try:
        # Covers present.
        cover_cache.fetch = with_cover(1)
        feed_redesign.build_cover("nous_albums", SET).save(OUT / "01_cover_albums.png")
        feed_redesign.build_cover("nous_singles", SET).save(
            OUT / "02_cover_singles.png"
        )
        feed_redesign.build_album(ALBUM).save(OUT / "03_album.png")
        feed_redesign.build_singles(SINGLES, 1, 2, setmana=SET).save(
            OUT / "04_singles_p1of2.png"
        )
        feed_redesign.build_singles(SINGLES[:7], 2, 2, setmana=SET).save(
            OUT / "05_singles_p2of2.png"
        )
        # Fallback (cover == null).
        cover_cache.fetch = lambda url, *a, **k: None
        feed_redesign.build_album(ALBUM_NOCOVER).save(OUT / "06_album_nocover.png")
        feed_redesign.build_singles(SINGLES_NOCOVER, 1, 1, setmana=SET).save(
            OUT / "07_singles_nocover.png"
        )
        # 10 rows, no PPCC — direct 1:1 with reference singles.png.
        cover_cache.fetch = with_cover(2)
        feed_redesign.build_singles(SINGLES_10, 1, 2, setmana=SET).save(
            OUT / "08_singles_10_noppcc.png"
        )
    finally:
        cover_cache.fetch = orig

    for p in sorted(OUT.glob("*.png")):
        im = Image.open(p)
        saved.append((p.name, im.size))
        assert im.size == (1080, 1350), f"{p.name} wrong size {im.size}"
    print("OK — all 1080x1350:")
    for n, s in saved:
        print(f"  {n} {s}")


if __name__ == "__main__":
    main()
