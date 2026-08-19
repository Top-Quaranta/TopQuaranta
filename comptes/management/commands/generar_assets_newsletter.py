"""Generate the newsletter's raster brand assets (run-once).

Email clients don't render SVG, so the header logo and the cover
placeholder are committed PNGs rasterised from the vendored brand SVG
(`vendor/mm-design/icons/brand/logo-topquaranta-rect.svg`) via the same
`social.svg_assets` rasteriser the Instagram renderer uses.

Outputs (committed to the repo, served at /static/…):
  * web/static/web/img/newsletter/cover_placeholder.png
        500×500, ink #0a0a0a background, white brand logo centred.
  * web/static/web/img/newsletter/logo_email.png
        ~440 px wide, full-colour brand logo on transparent background.

Re-run with `manage.py generar_assets_newsletter` after a logo refresh.
"""

# Spec: docs/architecture/comptes.md

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image

OUT_DIR = Path(settings.BASE_DIR) / "web" / "static" / "web" / "img" / "newsletter"
INK = (10, 10, 10)  # #0a0a0a


class Command(BaseCommand):
    help = "Generate the newsletter cover placeholder + header logo PNGs."

    def handle(self, *args, **opts):
        from social import svg_assets

        OUT_DIR.mkdir(parents=True, exist_ok=True)

        # ── Cover placeholder: 500×500 ink + white logo centred ──────
        logo_white = svg_assets.logo_image_mono(width=340, fill="#ffffff")
        if logo_white is None:
            raise CommandError("cairosvg unavailable or logo SVG missing.")
        canvas = Image.new("RGB", (500, 500), INK)
        lx = (500 - logo_white.width) // 2
        ly = (500 - logo_white.height) // 2
        canvas.paste(logo_white, (lx, ly), logo_white)
        placeholder = OUT_DIR / "cover_placeholder.png"
        canvas.save(placeholder, "PNG")
        self.stdout.write(f"✓ {placeholder} ({canvas.size})")

        # ── Header logo: full-colour brand mark, transparent bg ──────
        logo_color = svg_assets.logo_image(width=440)
        if logo_color is None:
            raise CommandError("cairosvg unavailable or logo SVG missing.")
        header = OUT_DIR / "logo_email.png"
        logo_color.save(header, "PNG")
        self.stdout.write(f"✓ {header} ({logo_color.size})")
