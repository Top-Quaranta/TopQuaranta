"""Single source of truth for legal-document versioning.

Bump `TERMES_VERSIO` whenever a material change to the public legal
pages would require users to re-accept (e.g. new processor, new
purpose, new categories of data). The value goes into
`PerfilUsuari.consent_termes_versio` so we can ask for a fresh
acceptance via UI.

Conventionally we use the publication date as the version, ISO
formatted (`YYYY-MM-DD`).
"""

TERMES_VERSIO = "2026-04-26"
