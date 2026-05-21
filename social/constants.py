"""Shared timing/limits/HTTP constants for the social distribution stack.

Single source of truth for values that were duplicated across the
per-channel client modules. Keep this file small — it should hold
constants that are genuinely cross-cutting, not one-off magic numbers
that belong inside their callsite.
"""

# HTTP timeout for outbound social-API requests (Mastodon, Bluesky,
# Telegram). 60 s is generous on purpose: media-upload responses
# routinely take 20-40 s when the API is busy, and we'd rather wait
# than retry an upload that succeeded server-side. The Instagram
# Graph client uses a tighter 30 s timeout because the Graph API is
# more responsive and aggressive retries are safer there.
HTTP_TIMEOUT_S = 60


# Bluesky `uploadBlob` against `bsky.social` PDS for 4-PNG carousels
# (~1 MB each) is marginal at 60 s — five publications dropped in one
# week (post-mortem 2026-05-21-bluesky-silent-failures.md). Bumped to
# 180 s with the retry helper below. Vegeu ADR-0005.
BLUESKY_UPLOAD_TIMEOUT_S = 180
BLUESKY_UPLOAD_RETRIES = 3
# Back-off seconds between retries (1st → 2nd → 3rd attempt).
BLUESKY_UPLOAD_BACKOFF_S = (5, 15)


# ── Renderer layout primitives ───────────────────────────────────────
#
# Numeric anchors shared across slide kinds so the visual rhythm stays
# coherent. A bump to `LIST_ROW_HEIGHT` ripples to every list-style
# slide (territorial top + novetats singles + future variants).
#
# Rationale for the chosen values is in the readability v2/v3 audit
# trail at `_feed_list_slide` (May-2026 sprint).

# Pixels between the start of two consecutive cards in a list slide.
# 105 = 76 px card height + 29 px gap.
LIST_ROW_HEIGHT = 105

# Y-coordinate of the first row's top edge in a list slide.
# Leaves room for the 60 px header + 8 px accent rule + 32 px gap.
LIST_TOP_Y = 170
