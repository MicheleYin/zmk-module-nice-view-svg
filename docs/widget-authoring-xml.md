# LVGL XML screen authoring

ZMK status screens can be authored as **LVGL component XML** instead of SVG.
The XML uses the same status field catalog as SVG (`tools/status_fields.json`)
and the same 22-binding budget.

## Project layout

| Path | Purpose |
| --- | --- |
| `docs/ui/project.xml` | Display size and project metadata |
| `docs/ui/globals.xml` | Shared fonts/images notes |
| `docs/ui/assets/*.png` | 1-bit background art (from SVG exports) |
| `docs/ui/screens/*.xml` | Screen definitions (160×68 and 128×32 themes) |

Each screen file must be a single `<component>` with one `<view width="…" height="…">`.

## Dynamic widgets

| Element | Role |
| --- | --- |
| `<zmk_status_text field="…" format="percent\|text\|output-label"/>` | Label bound to a field |
| `<zmk_status_bar field="…"/>` | Horizontal bar (integer/percent fields) |
| `<zmk_status_arc field="…"/>` | Ring indicator |
| `<zmk_status_when field="…" test="equals\|bit_set\|bit_clear" …>` | Conditional visibility |
| `<lv_image src="../assets/….png"/>` | Full-screen I1 background (one per screen) |

Optional `role="central"` or `role="peripheral"` limits a widget to one half.

Static decoration uses `<lv_label>` (and other LVGL tags). Prefer absolute `x`/`y` so codegen and firmware stay aligned.

### Background images

Export static art from an SVG (dynamic `data-nvp-*` nodes stripped):

```sh
uv run --isolated --with-requirements tools/requirements.txt python -c "
from pathlib import Path
from tools.nice_view_xml_assets import export_static_svg_background
export_static_svg_background(Path('docs/screens/default.svg'), Path('docs/ui/assets/default_bg.png'))
"
```

`nice_view_xml.py generate` embeds the PNG as an LVGL I1 `lv_image` in `status_screen_gen.c`. Live preview pastes the same PNG under the status widgets.

## Tooling

```sh
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml.py validate docs/ui/screens/status_screen.xml

uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml.py generate docs/ui/screens/status_screen.xml \
  --output-dir src/generated_xml/default

uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml_live.py docs/ui/screens/status_screen.xml
```

Regenerate committed `status_screen_gen.c` / `.h` before flashing when XML changes.

## Firmware

Enable XML screens instead of SVG bitmap headers:

```conf
CONFIG_ZMK_SVG=y
CONFIG_ZMK_SVG_SCREEN=y
CONFIG_ZMK_SVG_LVGL_XML=y
```

For 128×32 OLED automatic themes, also set `CONFIG_ZMK_SVG_LVGL_XML_OLED=y` and
use `CONFIG_ZMK_SVG_RIGHT_HALF=y` on the mirrored half when needed.

Left/right Nice!View themes use `CONFIG_ZMK_SVG_THEME_LEFT=y` or
`CONFIG_ZMK_SVG_THEME_RIGHT=y` with the matching `docs/ui/screens/day.xml` or
`night.xml` generated into `src/generated_xml/day` or `night`.

## SVG migration

SVG `data-nvp-*` attributes map to the ZMK XML widgets above. Background artwork
from SVG should be converted to I1/I2 `lv_image` assets rather than rsvg-at-build-time.
The legacy SVG pipeline remains available when `CONFIG_ZMK_SVG_LVGL_XML` is disabled.
