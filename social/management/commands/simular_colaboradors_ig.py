"""Dry-run the IG collaborator slot policy — read-only, sends nothing.

# Spec: docs/archive/decisions/0015-ig-collaborator-invitations.md §5.2

Builds the real candidate pool for one or more feed posts (default: the
latest weekly PPCC top + this week's novetats), applies the slot policy
against the live `InvitacioColaboracioIG` registry + config, and prints
what WOULD be invited — the pool, each artist's category + eligibility,
the ≤3 selected, and who is discarded (cooldown / no username).

Works with `ig_collaboradors_actiu` **False**: it's a read-only
simulation, independent of the publish gate. Writes nothing, calls no
API.
"""

from __future__ import annotations

import datetime
import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from music.models import Artista
from ranking.models import ConfiguracioGlobal, TopSetmanal
from social import collaboradors as C
from social import payload
from social.models import InvitacioColaboracioIG, SocialPost


class Command(BaseCommand):
    help = "Simula (dry-run) la política de col·laboradors IG. No envia ni escriu res."

    def add_arguments(self, parser):
        parser.add_argument("--tipus", default=None, help="Restrict to one tipus.")
        parser.add_argument("--territori", default="PPCC", help="Top territori.")
        parser.add_argument("--data", default=None, help="Publish date (YYYY-MM-DD).")
        parser.add_argument("--json", action="store_true", help="Emit JSON.")

    def handle(self, *args, **opts):
        cfg = ConfiguracioGlobal.load()
        config = C.PolicyConfig.from_config(cfg)
        now = timezone.now()
        publish_date = (
            datetime.date.fromisoformat(opts["data"])
            if opts.get("data")
            else datetime.date.today()
        )
        setmana = (
            TopSetmanal.objects.filter(territori="PPCC")
            .order_by("-setmana")
            .values_list("setmana", flat=True)
            .first()
        )

        # Which posts to simulate.
        if opts.get("tipus"):
            targets = [(opts["tipus"], opts["territori"])]
        else:
            targets = [
                (SocialPost.TIPUS_TOP_PPCC, "PPCC"),
                (SocialPost.TIPUS_NOUS_ALBUMS, ""),
                (SocialPost.TIPUS_NOUS_SINGLES, ""),
            ]

        report = {
            "flag_actiu": bool(cfg.ig_collaboradors_actiu),
            "slots_total": cfg.ig_collab_slots_total,
            "slots_efectius": C.effective_slots(config),
            "setmana": setmana.isoformat() if setmana else None,
            "posts": [],
        }
        for tipus, territori in targets:
            report["posts"].append(
                self._simulate_post(
                    tipus, territori, setmana, publish_date, config, now
                )
            )

        if opts.get("json"):
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self._print(report)

    def _simulate_post(self, tipus, territori, setmana, publish_date, config, now):
        out = {"tipus": tipus, "territori": territori, "candidats": [], "nota": ""}
        if setmana is None:
            out["nota"] = "cap TopSetmanal"
            return out
        if tipus in (SocialPost.TIPUS_TOP_PPCC, SocialPost.TIPUS_TOP_TERRITORIAL):
            data = payload.build_top(territori, setmana)
        else:
            data = payload.build_novetats(tipus, setmana, publish_date=publish_date)
        if not data:
            out["nota"] = "sense contingut"
            return out

        entries = data.get("entries") or data.get("items") or []
        # Ordered, deduped pool (id, username) — same expansion as publish.
        pool: list[tuple[int, str]] = []
        seen: set[int] = set()
        for e in entries:
            for pa in e.get("artistes_pool") or []:
                aid, uname = pa.get("id"), pa.get("username")
                if aid is None or not uname or aid in seen:
                    continue
                seen.add(aid)
                pool.append((aid, uname))

        # Count artists without a username (expanded but no handle) for
        # the report — names from `artistes_noms` minus the pool names.
        names = {
            a.id: a.nom for a in Artista.objects.filter(id__in=[a for a, _ in pool])
        }
        pool_names = set(names.values())
        expanded_names = set()
        for e in entries:
            for n in e.get("artistes_noms") or []:
                if n and n != "—":
                    expanded_names.add(n)
        out["sense_username"] = sorted(expanded_names - pool_names)

        if not pool:
            out["nota"] = "cap artista amb username al pool"
            return out

        historic = self._load_historic([aid for aid, _ in pool])
        pool_objs = [C.PoolArtist(artista_id=aid, username=u) for aid, u in pool]
        selected = C.select_collaborators(pool_objs, historic, config, now=now)
        selected_ids = {s.artista_id for s in selected}

        for aid, uname in pool:
            cat, elig, motiu = C.candidate_status(historic.get(aid, []), config, now)
            out["candidats"].append(
                {
                    "artista": names.get(aid, str(aid)),
                    "username": uname,
                    "categoria": cat,
                    "elegible": elig,
                    "seleccionat": aid in selected_ids,
                    "motiu": ("SELECCIONAT" if aid in selected_ids else motiu),
                }
            )
        out["seleccionats"] = [s.username for s in selected]
        return out

    @staticmethod
    def _load_historic(artista_ids):
        from collections import defaultdict

        hist = defaultdict(list)
        for r in InvitacioColaboracioIG.objects.filter(artista_id__in=artista_ids):
            hist[r.artista_id].append(
                C.InviteRecord(
                    estat=r.estat,
                    data_invitacio=r.data_invitacio,
                    data_resolucio=r.data_resolucio,
                )
            )
        return hist

    def _print(self, report):
        w = self.stdout.write
        w(
            f"Flag actiu={report['flag_actiu']} · slots efectius="
            f"{report['slots_efectius']} · setmana={report['setmana']}"
        )
        for post in report["posts"]:
            w(f"\n=== {post['tipus']} · {post['territori'] or '—'} ===")
            if post.get("nota"):
                w(f"  {post['nota']}")
            if post.get("sense_username"):
                w(
                    f"  sense username ({len(post['sense_username'])}): "
                    f"{', '.join(post['sense_username'][:12])}"
                    + (" …" if len(post["sense_username"]) > 12 else "")
                )
            for c in post.get("candidats", []):
                mark = "✓" if c["seleccionat"] else " "
                w(
                    f"  [{mark}] {c['artista'][:24]:24} @{c['username'][:20]:20} "
                    f"{c['categoria']}  {c['motiu']}"
                )
            if post.get("seleccionats"):
                w(f"  → SELECCIONATS: {', '.join(post['seleccionats'])}")
