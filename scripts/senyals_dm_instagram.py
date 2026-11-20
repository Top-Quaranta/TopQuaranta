"""Turn an Instagram data export into per-account inbox counts.

    python scripts/senyals_dm_instagram.py <export_dir> > senyals.json

Runs where the export is (never on the server) and prints only counts:
`[nom, missatges, mencions, reaccions, ultim]`, one row per account that
did anything. Feed the result to `manage.py importar_senyals_dm`.

# Spec: docs/architecture/social.md
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import re
import sys

NOSALTRES = "Top Quaranta"


def _text(s: str) -> str:
    # Meta's export writes UTF-8 bytes as latin-1 escapes.
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def comptadors(export_dir: str) -> list[list]:
    files = []
    patro = os.path.join(export_dir, "your_instagram_activity/messages/*/*")
    for carpeta in sorted(glob.glob(patro)):
        missatges, nom = [], ""
        for f in glob.glob(os.path.join(carpeta, "message_*.json")):
            with open(f, encoding="utf-8") as fh:
                j = json.load(fh)
            missatges += j["messages"]
            altres = [_text(p["name"]) for p in j["participants"]]
            nom = next((n for n in altres if n != NOSALTRES), "")
        n_text = n_mencions = n_reaccions = 0
        ultim = 0
        for m in missatges:
            nostre = _text(m["sender_name"]) == NOSALTRES
            if nostre:
                n_reaccions += len(m.get("reactions", []))
                continue
            ultim = max(ultim, m["timestamp_ms"])
            story = re.search(
                r"/stories/([^/]+)/", (m.get("share") or {}).get("link", "")
            )
            if story and story.group(1) == "topquaranta":
                n_reaccions += 1  # a reply to one of our stories
            elif m.get("share"):
                n_mencions += 1
            elif m.get("content") and not _text(m["content"]).startswith("Liked a"):
                n_text += 1
        if nom and nom != "Instagram User" and (n_text or n_mencions or n_reaccions):
            dia = datetime.date.fromtimestamp(ultim / 1000).isoformat() if ultim else ""
            files.append([nom, n_text, n_mencions, n_reaccions, dia])
    return files


if __name__ == "__main__":
    json.dump(comptadors(sys.argv[1]), sys.stdout, ensure_ascii=False)
