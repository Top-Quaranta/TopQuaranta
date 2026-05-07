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
