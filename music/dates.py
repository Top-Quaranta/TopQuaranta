"""Project-wide date helpers for the TopQuaranta calendar.

Two concepts the rest of the codebase needs to share:

1. **TQ-week** — Saturday → Friday. The week opens on Saturday with
   the official top publication. Use `tq_week_start(date)` to get
   the Saturday that opens the TQ-week containing `date`.

2. **Project-week number** — a monotonically increasing integer that
   identifies a TQ-week without ambiguity (no calendar-year reset, no
   "is this ISO 53 or 1?" weirdness). Anchor:
       Sat 2026-04-25 = week 34
   Use `project_week_number(date)` to get the integer.

These functions are imported from many surfaces (renderer, captions,
staff API, React via the social_list payload). Keep them here, not
inside `ingesta.social.calendari`, so non-social consumers can use
them without dragging in the calendar dataclasses.
"""

from __future__ import annotations

import datetime

# The Saturday we declared as project-week 34. Every TQ-week before
# or after is computed by counting 7-day strides from this anchor.
# Don't move this constant without coordinating a global re-numbering
# in the operator-facing UI.
PROJECT_WEEK_ANCHOR_SATURDAY = datetime.date(2026, 4, 25)
PROJECT_WEEK_ANCHOR_NUMBER = 34


def tq_week_start(reference: datetime.date | None = None) -> datetime.date:
    """The Saturday that opens the TQ-week containing `reference`.

    `reference` may be any day of the week; we walk back to the most
    recent Saturday (Sat itself returns Sat).
    """
    if reference is None:
        reference = datetime.date.today()
    # weekday(): Mon=0 … Sat=5 … Sun=6.
    # Days back to the most recent Saturday: (weekday + 2) % 7.
    days_back = (reference.weekday() + 2) % 7
    return reference - datetime.timedelta(days=days_back)


def project_week_number(reference: datetime.date | None = None) -> int:
    """Monotonic project-week number for the TQ-week containing
    `reference`. Anchor: Sat 2026-04-25 = 34."""
    sat = tq_week_start(reference)
    delta_days = (sat - PROJECT_WEEK_ANCHOR_SATURDAY).days
    return PROJECT_WEEK_ANCHOR_NUMBER + delta_days // 7


def project_week_label(reference: datetime.date | None = None) -> str:
    """User-facing 'Setmana N' string. The renderer + caption helpers
    funnel through this so the operator never sees a raw date."""
    return f"Setmana {project_week_number(reference)}"
