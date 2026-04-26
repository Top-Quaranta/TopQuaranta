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
