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

Body note: the public feed renders `Publicacio.cos` as markdown
(`react-markdown`, which never emits raw HTML) and previews it via
`stripMarkdown`. The newsletter stores `narrative_html` (HTML), which would
render broken in both. So the bridge stores a **plain-text** rendition of the
narrative (HTML stripped). This is lossy (links/formatting dropped) but renders
correctly and safely. The richer options (vendoring an HTML→markdown step, or
composing markdown from the structured top) are a product decision — see the PR.
"""

from __future__ import annotations

import html
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from comptes.models import NewsletterDraft, Publicacio


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


_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_END_RE = re.compile(r"(?i)</(p|div|h[1-6]|li|tr|table|ul|ol)>")
_BR_RE = re.compile(r"(?i)<br\s*/?>")


def _html_to_text(raw: str) -> str:
    """Minimal, dependency-free HTML → plain text: block ends and <br>
    become newlines, all other tags are dropped, entities are unescaped,
    and whitespace is collapsed. Good enough for a feed body; not a parser."""
    if not raw:
        return ""
    s = _BR_RE.sub("\n", raw)
    s = _BLOCK_END_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return "\n".join(line.strip() for line in s.splitlines()).strip()


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

    body = _html_to_text(draft.narrative_html) or draft.subject
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
