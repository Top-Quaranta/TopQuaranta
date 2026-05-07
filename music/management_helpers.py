"""Shared argparse helpers for management commands.

Used across the cron-style commands (`obtenir_*`, `inferir_*`,
`netejar_*`, `recalcular_ml`) that all accept the same handful of
flags: `--dry-run`, `--limit`, sometimes `--artista-id`. Inlining
the argparse boilerplate per command meant minor drift in help
strings and defaults; centralising preserves consistency.

Usage:

    from music.management_helpers import add_dry_run, add_limit

    class Command(BaseCommand):
        def add_arguments(self, parser):
            add_dry_run(parser)
            add_limit(parser, default=500)

We deliberately do NOT introduce a base class — each command's
`handle()` has different shape (lock name, refresh-days flag, etc.)
and a base class would force every command into one mould.
"""

from __future__ import annotations


def add_dry_run(parser, *, help: str | None = None) -> None:
    """Add `--dry-run` boolean flag. Default off.

    Convention: when set, the command logs what it WOULD do without
    writing to the DB or calling external APIs.
    """
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=help or "Show what would change without writing or calling external APIs.",
    )


def add_limit(parser, *, default: int | None = None, help: str | None = None) -> None:
    """Add `--limit N` integer flag. Default `None` (= no cap).

    Convention: cap the number of items the command processes per
    invocation. Useful for incremental backfills and for capping
    audit-log volume on cron-driven cleanup commands.
    """
    parser.add_argument(
        "--limit",
        type=int,
        default=default,
        help=help
        or (
            "Cap the number of items processed in this run "
            f"(default: {'unlimited' if default is None else default})."
        ),
    )


def add_artista_id(parser) -> None:
    """Add `--artista-id N` flag for "process only this Artista".

    Used by per-artista commands (obtenir_metadata, MB sync, Last.fm
    sync, ML feature extraction). When set, the command typically
    bypasses the refresh-days queue order and processes the single
    target unconditionally.
    """
    parser.add_argument(
        "--artista-id",
        type=int,
        default=None,
        help="Process only the given Artista pk; ignores queue ordering.",
    )
