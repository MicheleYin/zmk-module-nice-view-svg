# SVG Screen Pipeline Retirement

The standalone SVG screen authoring, preview, code-generation, and firmware runtime
paths have been retired. LVGL component XML is now the sole source for firmware
screens. This note remains as a migration pointer for older module revisions.

## Keep SVG Artwork

SVG files remain supported under `docs/ui/assets/` as decoration only. The XML
generator rasterizes them offline into monochrome image descriptors; firmware does
not parse SVG or enable ThorVG.

## Current XML Pipeline

| Purpose | Location |
| --- | --- |
| Screens | `docs/ui/screens/*.xml` |
| Reusable widgets | `docs/ui/widgets/*.xml` |
| Composed examples | `docs/ui/samples/*.xml` |
| Validation and generation | `tools/nice_view_xml.py` |
| Live preview | `tools/nice_view_xml_live.py` |
| Firmware runtime | `src/xml_screen.c` |
| Generated firmware sources | `src/generated_xml/<theme>/status_screen_gen.{c,h}` |

Read [LVGL XML screen authoring](widget-authoring-xml.md) for screen editing,
validation, automatic theme selection, and regeneration instructions.
