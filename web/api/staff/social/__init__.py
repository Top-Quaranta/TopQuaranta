"""Staff endpoints to monitor + control the social distribution.

  GET  /api/v1/staff/social/                — list of SocialPost rows
  POST /api/v1/staff/social/preview/        — render dry-run for a slot,
                                              returns the URLs of the
                                              freshly generated PNGs
  POST /api/v1/staff/social/publicar-ara/   — force-run publicar_social
                                              for a (data, tipus, platform)
                                              triple
  POST /api/v1/staff/social/toggle/         — flip ConfiguracioGlobal
                                              .instagram_actiu
  POST /api/v1/staff/social/fase/           — set ConfiguracioGlobal
                                              .fase_distribucio
  POST /api/v1/staff/social/story-cap/      — set ConfiguracioGlobal
                                              .story_max_cancons_ppcc
  GET  /api/v1/staff/social/token-status/   — days until token expires

All require IsStaff (the existing permission that the rest of the
staff endpoints already use, mounted by `staff_views`).
"""

from ._common import _serve_png
from .accounts import (
    social_bluesky_clear,
    social_bluesky_save,
    social_bluesky_test,
    social_credentials_clear,
    social_credentials_save,
    social_credentials_test,
    social_mastodon_clear,
    social_mastodon_save,
    social_mastodon_test,
    social_telegram_clear,
    social_telegram_save,
    social_telegram_test,
)
from .controls import social_delay, social_fase, social_story_cap, social_toggle
from .posts import (
    social_eliminar_instagram,
    social_eliminar_remot,
    social_list,
    social_preview,
    social_preview_all,
    social_publicar_ara,
    social_render_serve,
    social_republicar,
    social_reset,
    social_slides_for,
)

__all__ = [
    "social_list",
    "social_credentials_save",
    "social_credentials_test",
    "social_credentials_clear",
    "social_mastodon_save",
    "social_mastodon_test",
    "social_mastodon_clear",
    "social_bluesky_save",
    "social_bluesky_test",
    "social_bluesky_clear",
    "social_telegram_save",
    "social_telegram_test",
    "social_telegram_clear",
    "social_slides_for",
    "social_render_serve",
    "social_preview",
    "social_preview_all",
    "social_publicar_ara",
    "social_reset",
    "social_eliminar_instagram",
    "social_eliminar_remot",
    "social_republicar",
    "social_toggle",
    "social_fase",
    "social_story_cap",
    "social_delay",
    "_serve_png",
]
