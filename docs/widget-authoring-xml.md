# LVGL XML Screen Authoring

LVGL component XML is the module's only firmware screen source. The typed status
field catalog is `tools/status_fields.json`; each screen has a 22-binding budget.

## Project layout

| Path | Purpose |
| --- | --- |
| `docs/ui/project.xml` | Display size and project metadata |
| `docs/ui/globals.xml` | Shared fonts/images notes |
| `docs/ui/assets/*.png` | 1-bit background art (from SVG exports) |
| `docs/ui/screens/*.xml` | Screen definitions (160×68 and 128×32 themes) |
| `docs/ui/widgets/*.xml` | Reusable parameterized status widgets |
| `docs/ui/samples/*.xml` | Composed screen examples |

Each screen file must be a single `<component>` with one `<view width="…" height="…">`.

### Reusable widgets

Screens can include XML fragments with `<zmk_include src="…"/>`. Fragment files
use a `<fragment>` root and `{{parameter}}` placeholders. Include attributes other
than `src` provide the parameter values; paths in fragment images are resolved
relative to the fragment and rewritten for the screen. Includes expand before
validation, preview, and C generation.

The widget library contains battery, layer, host-output, BLE profile-tile,
split-link, and split-indicator fragments. See `docs/ui/samples/` for composed
160×68 and 128×32 layouts and the complete widget showcase.

## Dynamic widgets

| Element | Role |
| --- | --- |
| `<zmk_status_text field="…" format="text\|percent\|output-label\|profile-number"/>` | Label bound to a field |
| `<zmk_status_bar field="…"/>` | Horizontal bar (integer/percent fields) |
| `<zmk_status_arc field="…"/>` | Ring indicator |
| `<zmk_status_when field="…" test="equals\|bit_set\|bit_clear" …>` | Conditional visibility |
| `<lv_image src="../assets/….png\|.svg"/>` | Static I1 decoration (any count) |
| `<zmk_status_when>…<lv_image src="…"/>` | Conditional I2 sprite (≤16 assets) |

Optional `role="central"` or `role="peripheral"` limits a widget to one half.

Static decoration uses `<lv_label>` and `<lv_image>`. Prefer absolute `x`/`y` so codegen and firmware stay aligned.

### Offline Artwork

LVGL widgets handle status (text, bars, arcs). Decorative art that is not a native widget can be referenced as **offline** PNG or SVG files under `docs/ui/assets/`:

```xml
<lv_image src="../assets/default_bg.png" x="0" y="0" />
<zmk_status_when field="battery.left.charge" test="equals" value="charging">
  <lv_image src="../assets/bolt.svg" x="27" y="4" width="8" height="10" />
</zmk_status_when>
```

`generate` rasterizes `.svg` with `rsvg-convert` and embeds **I1** (static) or **I2** (conditional) `lv_image` descriptors. Firmware never enables `LV_USE_SVG` / ThorVG.

SVG is supported only as offline artwork. The background exporter strips dynamic
nodes and SVG text; author status text as XML `<lv_label>` widgets to avoid drawing
it twice:

```sh
uv run --isolated --with-requirements tools/requirements.txt python -c "
from pathlib import Path
from tools.nice_view_xml_assets import export_static_svg_background
export_static_svg_background(Path('docs/ui/assets/profile_active.svg'), Path('/tmp/profile-active.png'))
"
```

Conditional sprites under `zmk_status_when` should set `width` and `height` (placement bounds). Soft budget: 16 visible image assets; 22 dynamic bindings.

## Tooling

```sh
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml.py validate docs/ui/screens/status_screen.xml

uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml.py generate docs/ui/screens/status_screen.xml \
  --output-dir src/generated_xml/default

uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml_live.py docs/ui/screens/status_screen.xml

# Compare separate left and right XML screens side by side
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml_live.py docs/ui/screens/day.xml \
  --right-screen docs/ui/screens/night.xml
```

Paired live preview defaults to central data on the left and peripheral data on the
right. Use `--left-role` and `--right-role` to change those assignments.
The watcher follows nested widget XML and referenced artwork; valid edits refresh both
panels, while invalid edits leave the last valid render visible.

Generate the paired screen and complete widget gallery with:

```sh
emcmake cmake -S tools/lvgl_wasm -B build/lvgl_wasm
cmake --build build/lvgl_wasm
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/render_xml_gallery.py
```

Regenerate committed `status_screen_gen.c` / `.h` before flashing when XML changes.

## Firmware

Enable the module and generated XML screen:

```conf
CONFIG_ZMK_SVG=y
CONFIG_ZMK_SVG_SCREEN=y
```

The automatic theme uses the selected display's dimensions. On a 128×32 OLED,
set `CONFIG_ZMK_SVG_RIGHT_HALF=y` on the mirrored half when needed.

Left/right Nice!View themes use `CONFIG_ZMK_SVG_THEME_LEFT=y` or
`CONFIG_ZMK_SVG_THEME_RIGHT=y` with the matching `docs/ui/screens/day.xml` or
`night.xml` generated into `src/generated_xml/day` or `night`.

## Migration Notes

The old SVG screen authoring and runtime paths are retired. Convert decorative
backgrounds and icons to offline PNG or SVG files under `docs/ui/assets/` and
reference them with `<lv_image>`; firmware does not parse SVG.
