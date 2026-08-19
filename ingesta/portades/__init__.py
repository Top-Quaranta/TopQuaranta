"""Self-hosted cover pipeline (Fase 1).

Downloads Deezer covers once and transcodes them into small
webp/avif/jpg variants stored on our own origin. State is derived
from the filesystem (no DB column): a cover "exists" iff its
500 px webp variant is on disk.

# Spec: docs/architecture/ingesta.md
"""

from ingesta.portades.manager import (
    ENTITATS,
    delete,
    download_and_convert,
    exists,
    path_for,
)

__all__ = [
    "ENTITATS",
    "delete",
    "download_and_convert",
    "exists",
    "path_for",
]
