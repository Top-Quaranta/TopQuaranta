"""Newsletter → Community bridge (additive, gated).

# Spec: docs/architecture/comptes.md

Mirrors a `NewsletterDraft` into a PUBLIC community `Publicacio`, authored by
the `admin` pseudo-user. Strictly additive and **gated** by
`ConfiguracioGlobal.newsletter_publicacio_pont_actiu` (default False):

  * While the flag is off, `publicar_draft_a_comunitat` raises
    `PontDesactivat` — nothing is created.
  * It creates ONLY a `Publicacio` row. It never sends an email, never calls
    the social distribution pipeline, and never touches the newsletter send
    flow. "Publishing a real newsletter" and "mirroring to the feed" are
    separate acts.
  * Idempotent: a draft maps to at most one Publicació (`draft.publicacio`).

Body (Miquel's decision, option b): the draft's `narrative_html` is converted
to **markdown** (via `markdownify`) and stored in `Publicacio.cos`. The public
feed renders `cos` with `react-markdown` (+ remark-gfm; never emits raw HTML)
and previews it via `stripMarkdown`, so markdown is the right shape. The
service cleans the ugly cases before storing: images are dropped (decorative /
tracked URLs have no place in a text post), relative links are absolutised to
the public site, and runs of blank lines are collapsed. The result contains no
raw HTML, so it is safe and renders cleanly in both surfaces.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from markdownify import markdownify as _markdownify

from comptes.models import NewsletterDraft, Publicacio

# Default public base for absolutising relative links found in the narrative
# (e.g. `/canco/slug`). Overridable via settings for non-prod environments.
_PUBLIC_BASE = getattr(
    settings, "PUBLIC_SITE_BASE", "https://www.topquaranta.cat"
).rstrip("/")


class PontDesactivat(Exception):
    """Raised when the bridge is invoked while the gate flag is off."""


class AdminInaccessible(Exception):
    """Raised when the `admin` pseudo-user cannot be resolved."""


def pont_actiu() -> bool:
    """True iff the additive bridge gate is on."""
    from ranking.models import ConfiguracioGlobal

    return bool(ConfiguracioGlobal.load().newsletter_publicacio_pont_actiu)


def _admin_user():
    username = getattr(settings, "ADMIN_INBOX_USERNAME", "admin")
    User = get_user_model()
    try:
        return User.objects.get(username=username)
    except User.DoesNotExist as exc:  # pragma: no cover - seeded by migration
        raise AdminInaccessible(f"admin pseudo-user {username!r} not found") from exc


# `[text](/relative)` → absolute (skips already-absolute http(s)/mailto/anchors).
_REL_LINK_RE = re.compile(r"(\]\()(/[^)]*)(\))")
# Defensive: any leftover markdown image (markdownify already strips <img>).
_IMG_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_markdown(raw: str) -> str:
    """Convert newsletter `narrative_html` to clean markdown for the feed.

    Uses `markdownify` (so no raw HTML survives), then cleans the ugly cases:
    images dropped, relative links absolutised to the public site, blank-line
    runs collapsed. Never returns raw HTML tags."""
    if not raw:
        return ""
    md = _markdownify(raw, heading_style="ATX", strip=["img"])
    md = _IMG_MD_RE.sub("", md)
    md = _REL_LINK_RE.sub(
        lambda m: m.group(1) + _PUBLIC_BASE + m.group(2) + m.group(3), md
    )
    md = re.sub(r"\n{3,}", "\n\n", md)
    # Belt-and-braces: strip any stray tag markdownify may have passed through.
    md = _HTML_TAG_RE.sub("", md)
    return md.strip()


@transaction.atomic
def publicar_draft_a_comunitat(
    draft: NewsletterDraft, *, enforce_gate: bool = True
) -> Publicacio:
    """Create (or return the existing) public `Publicacio` for `draft`.

    Gated by `newsletter_publicacio_pont_actiu` unless `enforce_gate=False`
    (tests only). Idempotent. Creates nothing but a `Publicacio` row — no
    email, no distribution, no newsletter send.
    """
    if enforce_gate and not pont_actiu():
        raise PontDesactivat("newsletter_publicacio_pont_actiu is off")

    if draft.publicacio_id:
        return draft.publicacio

    body = _html_to_markdown(draft.narrative_html) or draft.subject
    pub = Publicacio.objects.create(
        autor=_admin_user(),
        titol=draft.subject[:200],
        cos=body[:20000],
        visibilitat=Publicacio.VISIBILITAT_PUBLICA,
        estat=Publicacio.ESTAT_PUBLICAT,
        publicat_at=timezone.now(),
    )
    draft.publicacio = pub
    draft.save(update_fields=["publicacio", "updated_at"])
    return pub
