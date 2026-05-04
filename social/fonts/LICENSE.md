# Vendored fonts

These TTF files are bundled at build time so the Instagram renderer
has guaranteed glyphs available without depending on the host's
fontconfig.

| Font | Upstream | Licence |
|---|---|---|
| `PlayfairDisplay-Bold.ttf`, `PlayfairDisplay-Regular.ttf` | [google/fonts/ofl/playfairdisplay](https://github.com/google/fonts/tree/main/ofl/playfairdisplay) | [SIL Open Font License 1.1](https://openfontlicense.org/) |
| `Roboto-Bold.ttf`, `Roboto-Regular.ttf` | [googlefonts/roboto](https://github.com/googlefonts/roboto) | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) |

Both licences allow vendoring + redistribution alongside derivative
work; no attribution string in the rendered images is required by
either licence (the project still credits them at `/legal/llicencies`).

If a font is replaced upstream, re-download the TTF and overwrite the
file here. Don't hand-edit the binary.
