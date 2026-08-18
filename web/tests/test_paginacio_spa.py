"""Every `<Pagination>` in the SPA must be called with `meta`.

`components/rd/surface.jsx::Pagination` opens with:

    if (!meta || meta.num_pages <= 1) return null

so a call site passing the wrong prop names renders **nothing at all** —
no error, no warning, no control. `/staff/artistes/sense-youtube` did
exactly that (`page` / `total` / `pageSize` / `onChange`), and the
operator spent days believing the queue held 50 artists when it held
400: there was no second page to click to.

There is no Vitest wiring in this project (CLAUDE.md §9), so this is a
static check. It is crude and it is enough: the failure mode is a prop
name, and a prop name is greppable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ARREL = Path(__file__).resolve().parent.parent.parent / "web-react" / "src"
CRIDA = re.compile(r"<Pagination\b(.*?)/?>", re.S)


def _crides():
    fora = []
    for f in sorted(ARREL.rglob("*.jsx")):
        text = f.read_text()
        for m in CRIDA.finditer(text):
            if "export function Pagination" in text[: m.start()]:
                continue  # la definició, no una crida
            fora.append((f.relative_to(ARREL), m.group(1)))
    return fora


def test_there_are_pagination_call_sites():
    assert len(_crides()) >= 2


@pytest.mark.parametrize("fitxer,props", _crides(), ids=[str(f) for f, _ in _crides()])
def test_pagination_is_given_a_meta_prop(fitxer, props):
    assert "meta=" in props, (
        f"{fitxer}: <Pagination> sense `meta=`. El component fa "
        f"`if (!meta) return null`, així que no dibuixarà res i la vista "
        f"semblarà que no té més pàgines."
    )
