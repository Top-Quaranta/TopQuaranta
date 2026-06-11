"""Sample generator for the TOP family (committed PNGs for review). No network.
Run: .venv/bin/python social/top_design/render_samples.py"""

import datetime
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "topquaranta.settings.test")
import django  # noqa: E402

django.setup()
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from social import cover_cache, feed_redesign  # noqa: E402
from social import top_redesign as TR  # noqa: E402

OUT = Path("social/top_design/samples")
OUT.mkdir(parents=True, exist_ok=True)
SET = datetime.date(2026, 6, 8)
TINTS = ["#2a2740", "#8a4a1e", "#1f5a63", "#7a2730", "#427c42"]
TERR = ["CAT", "VAL", "BAL", "CNO", "FRA", "AND", "ALG"]


def swatch(url, *a, **k):
    if not url:
        return None
    import re

    m = re.search(r"#?([0-9a-fA-F]{6})", url)
    base = (
        tuple(int(m.group(1)[i : i + 2], 16) for i in (0, 2, 4)) if m else (70, 70, 84)
    )
    arr = np.zeros((300, 300, 3), "uint8")
    arr[:] = base
    return Image.fromarray(arr, "RGB")


def entries(n):
    out = []
    for i in range(1, n + 1):
        pa = None if i in (3, 15, 26) else i + (2 if i % 2 else -1)
        out.append(
            {
                "posicio": i,
                "posicio_anterior": pa,
                "reentrada": i == 26,
                "canco_nom": f"Cançó número {i} de prova llarga",
                "artista_nom": f"Artista {i}",
                "artista_territori": TERR[i % len(TERR)],
                "cover_url": TINTS[i % 5],
            }
        )
    return out


def main():
    cover_cache.fetch = swatch
    e = entries(40)
    TR.build_poster(e, SET, "ppcc").save(OUT / "01_cartell_global.png")
    TR.build_poster(e, SET, "VAL").save(OUT / "02_cartell_valencia_clar.png")
    TR.build_poster(e, SET, "AND").save(OUT / "03_cartell_andorra_fosc.png")
    TR.build_top_cover(SET, "ppcc").save(OUT / "04_portada.png")
    TR.build_top_cover(SET, "VAL").save(OUT / "05_portada_valencia.png")
    TR.build_top_list(list(reversed(e[30:40])), 1, 4, SET, "ppcc").save(
        OUT / "06_llista_40_31.png"
    )
    TR.build_top_list(list(reversed(e[0:10])), 4, 4, SET, "ppcc").save(
        OUT / "07_llista_10_1.png"
    )
    TR.build_top_list(list(reversed(e[0:10])), 4, 4, SET, "VAL").save(
        OUT / "08_llista_valencia.png"
    )
    albums = [
        {
            "nom": f"Àlbum {i} amb títol",
            "artista_nom": f"Art {i}",
            "artista_territori": TERR[i % 7],
            "cover_url": TINTS[i % 5],
        }
        for i in range(9)
    ]
    TR.build_albums_mosaic(albums, SET).save(OUT / "09_mosaic_9.png")
    TR.build_albums_mosaic(albums[:3], SET).save(OUT / "10_mosaic_3.png")
    singles = [
        {
            "nom": f"Single {i}",
            "artista_nom": f"Art {i}",
            "artista_territori": TERR[i % 7],
            "cover_url": TINTS[i % 5],
        }
        for i in range(12)
    ]
    feed_redesign.build_singles(singles[:10], 1, 1, setmana=SET).save(
        OUT / "11_graella_unica.png"
    )
    for p in sorted(OUT.glob("*.png")):
        im = Image.open(p)
        assert im.size == (1080, 1350), (p.name, im.size)
    print("OK — TOP samples:", len(list(OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
