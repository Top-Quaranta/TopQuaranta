"""Colour palette for generated Instagram artwork.

Single source of truth — every value here mirrors a token from the
mm-design system or the SPA's `tq-*` aliases. PIL needs literal RGB
values (it can't read CSS variables), so the hex strings are present;
each constant carries a comment naming its source token.

Sprint I prompt called for some Tailwind colours that don't exist in
mm-design (`#1a1a2e` greyish-blue card, `#38bdf8` sky-400 teal,
`#b91c1c` red-700, `#16a34a` green-600). They've been adapted to the
nearest mm-design equivalents so the generated artwork stays on-brand
and a future palette change in mm-design propagates here mechanically.
"""

# Brand surfaces ─────────────────────────────────────────────────────
COLOR_BG = "#0a0a0a"  # tq-ink (SPA `tq-ink`, also the body bg)
COLOR_WHITE = "#ffffff"  # mm-color-white

# Yellow — primary accent
COLOR_YELLOW = "#facc15"  # SPA `tq-yellow`
COLOR_YELLOW_DEEP = "#ca8a04"  # SPA `tq-yellow-deep` — used as the
# secondary accent (e.g. song name) in
# place of the prompt's `#38bdf8` so we
# don't introduce a 4th brand colour.

# Card surfaces sitting on the ink background. mm-design has the
# `mm-color-gray-*` ladder; pick gray-900 / gray-800 (truly neutral)
# instead of the prompt's blueish #1a1a2e/#2a2a3e to avoid a colour
# the rest of the SPA never uses.
COLOR_CARD = "#1f2937"  # mm-color-gray-800
COLOR_CARD_LIGHT = "#374151"  # mm-color-gray-700

# Neutral text — mm-color-gray-* ladder
COLOR_TEXT_MUTED = "#9ca3af"  # mm-color-gray-400 (4.5:1 on COLOR_BG)
COLOR_TEXT_SUBTLE = "#6b7280"  # mm-color-gray-500

# Status colours — brand mm-design tokens
COLOR_SUCCESS = "#427c42"  # mm-color-success (the project's green)
COLOR_DANGER = "#cf3339"  # mm-color-error / red — used for arrow-down

# "NOU" badge
COLOR_NEW = COLOR_YELLOW  # same yellow; reused as the badge fill

# Novetats slide accents — semantic aliases of palette tokens. Aliases
# (not literal hex) so a future palette change propagates and so the
# renderer reads as "novetats: albums accent" instead of an opaque
# "#0047ba". Both happen to coincide with TERR_COLORS values today
# (BAL blue, VAL red) but the meaning is editorial, not territorial —
# kept distinct so we can rebrand without touching territory mappings.
COLOR_NOVETATS_ALBUMS = "#0047ba"  # mm-color-blue
COLOR_NOVETATS_SINGLES = COLOR_DANGER  # red, mm-color-error

# Per-territory accent. Mirrors `TERR_COLORS` from
# `web-react/src/components/editorial.jsx` — keep the two in sync.
# Used to recolour position-number squares, intro headers, and the
# territory icon mask on cover slides.
TERR_COLORS = {
    "PPCC": "#427c42",  # mm-color-green
    "CAT": "#8a6900",  # dark amber (5.08:1 on white)
    "VAL": "#cf3339",  # mm-color-red
    "BAL": "#0047ba",  # mm-color-blue
    "AND": "#7c3aed",  # violet
    "CNO": "#0e7490",  # teal
    "FRA": "#c2410c",  # orange
    "ALG": "#db2777",  # pink
    "ALT": "#525252",
    "CAR": "#525252",
}


# PPCC story redesign palette (Step 3b). These are renderer-only
# editorial tones for the seven-slide PPCC story set; they extend the
# brand surfaces above and are not part of mm-design's public tokens.
COLOR_GREEN_DEEP = "#2f5a2f"  # slide-1 radial gradient end
COLOR_GREEN_LIGHT = "#7bbf7b"  # footer URL, green kickers, novetats rule
COLOR_INK_CENTRE = "#141210"  # radial gradient centre on the ink slides
COLOR_CREAM = "#f3ecdd"  # slide-1 "presenta"


def terr_color(territori: str | None) -> str:
    """Brand colour for a territory; falls back to yellow."""
    return TERR_COLORS.get(territori or "", COLOR_YELLOW)


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def mix(hex_a: str, hex_b: str, t: float) -> str:
    """Linear blend two hex colours. `t=0` → a, `t=1` → b."""
    a = _hex_to_rgb(hex_a)
    b = _hex_to_rgb(hex_b)
    r = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*r)


def darken(hex_str: str, t: float = 0.4) -> str:
    """Mix `hex_str` with ink — useful for tinted card surfaces."""
    return mix(hex_str, COLOR_BG, t)


def best_text_on(hex_str: str) -> str:
    """Pick white or ink based on which gives better contrast on
    `hex_str`. Uses relative-luminance (sRGB), same heuristic the SPA
    uses for badge text colours."""
    r, g, b = _hex_to_rgb(hex_str)

    # Linearise sRGB then weighted sum.
    def _lin(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    L = 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
    return COLOR_WHITE if L < 0.4 else COLOR_BG


# ── Editorial story palette per territory (Step 3c) ──────────────────
#
# The seven-slide editorial story set (intro radial + ink section
# slides) is recoloured per territory. Each palette carries:
#   accent  — radial base on the intro + territory pills
#   deep    — radial gradient end (darker corner of the intro)
#   light   — kickers / rules / footer URL on the ink section slides
#   text_on — text drawn directly on the accent fill
#
# PPCC, CAT, VAL and BAL are hand-curated and WCAG-AA verified (white
# on accent >= 4.5, light on ink >= 4.5). PPCC returns the exact
# Step-3b green tones so its render stays byte-identical once the
# builders read from here. Hero (#1) and outro stay yellow/ink (brand
# climax) and do NOT consume this palette. Territories without a story
# slot today fall through to a derived palette so the function never
# raises on a future code.
_STORY_PALETTES: dict[str, dict[str, str]] = {
    "PPCC": {"accent": "#427c42", "deep": COLOR_GREEN_DEEP, "light": COLOR_GREEN_LIGHT},
    # CAT amber darkened (polish 1): brand yellow shares the amber hue, so
    # only luminance separates them. A much darker amber lets the "40" /
    # SETMANA pill / badges pop like they do on the red/blue/green accents,
    # without touching the yellow. Identity stays amber. light unchanged
    # (gold kicker/footer on ink, already high-contrast).
    # CAT: the dark amber accent fills the intro field, but as a pill on
    # ink it would sink in. `badge` is a separate vivid burnt-orange used
    # only for the territory pill: it pops on ink like VAL/BAL (badge/ink
    # 3.82 vs VAL 3.95), white text passes AA (5.18), and it stays clearly
    # distinct from the neighbouring yellow SETMANA pill (3.38).
    "CAT": {
        "accent": "#5c4500",
        "deep": "#3a2b00",
        "light": "#f0c419",
        "badge": "#c2410c",
    },
    "VAL": {"accent": "#cf3339", "deep": "#8c1f24", "light": "#f4a3a6"},
    "BAL": {"accent": "#0047ba", "deep": "#00307d", "light": "#9bc0f5"},
}


def story_palette(territori: str) -> dict[str, str]:
    """Return the editorial-story palette for `territori`.

    Curated literals for PPCC/CAT/VAL/BAL (the only territories with a
    story slot); a derived fallback for any other code so the function
    is total. `text_on` is computed from the accent via `best_text_on`."""
    pal = _STORY_PALETTES.get(territori)
    if pal is None:
        accent = terr_color(territori)
        pal = {
            "accent": accent,
            "deep": darken(accent, 0.45),
            "light": mix(accent, COLOR_WHITE, 0.35),
        }
    # `badge` defaults to the accent (VAL/BAL/PPCC + derived); only CAT
    # overrides it. `text_on` is the text colour over the accent; the pill
    # picks its own text over `badge` via `best_text_on` at draw time.
    badge = pal.get("badge", pal["accent"])
    return {**pal, "badge": badge, "text_on": best_text_on(pal["accent"])}
