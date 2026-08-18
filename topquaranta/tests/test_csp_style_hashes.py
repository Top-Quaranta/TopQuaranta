"""Every inline `<style>` we serve must be whitelisted in the CSP.

The failure this prevents is silent and total. `deploy/Caddyfile` sends
`style-src 'self' '<sha256…>'` — a hash per inline style block. Edit the
CSS inside a template and its hash changes; the browser then refuses the
whole block and serves the page **completely unstyled**. Nothing in the
pipeline notices: the HTML is correct, the CSS is in it, the tests pass,
curl shows everything present. Only a real browser enforces CSP, and only
a human looking at the page can tell.

That is exactly what happened: the 2026-06-13 redesign rewrote
`comptes/_base_auth.html`, the Caddyfile kept the old hash, and every
Django-rendered auth page — login, registration, the three 2FA screens,
password reset, account deletion — plus 403/404/500 went out as raw HTML
for two months. Reported 2026-08-15 by the only means available: the
owner logging in on his phone and seeing it.

Emails are excluded: they are never served over HTTP, so no CSP applies.
"""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

import pytest

ARREL = Path(__file__).resolve().parent.parent.parent
CADDYFILE = ARREL / "deploy" / "Caddyfile"

# Directories whose .html files are served to a browser.
ZONES = [
    ARREL / "comptes" / "templates",
    ARREL / "web" / "templates",
    ARREL / "web-react" / "index.html",
]

_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
_DINAMIC = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)


def _hash(css: str) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(css.encode()).digest()).decode()


def _plantilles() -> list[Path]:
    out: list[Path] = []
    for zona in ZONES:
        if zona.is_file():
            out.append(zona)
        elif zona.exists():
            out += [
                f
                for f in sorted(zona.rglob("*.html"))
                # Emails don't travel over HTTP, so no CSP reaches them.
                if not f.name.startswith("email_")
            ]
    return out


def _blocs() -> list[tuple[Path, str]]:
    return [(f, b) for f in _plantilles() for b in _STYLE.findall(f.read_text())]


def test_there_is_something_to_check():
    """A guard on the guard: if the globs ever stop matching, this file
    would pass by finding nothing at all."""
    assert len(_blocs()) >= 8


@pytest.mark.parametrize(
    "fitxer,css", _blocs(), ids=[f"{f.name}#{i}" for i, (f, _) in enumerate(_blocs())]
)
def test_inline_style_is_whitelisted_in_the_csp(fitxer: Path, css: str):
    csp = CADDYFILE.read_text()
    h = _hash(css)
    assert h in csp, (
        f"El bloc <style> de {fitxer.relative_to(ARREL)} no és a la CSP.\n"
        f"El navegador el bloquejarà i la pàgina eixirà sense estils.\n"
        f"Afig aquesta empremta a style-src de deploy/Caddyfile:\n\n    '{h}'\n"
    )


@pytest.mark.parametrize("fitxer,css", _blocs(), ids=lambda v: getattr(v, "name", ""))
def test_inline_style_is_static(fitxer: Path, css: str):
    """A hash can only cover fixed bytes. A template tag inside a style
    block means the served CSS differs from the source, so the hash would
    be right here and wrong in production — the worst combination."""
    assert not _DINAMIC.search(css), (
        f"{fitxer.relative_to(ARREL)} té plantilla dins d'un <style>. "
        f"L'empremta no es pot calcular des del codi font."
    )
