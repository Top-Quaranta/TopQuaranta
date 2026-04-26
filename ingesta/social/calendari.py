"""Sprint I distribution calendar.

Maps each `(weekday, slot)` to the `(platform, tipus, territori,
min_fase)` tuple it should publish. The territorial top rotates
across CAT/VAL/BAL by ISO week number so coverage feels balanced
even when only one territorial day is active.

`min_fase` gates each entry. `publicar_social` reads
`ConfiguracioGlobal.fase_distribucio` and skips entries above the
current phase (status="omes").

Phase ladder (must match ROADMAP + ConfiguracioGlobal help_text):
    1 — només dissabte (PPCC feed + stories)
    2 — + dimecres (territorial rotatori)
    3 — + dilluns (segon territorial)
    4 — + divendres (singles)
    5 — + dimarts (àlbums)
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
    min_fase: int


# A "ROTATORI_A" slot uses the (week_no % 3) territori; "ROTATORI_B"
# uses the next one in the cycle so dilluns and dimecres of the same
# week never feature the same territori.
CALENDARI: list[CalendarSlot] = [
    # Saturday — Phase 1 (always on once instagram_actiu=True)
    CalendarSlot(
        5,
        SocialPost.PLATFORM_INSTAGRAM_FEED,
        SocialPost.TIPUS_TOP_PPCC,
        "PPCC",
        min_fase=1,
    ),
    CalendarSlot(
        5,
        SocialPost.PLATFORM_INSTAGRAM_STORY,
        SocialPost.TIPUS_TOP_PPCC,
        "PPCC",
        min_fase=1,
    ),
    # Wednesday — Phase 2
    CalendarSlot(
        2,
        SocialPost.PLATFORM_INSTAGRAM_FEED,
        SocialPost.TIPUS_TOP_TERRITORIAL,
        "ROTATORI_A",
        min_fase=2,
    ),
    CalendarSlot(
        2,
        SocialPost.PLATFORM_INSTAGRAM_STORY,
        SocialPost.TIPUS_TOP_TERRITORIAL,
        "ROTATORI_A",
        min_fase=2,
    ),
    # Monday — Phase 3 (second territorial of the week)
    CalendarSlot(
        0,
        SocialPost.PLATFORM_INSTAGRAM_FEED,
        SocialPost.TIPUS_TOP_TERRITORIAL,
        "ROTATORI_B",
        min_fase=3,
    ),
    CalendarSlot(
        0,
        SocialPost.PLATFORM_INSTAGRAM_STORY,
        SocialPost.TIPUS_TOP_TERRITORIAL,
        "ROTATORI_B",
        min_fase=3,
    ),
    # Friday — Phase 4
    CalendarSlot(
        4,
        SocialPost.PLATFORM_INSTAGRAM_FEED,
        SocialPost.TIPUS_NOUS_SINGLES,
        "",
        min_fase=4,
    ),
    # Tuesday — Phase 5
    CalendarSlot(
        1,
        SocialPost.PLATFORM_INSTAGRAM_FEED,
        SocialPost.TIPUS_NOUS_ALBUMS,
        "",
        min_fase=5,
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


def upcoming_week(
    reference: datetime.date | None = None,
) -> list[tuple[CalendarSlot, str, datetime.date]]:
    """Return every slot of the ISO week containing `reference`
    (default: today). Each tuple is `(slot, resolved_territori,
    publication_date)`. Used by the staff dashboard to show what's
    coming and which territori has been picked."""
    if reference is None:
        reference = datetime.date.today()
    monday = reference - datetime.timedelta(days=reference.weekday())
    out = []
    for s in CALENDARI:
        publish_date = monday + datetime.timedelta(days=s.weekday)
        out.append((s, resolve_territori(s, monday), publish_date))
    out.sort(key=lambda t: (t[2], t[0].platform))
    return out


def publication_date_for(slot_tipus: str, setmana: datetime.date) -> datetime.date:
    """Given a tipus + the Monday-of-week, return the calendar date
    on which that slot's content publishes. Used by the staff
    `Preview` action so we don't accidentally render against the
    Monday (which has no PPCC slot)."""
    monday = setmana - datetime.timedelta(days=setmana.weekday())
    for s in CALENDARI:
        if s.tipus == slot_tipus:
            return monday + datetime.timedelta(days=s.weekday)
    return monday
