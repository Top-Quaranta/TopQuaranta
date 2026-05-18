"""Per-network text assemblers.

Each composer is a single `compose(scenarios, entries, *, territori,
setmana, rng=None) -> dict` function returning `{"text", "hashtags",
"cta"}`. Entry-row shape matches the existing `payload.build_top`
output (`posicio`, `canco_nom`, `artista_nom`,
`artista_instagram_url`).

Channel-specific knobs (length, mention style, hashtag density) are
encoded here; the bank in `phrases.py` is channel-agnostic.
"""
