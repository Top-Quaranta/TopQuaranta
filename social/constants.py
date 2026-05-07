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
