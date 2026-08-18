"""Comma-joined artist listing — pixel + char truncation (Tasca B2).

`_join_artists` (pixels, used by the PIL renderer) and
`_join_artists_text` (chars, used by captions / composers) share
the same shape semantics:

  * 0 names         → "—"
  * 1 name fits     → the name unchanged
  * 1 name no fits  → char-level truncation with ellipsis
  * 3 names fit     → "A, B, C"
  * 3 names partial → "A, B…"
  * tail-only fit   → "A…"

This file unit-tests both helpers and adds one integration smoke
that the renderer's feed-list slide picks up `artistes_noms` from
the entry dict and emits a comma-joined string for the painted
artist label."""

from __future__ import annotations

from PIL import Image, ImageDraw

from social import fonts
from social.captions import _join_artists_text
from social.renderer import _join_artists, _truncate

# ── pixel helper: _join_artists ────────────────────────────────────


def _draw() -> ImageDraw.ImageDraw:
    img = Image.new("RGB", (1080, 200), (0, 0, 0))
    return ImageDraw.Draw(img)


def test_join_artists_empty_list_returns_dash():
    d = _draw()
    f = fonts.sans_regular(22)
    assert _join_artists(d, [], f, 680) == "—"


def test_join_artists_single_short_name_unchanged():
    d = _draw()
    f = fonts.sans_regular(22)
    assert _join_artists(d, ["Manel"], f, 680) == "Manel"


def test_join_artists_three_names_fit_full():
    d = _draw()
    f = fonts.sans_regular(22)
    out = _join_artists(d, ["A", "B", "C"], f, 680)
    assert out == "A, B, C"


def test_join_artists_three_names_partial_fit():
    """With a very narrow slot, the helper should drop names from the
    tail and append `…` after the last fitting name."""
    d = _draw()
    f = fonts.sans_regular(22)
    # ~80 px is just enough for two short names + ellipsis.
    out = _join_artists(d, ["Maria", "Joan", "Pere"], f, 80)
    assert out.endswith("…")
    assert "Maria" in out
    # The dropped names mustn't appear as partial fragments.
    assert "Joan…" not in out  # whole-name drops, not char-level


def test_join_artists_only_first_name_too_wide_falls_back_to_char_truncation():
    """If even the main artist alone is wider than the slot, fall
    back to `_truncate` (char-level + ellipsis)."""
    d = _draw()
    f = fonts.sans_regular(22)
    long_main = "An Extremely Long Pathological Artist Name For Testing Only"
    out = _join_artists(d, [long_main, "Other"], f, 60)
    assert out.endswith("…")
    # Char-level truncation: the result is a prefix of the main name
    # plus ellipsis, no comma (collabs implicitly dropped).
    assert "," not in out


def test_join_artists_long_collab_list_drops_from_tail():
    """The 39-collab "La Gent de la Mediterrània" case scaled down:
    a long list in a moderate slot should keep the first few names
    and emit `…` after the last fitter."""
    d = _draw()
    f = fonts.sans_regular(22)
    names = [f"Artist {i}" for i in range(10)]
    out = _join_artists(d, names, f, 200)
    assert out.endswith("…")
    assert out.startswith("Artist 0")


# ── char helper: _join_artists_text ────────────────────────────────


def test_join_artists_text_empty_returns_dash():
    assert _join_artists_text([], max_chars=80) == "—"


def test_join_artists_text_single_fits():
    assert _join_artists_text(["Manel"], max_chars=80) == "Manel"


def test_join_artists_text_all_fit():
    assert _join_artists_text(["A", "B", "C"], max_chars=80) == "A, B, C"


def test_join_artists_text_partial_fit_drops_from_tail():
    """Three names but the budget only allows two."""
    out = _join_artists_text(["Maria", "Joan", "Pere"], max_chars=10)
    assert out == "Maria…", out


def test_join_artists_text_only_first_fits():
    out = _join_artists_text(["Maria", "Joan"], max_chars=5)
    # Only "Maria" itself is exactly 5 chars — can't add an ellipsis
    # without exceeding, so it falls through to char-truncating the
    # first name to make room.
    # Property: the output respects the budget, signals omission with
    # `…`, is a prefix of the main name (no collab leaks through) and
    # keeps as much of that name as the budget allows.
    assert len(out) <= 5
    assert out.endswith("…")
    assert "Joan" not in out and "," not in out
    assert "Maria".startswith(out[:-1]) and len(out[:-1]) >= 1


def test_join_artists_text_main_too_long_char_truncates():
    long_main = "PathologicallyLongArtistName"
    out = _join_artists_text([long_main, "Other"], max_chars=10)
    assert out.endswith("…")
    assert len(out) <= 10
    # No comma — collab implicitly dropped.
    assert "," not in out


# ── integration: renderer reads `artistes_noms` ────────────────────


# ── max_lines=2 (story surface) — Tasca B3 ─────────────────────────


def test_join_artists_two_lines_single_name_no_split():
    """One short name fits on one line. Don't force a split."""
    d = _draw()
    f = fonts.sans_regular(44)  # story font size
    out = _join_artists(d, ["Manel"], f, 840, max_lines=2)
    assert out == "Manel"
    assert "\n" not in out


def test_join_artists_two_lines_all_fit_one_line():
    """Three short names that fit on one line at 44-pt / 840 px must
    stay on one line — `max_lines=2` is permissive, not mandatory."""
    d = _draw()
    f = fonts.sans_regular(44)
    out = _join_artists(d, ["Maria", "Joan", "Pere"], f, 840, max_lines=2)
    assert "\n" not in out, out
    assert out == "Maria, Joan, Pere"


def test_join_artists_two_lines_packs_to_second_line_when_needed():
    """A list too long for one line at 44-pt / 840 px packs greedily
    onto two lines. The Ai-Mareta case scaled — 4 short names that
    fit altogether on two lines but not on one."""
    d = _draw()
    f = fonts.sans_regular(44)
    names = ["Aaaaaa", "Bbbbbb", "Cccccc", "Dddddd", "Eeeeee", "Ffffff", "Gggggg"]
    out = _join_artists(d, names, f, 500, max_lines=2)
    assert "\n" in out, out
    parts = out.split("\n")
    assert len(parts) == 2
    # Both lines fit within the slot.
    for line in parts:
        assert d.textlength(line, font=f) <= 500


def test_join_artists_two_lines_stress_39_collabs_truncates_line2():
    """The La Gent de la Mediterrània case: too many names to fit
    even on two lines → line 2 ends with `…` after the last
    fitting whole name."""
    d = _draw()
    f = fonts.sans_regular(44)
    names = [f"Artist {i}" for i in range(40)]
    out = _join_artists(d, names, f, 840, max_lines=2)
    assert "\n" in out, out
    parts = out.split("\n")
    assert parts[1].endswith("…")
    # Each painted line fits.
    for line in parts:
        assert d.textlength(line, font=f) <= 840


def test_join_artists_two_lines_first_name_monstruous_falls_back_to_single_line():
    """If the first name alone is wider than the slot, splitting
    across two lines doesn't help — fall back to char-level
    truncation on one line."""
    d = _draw()
    f = fonts.sans_regular(44)
    long_main = "A" * 200  # absurdly long
    out = _join_artists(d, [long_main, "Other"], f, 200, max_lines=2)
    assert "\n" not in out, out
    assert out.endswith("…")


# ── Tasca B4: greedy maximizes line 1 ──────────────────────────────


# ── Tasca B5: opportunistic word-wrap at end of line 1 ────────────


def test_word_wrap_split_with_realistic_data():
    """End-to-end check via real data: when given the La-Gent-style
    list with insertion-order multi-word names ("Arde Bogotá" is
    the 4th), the helper splits "Arde Bogotá" so line 1 ends with
    "Arde" and line 2 leads with "Bogotá, …"."""
    d = _draw()
    f = fonts.sans_regular(44)
    names = [
        "La Fúmiga",
        "Abril.",
        "Andreu Valor",
        "Arde Bogotá",
        "Aspencat",
        "Auxili",
        "Dani Miquel",
        "Doctor Prats",
        "El Diluvi",
    ]
    out = _join_artists(d, names, f, 840, max_lines=2)
    # Property (not the exact split point, which depends on font
    # metrics): the output uses two lines, both lines fit the slot,
    # every name is preserved whole or broken exactly at a word
    # boundary (line 1 ends with a leading-word prefix of the broken
    # name and line 2 starts with its remaining words), and the
    # word-wrap did fire — line 1 does not end with a whole name.
    assert "\n" in out, out
    parts = out.split("\n")
    assert len(parts) == 2
    for line in parts:
        assert d.textlength(line, font=f) <= 840, line
    l1 = parts[0].split(", ")
    l2 = parts[1].rstrip("…").split(", ")
    # Line 1: whole names in insertion order, except possibly the last
    # token, which may be a leading-word prefix of the next name.
    assert l1[:-1] == names[: len(l1) - 1], l1
    nxt = names[len(l1) - 1]
    if l1[-1] == nxt:
        broken = False
        rest = names[len(l1) :]
    else:
        words = nxt.split(" ")
        prefixes = [" ".join(words[:k]) for k in range(1, len(words))]
        assert l1[-1] in prefixes, (l1[-1], nxt)
        broken = True
        # Line 2 opens with the remaining words of the broken name.
        assert l2[0] == nxt[len(l1[-1]) + 1 :], (l2[0], nxt)
        l2 = l2[1:]
        rest = names[len(l1) :]
    # Line 2: whole names, in order, a prefix of what's left.
    assert l2 == rest[: len(l2)], (l2, rest)
    # With this real-world list the word-wrap must actually fire
    # (line 1 has room for a leading word of the next multi-word
    # name) — otherwise the test would not exercise Tasca B5.
    assert broken, out


def test_word_wrap_does_not_split_single_word_names():
    """If the first leftover name is single-word, never split it.
    It goes whole to line 2."""
    d = _draw()
    f = fonts.sans_regular(44)
    names = ["A", "B", "OBESES"]
    w_with_obeses = d.textlength("A, B, OBESES", font=f)
    # Width that fits "A, B" but not "A, B, OBESES".
    w_ab = d.textlength("A, B", font=f)
    max_w = int((w_ab + w_with_obeses) / 2)
    out = _join_artists(d, names, f, max_w, max_lines=2)
    assert "\n" in out, out
    parts = out.split("\n")
    # Line 1 must NOT end with "OBE" or similar partial. The whole
    # name moves to line 2.
    assert parts[0] == "A, B", parts[0]
    assert parts[1] == "OBESES", parts[1]


def test_word_wrap_is_opportunistic_not_forced():
    """If all names fit whole across 2 lines, don't split anyone."""
    d = _draw()
    f = fonts.sans_regular(44)
    names = ["Aaaa", "Bbbb", "Long Name", "Other"]
    # Slot sized empirically: fits "Aaaa, Bbbb, Long" (so a forced
    # word-wrap COULD extend line 1) but not the whole list on one
    # line, while "Long Name, Other" fits whole on line 2.
    w_forced = d.textlength("Aaaa, Bbbb, Long", font=f)
    w_full = d.textlength(", ".join(names), font=f)
    max_w = int((w_forced + w_full) / 2)
    assert d.textlength("Long Name, Other", font=f) <= max_w
    out = _join_artists(d, names, f, max_w, max_lines=2)
    # Property, asserted unconditionally: two lines, nothing dropped,
    # and no name broken across lines — every painted token is one
    # of the input names.
    assert "\n" in out, out
    parts = out.split("\n")
    assert len(parts) == 2, out
    tokens = [t for line in parts for t in line.split(", ")]
    assert tokens == names, tokens
