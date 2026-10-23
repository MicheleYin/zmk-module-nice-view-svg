# XML vs SVG status screens

This module currently ships **two** authoring pipelines that share the same runtime
binding model (`struct zmk_nvp_svg_binding`, 22-binding budget, `status_fields.json`).

| | SVG (legacy / default) | LVGL XML |
| --- | --- | --- |
| Source | `docs/screens/*.svg`, `docs/examples/*.svg` | `docs/ui/screens/*.xml` + `docs/ui/assets/*` |
| Tools | `tools/nice_view_svg.py`, `nice_view_svg_live.py` | `tools/nice_view_xml.py`, `nice_view_xml_live.py` |
| Generate output | `src/generated_*.h` (I1 bg + I2 sprites in one header) | `src/generated_xml/<theme>/status_screen_gen.{c,h}` |
| Firmware | `src/svg_screen.c` | `src/xml_screen.c` when `CONFIG_ZMK_SVG_LVGL_XML=y` |
| Authoring guide | [widget-authoring.md](widget-authoring.md) | [widget-authoring-xml.md](widget-authoring-xml.md) |

## Prefer which path?

- **XML** — LVGL-native widgets (`zmk_status_*`, `lv_label`, `lv_image`) plus optional
  offline SVG/PNG embeds for decoration. Closer to LVGL; better for structured status UI.
- **SVG** — Inkscape-first freehand art, `data-nvp-widget` groups, richest examples on
  `main`. Keep using SVG when you need complex paths/groups as conditional sprites without
  splitting assets by hand.

Firmware never runs LVGL `LV_USE_SVG` / ThorVG. Both paths bake bitmaps at generate time.

## Feature parity (XML vs SVG on `main`)

### At or near parity

- Field catalog and sample fixtures
- Renderers: text, percent, bar, ring/arc, visible
- Formats: text, percent, output-label, profile-number
- Roles (central / peripheral)
- Conditional show/hide (`when` / `visible`)
- I1 backgrounds and I2 conditional sprites (XML: via `<lv_image src="…">`)
- Live preview HTTP API (`/config`, `/render`)
- Theme slots: default, day, night, OLED, OLED mirror

### Still missing or weaker in XML

| Gap | SVG today | XML today |
| --- | --- | --- |
| Widget catalog | `widget_types.json` + `data-nvp-widget` slots | Not validated |
| prefix / suffix | `data-nvp-prefix` / `suffix` | Not emitted on text bindings |
| color | From fill/stroke | Always foreground (`0`) |
| `not_equals` | Supported | Validated; not mapped in codegen |
| Bounds / transforms | `data-nvp-bounds` + transform-aware crop | Soft `width`/`height` on images |
| Theme richness | Full day/night/OLED SVG art + sprites | Thinner overlays; fewer icons |
| Example gallery | Many `docs/examples/*` | Screens + `basic-status.xml` |
| Tests | Large `test_nice_view_svg.py` | Smaller `test_nice_view_xml.py` |
| OLED AUTO | DT size selects header | Needs `CONFIG_ZMK_SVG_LVGL_XML_OLED=y` |

## Attribute map (SVG → XML)

| SVG | XML |
| --- | --- |
| `data-nvp-bind` | `field=` |
| `data-nvp-render="text\|percent"` | `<zmk_status_text format="…">` |
| `data-nvp-render="bar"` | `<zmk_status_bar>` |
| `data-nvp-render="ring"` | `<zmk_status_arc>` |
| `data-nvp-render="visible"` | `<zmk_status_when>` + `<lv_label>` or `<lv_image>` |
| `data-nvp-when` / `data-nvp-bit` | `test=` / `value=` / `bit=` |
| `data-nvp-role` | `role=` |
| Artwork in `<g>` / `<path>` | Export PNG/SVG asset + `<lv_image src>` |

## Generate outputs by theme

| Theme Kconfig | SVG header | XML generate dir |
| --- | --- | --- |
| AUTO 160×68 | `generated_screen.h` | `src/generated_xml/default` |
| `THEME_LEFT` | `generated_day_screen.h` | `src/generated_xml/day` |
| `THEME_RIGHT` | `generated_night_screen.h` | `src/generated_xml/night` |
| AUTO 128×32 left | `generated_oled_screen.h` | `src/generated_xml/oled` (+ `LVGL_XML_OLED`) |
| AUTO 128×32 right | `generated_oled_mirror_screen.h` | `src/generated_xml/oled_mirror` (+ OLED + `RIGHT_HALF`) |
