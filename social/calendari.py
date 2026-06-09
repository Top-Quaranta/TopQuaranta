"""Sprint I distribution calendar.

Maps each `(weekday, slot)` to the `(platform, tipus, territori)` tuple
it should publish. The territorial top rotates across CAT/VAL/BAL by ISO
week number so coverage feels balanced even when only one territorial
day is active.

The legacy per-slot `min_fase` rollout gate was removed 2026-06 (prod was
at the final phase = everything on, so removal is neutral). Per-slot day
scheduling is now the distribution matrix's `dia_setmana`, uniform across
every channel — see `docs/architecture/social.md`.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from social.models import SocialPost

# weekday: Monday=0 … Sunday=6
WEEKDAY_NAMES = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}

# Territoris that can host a top of their own (Sprint I scope —
# only the three with consistent volume). Rotation is by ISO week
# number so the same territori falls on dilluns and dimecres
# evenly across the year.
TERRITORIS_ROTATORI = ("CAT", "VAL", "BAL")


@dataclass(frozen=True)
class CalendarSlot:
    weekday: int
    platform: str
    tipus: str
    territori_pick: str  # "PPCC" | "ROTATORI_A" | "ROTATORI_B" | ""


# A "ROTATORI_A" slot uses the (week_no % 3) territori; "ROTATORI_B"
# uses the next one in the cycle so dilluns and dimecres of the same
# week never feature the same territori.
CALENDARI: list[CalendarSlot] = [
    # Saturday — PPCC feed + stories
    CalendarSlot(
        5,
        SocialPost.PLATFORM_INSTAGRAM_FEED,
        SocialPost.TIPUS_TOP_PPCC,
        "PPCC",
    ),
    CalendarSlot(
        5,
        SocialPost.PLATFORM_INSTAGRAM_STORY,
        SocialPost.TIPUS_TOP_PPCC,
        "PPCC",
    ),
    # Wednesday — territorial rotatori A
    CalendarSlot(
        2,
        SocialPost.PLATFORM_INSTAGRAM_FEED,
        SocialPost.TIPUS_TOP_TERRITORIAL,
        "ROTATORI_A",
    ),
    CalendarSlot(
        2,
        SocialPost.PLATFORM_INSTAGRAM_STORY,
        SocialPost.TIPUS_TOP_TERRITORIAL,
        "ROTATORI_A",
    ),
    # Monday — second territorial of the week (rotatori B)
    CalendarSlot(
        0,
        SocialPost.PLATFORM_INSTAGRAM_FEED,
        SocialPost.TIPUS_TOP_TERRITORIAL,
        "ROTATORI_B",
    ),
    CalendarSlot(
        0,
        SocialPost.PLATFORM_INSTAGRAM_STORY,
        SocialPost.TIPUS_TOP_TERRITORIAL,
        "ROTATORI_B",
    ),
    # Friday — nous singles
    CalendarSlot(
        4,
        SocialPost.PLATFORM_INSTAGRAM_FEED,
        SocialPost.TIPUS_NOUS_SINGLES,
        "",
    ),
    # Tuesday — nous àlbums
    CalendarSlot(
        1,
        SocialPost.PLATFORM_INSTAGRAM_FEED,
        SocialPost.TIPUS_NOUS_ALBUMS,
        "",
    ),
]


def resolve_territori(slot: CalendarSlot, setmana: datetime.date) -> str:
    """Convert a `territori_pick` placeholder into the actual code."""
    if slot.territori_pick == "PPCC":
        return "PPCC"
    if slot.territori_pick == "":
        return ""
    iso_week = setmana.isocalendar().week
    if slot.territori_pick == "ROTATORI_A":
        return TERRITORIS_ROTATORI[iso_week % 3]
    if slot.territori_pick == "ROTATORI_B":
        return TERRITORIS_ROTATORI[(iso_week + 1) % 3]
    return slot.territori_pick


def slots_for(today: datetime.date) -> list[tuple[CalendarSlot, str]]:
    """Returns `[(slot, resolved_territori)]` for the given calendar
    date. The setmana used for resolution is the current ISO week's
    Monday so weekday-by-weekday calls stay deterministic."""
    monday = today - datetime.timedelta(days=today.weekday())
    out: list[tuple[CalendarSlot, str]] = []
    for s in CALENDARI:
        if s.weekday == today.weekday():
            out.append((s, resolve_territori(s, monday)))
    return out


# Canonical helper lives in `music.dates` so non-social code can use
# it. Keep this re-export so existing `from social.calendari
# import tq_week_start` callers don't break.
from music.dates import tq_week_start  # noqa: E402,F401


def upcoming_week(
    reference: datetime.date | None = None,
) -> list[tuple[CalendarSlot, str, datetime.date]]:
    """Every slot in the TopQuaranta week containing `reference`
    (Saturday → Friday). Each tuple: `(slot, resolved_territori,
    publication_date)`. Sorted chronologically: dissabte first,
    divendres last.

    The Monday used to resolve the rotatori territori is the Monday
    *of the same TQ week* (i.e. 2 days after the Saturday start).
    """
    saturday = tq_week_start(reference)
    monday = saturday + datetime.timedelta(days=2)
    out = []
    for s in CALENDARI:
        # Days from `saturday` to the slot's weekday — we walk
        # forwards 0..6 starting at Saturday so dissabte comes first.
        days_offset = (s.weekday - 5) % 7  # Sat=0, Sun=1, Mon=2, …, Fri=6
        publish_date = saturday + datetime.timedelta(days=days_offset)
        out.append((s, resolve_territori(s, monday), publish_date))
    out.sort(key=lambda t: (t[2], t[0].platform))
    return out


def publication_date_for(slot_tipus: str, setmana: datetime.date) -> datetime.date:
    """Given a tipus + the SocialPost.setmana (= ISO Monday of the
    TQ-week's Saturday), return the calendar date that slot publishes
    on. Anchored to the *Saturday* that opens the TQ-week, then offset
    forwards by `(slot.weekday - 5) % 7` (Sat=0, Sun=1, Mon=2 … Fri=6).

    Earlier this was anchored to ISO Monday + slot.weekday, which gave
    the wrong calendar date for Mon→Fri slots after we switched
    `setmana` to the TQ-week's-Saturday convention (the calendar date
    fell one ISO week behind). Caught 2026-04-27 because Preview was
    rendering territorials into the wrong setmana folder, so "Veure
    slides" found nothing.
    """
    saturday = setmana + datetime.timedelta(days=5)
    for s in CALENDARI:
        if s.tipus == slot_tipus:
            days_offset = (s.weekday - 5) % 7
            return saturday + datetime.timedelta(days=days_offset)
    return saturday
