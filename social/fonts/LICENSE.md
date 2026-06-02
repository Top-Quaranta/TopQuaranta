# Vendored fonts

These TTF files are bundled at build time so the Instagram renderer
has guaranteed glyphs available without depending on the host's
fontconfig.

| Font | Upstream | Licence |
|---|---|---|
| `PlayfairDisplay-Bold.ttf`, `PlayfairDisplay-Regular.ttf`, `PlayfairDisplay-ExtraBold.ttf` | [google/fonts/ofl/playfairdisplay](https://github.com/google/fonts/tree/main/ofl/playfairdisplay) | [SIL Open Font License 1.1](https://openfontlicense.org/) |
| `Roboto-Bold.ttf`, `Roboto-Regular.ttf` | [googlefonts/roboto](https://github.com/googlefonts/roboto) | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) |
| `Anton-Regular.ttf` | [google/fonts/ofl/anton](https://github.com/google/fonts/tree/main/ofl/anton) | [SIL Open Font License 1.1](https://openfontlicense.org/) |
| `BricolageGrotesque-ExtraBold.ttf` | [google/fonts/ofl/bricolagegrotesque](https://github.com/google/fonts/tree/main/ofl/bricolagegrotesque) | [SIL Open Font License 1.1](https://openfontlicense.org/) |
| `InstrumentSerif-Italic.ttf` | [google/fonts/ofl/instrumentserif](https://github.com/google/fonts/tree/main/ofl/instrumentserif) | [SIL Open Font License 1.1](https://openfontlicense.org/) |

The PPCC story redesign (Step 3c) added Anton, Bricolage Grotesque and
Instrument Serif. `PlayfairDisplay-ExtraBold.ttf` and
`BricolageGrotesque-ExtraBold.ttf` are **static instances** cut from the
upstream variable fonts (Playfair `wght=800`; Bricolage
`opsz=96, wght=800, wdth=100`) with `fonttools varLib.instancer`, so
Pillow doesn't have to resolve variable axes at render time. Re-cut from
the upstream VF if replaced; don't hand-edit the binary.

Both licences allow vendoring + redistribution alongside derivative
work; no attribution string in the rendered images is required by
either licence (the project still credits them at `/legal/llicencies`).

If a font is replaced upstream, re-download the TTF and overwrite the
file here. Don't hand-edit the binary.
