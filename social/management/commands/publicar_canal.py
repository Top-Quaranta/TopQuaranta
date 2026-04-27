"""Publish the same weekly content to a non-Instagram channel.

Channels supported (selected via `--channel`):
  mastodon   — toot on the configured instance
  bluesky    — feed post on bsky.social
  newsletter — HTML email to all `Usuari.vol_newsletter=True`

Each channel reuses the existing renderer + payload pipeline so the
caption / artwork stays in sync with what Instagram posts. The
SocialPost row keys off `(platform, tipus, territori, setmana)` so
re-runs are idempotent — the staff Reset/Esborrar buttons work the
same way as for Instagram.

Phase gating is **not** applied here: those phases are an
Instagram-only roll-out plan. Mastodon/Bluesky/newsletter are
either on (config kill-switch True) or off, no gradient. Each has
its own switch in `ConfiguracioGlobal`.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from ingesta.social import (
    bluesky_client,
    captions,
    mastodon_client,
    payload,
    renderer,
    telegram_client,
)
from ingesta.social.calendari import slots_for, tq_week_start
from music.audit import log_staff_action
from ranking.models import ConfiguracioGlobal
from social.models import SocialPost

logger = logging.getLogger(__name__)

CHANNELS = ("mastodon", "bluesky", "telegram", "newsletter")


class Command(BaseCommand):
    help = "Publica al canal indicat (mastodon | bluesky | newsletter)."

    def add_arguments(self, parser):
        parser.add_argument("--channel", required=True, choices=CHANNELS)
        parser.add_argument("--data", default=None)
        parser.add_argument("--tipus", default=None)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **opts):
        channel = opts["channel"]
        data = opts.get("data")
        target = datetime.date.fromisoformat(data) if data else datetime.date.today()
        cfg = ConfiguracioGlobal.load()
        switch = {
            "mastodon": cfg.mastodon_actiu,
            "bluesky": cfg.bluesky_actiu,
            "telegram": cfg.telegram_actiu,
            "newsletter": cfg.newsletter_actiu,
        }[channel]
        if not switch and not opts["dry_run"]:
            self.stdout.write(f"Kill switch tancat ({channel}_actiu=False). Surt.")
            return

        slots = slots_for(target)
        if opts.get("tipus"):
            slots = [(s, t) for (s, t) in slots if s.tipus == opts["tipus"]]
        # We only push **feed** content (not stories) to the
        # non-Instagram channels — stories are an IG-native format.
        slots = [
            (s, t)
            for (s, t) in slots
            if s.platform == SocialPost.PLATFORM_INSTAGRAM_FEED
        ]
        if not slots:
            self.stdout.write(f"Cap slot per a {target}.")
            return

        sat = tq_week_start(target)
        setmana = sat - datetime.timedelta(days=sat.weekday())
        for slot, territori in slots:
            self._handle(channel, slot, territori, setmana, target, opts)

    # ── per-slot ─────────────────────────────────────────────────

    def _handle(self, channel, slot, territori, setmana, target, opts):
        platform = {
            "mastodon": SocialPost.PLATFORM_MASTODON,
            "bluesky": SocialPost.PLATFORM_BLUESKY,
            "telegram": SocialPost.PLATFORM_TELEGRAM,
            "newsletter": SocialPost.PLATFORM_NEWSLETTER,
        }[channel]
        label = f"{platform} · {slot.tipus} · {territori or '—'}"
        self.stdout.write(f"\n[setmana {setmana}] {label}")
        post, _ = SocialPost.objects.get_or_create(
            platform=platform,
            tipus=slot.tipus,
            territori=territori or "",
            setmana=setmana,
            defaults={
                "status": SocialPost.STATUS_PENDENT,
                "scheduled_at": timezone.now(),
            },
        )
        if post.status == SocialPost.STATUS_PUBLICAT and not opts["force"]:
            self.stdout.write("  · ja publicat (--force per re-publicar). Salta.")
            return

        # Build payload + cover render (slide 0 of the IG carousel).
        if slot.tipus in (SocialPost.TIPUS_TOP_PPCC, SocialPost.TIPUS_TOP_TERRITORIAL):
            data = payload.build_top(territori, setmana)
        else:
            data = payload.build_novetats(slot.tipus, setmana, publish_date=target)
        if not data:
            self._mark(post, SocialPost.STATUS_OMES, error_msg="cap contingut")
            self.stdout.write("  · sense contingut → omès")
            return

        if slot.tipus in (SocialPost.TIPUS_TOP_PPCC, SocialPost.TIPUS_TOP_TERRITORIAL):
            paths = renderer.render_feed_top(
                slot.tipus, territori, setmana, data["entries"]
            )
            entries = data["entries"]
        else:
            paths = renderer.render_feed_novetats(slot.tipus, setmana, data["items"])
            entries = data["items"]

        cover = paths[0]  # the portada slide
        # Channel-specific caption length cap. Telegram allows 1024
        # chars on a media caption; we leave headroom by capping
        # `caption_short` lower so future link/utm additions fit.
        max_chars = {
            "mastodon": 480,
            "bluesky": 280,
            "telegram": 900,
            "newsletter": 9999,
        }[channel]
        text = captions.caption_short(
            slot.tipus, territori, setmana, entries, max_chars=max_chars
        )

        if opts["dry_run"]:
            self._mark(
                post,
                SocialPost.STATUS_PENDENT,
                metadata={
                    "dry_run": True,
                    "channel": channel,
                    "cover": cover.name,
                    "text": text,
                },
            )
            self.stdout.write(f"  · --dry-run\n  text: {text[:120]}…")
            return

        try:
            if channel == "mastodon":
                ext_id = self._publish_mastodon(cover, text, slot, territori, entries)
            elif channel == "bluesky":
                ext_id = self._publish_bluesky(cover, text, slot, territori, entries)
            elif channel == "telegram":
                ext_id = self._publish_telegram(paths, text, slot, territori, entries)
            else:  # newsletter
                ext_id = self._publish_newsletter(
                    slot, territori, setmana, target, entries, data
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("publicar_canal failed for %s", label)
            self._mark(post, SocialPost.STATUS_ERROR, error_msg=str(exc)[:500])
            self.stdout.write(f"  · ERROR: {type(exc).__name__}: {exc}")
            return

        self._mark(
            post,
            SocialPost.STATUS_PUBLICAT,
            instagram_media_id=ext_id[:80],
            metadata={"channel": channel, "external_id": ext_id, "cover": cover.name},
            published_at=timezone.now(),
        )
        log_staff_action(None, f"{channel}_publicat", target=post, tipus=slot.tipus)
        self.stdout.write(f"  · publicat → {ext_id}")

    # ── per-channel publish ──────────────────────────────────────

    def _publish_mastodon(self, cover: Path, text, slot, territori, entries) -> str:
        media_id = mastodon_client.upload_media(
            cover, alt_text=f"Top — {territori or 'Global'}"
        )
        return mastodon_client.post_status(text, media_ids=[media_id])

    def _publish_telegram(self, paths, text, slot, territori, entries) -> str:
        # Telegram fits up to 10 photos in one media-group message,
        # so we send the whole carousel — richer than the cover-only
        # treatment Mastodon/Bluesky get.
        from social.management.commands.publicar_social import _public_url_for

        urls = [_public_url_for(p) for p in paths[: telegram_client.MEDIA_GROUP_MAX]]
        return telegram_client.send_media_group(urls, caption=text)

    def _publish_bluesky(self, cover: Path, text, slot, territori, entries) -> str:
        blob = bluesky_client.upload_blob(cover)
        return bluesky_client.create_post(
            text,
            image_blobs=[blob],
            alt_texts=[f"Top — {territori or 'Global'}"],
        )

    def _publish_newsletter(
        self, slot, territori, setmana, target, entries, data
    ) -> str:
        from comptes.newsletter import send_top_newsletter

        return send_top_newsletter(slot.tipus, territori, setmana, target, entries)

    # ── mark helper ──────────────────────────────────────────────

    def _mark(
        self,
        post,
        status,
        *,
        instagram_media_id="",
        metadata=None,
        error_msg="",
        published_at=None,
    ):
        post.status = status
        if instagram_media_id:
            post.instagram_media_id = instagram_media_id
        if metadata is not None:
            post.metadata = metadata
        if error_msg:
            post.error_msg = error_msg
        if published_at is not None:
            post.published_at = published_at
        post.save()
