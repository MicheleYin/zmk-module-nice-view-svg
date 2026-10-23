# ZMK Module Development Instructions

This repository is the **ZMK SVG / LVGL XML status-screen module** (Zephyr module
name `zmk-svg`). Keyboard users enable it from a ZMK config; agents should treat
sibling Sofle/ZMK forks as the integration workspace, not upstream ZMK alone.

## Dual pipelines (read this first)

Two authoring paths share one firmware binding model. Do **not** assume SVG-only
or XML-only without checking Kconfig.

| Path | When | Sources | Generate into | Runtime |
| --- | --- | --- | --- | --- |
| SVG | default (`CONFIG_ZMK_SVG_LVGL_XML` off) | `docs/screens/`, `docs/examples/` | `src/generated_*.h` | `src/svg_screen.c` |
| XML | `CONFIG_ZMK_SVG_LVGL_XML=y` | `docs/ui/screens/`, `docs/ui/assets/` | `src/generated_xml/<theme>/` | `src/xml_screen.c` |

Parity and gaps: [docs/xml-vs-svg.md](docs/xml-vs-svg.md).  
Authoring: [docs/widget-authoring.md](docs/widget-authoring.md) (SVG),
[docs/widget-authoring-xml.md](docs/widget-authoring-xml.md) (XML).

### Agent rules

- After editing XML screens or assets, regenerate the matching
  `src/generated_xml/<theme>/status_screen_gen.{c,h}` and commit them.
- After editing SVG screens used by firmware themes, regenerate the matching
  `src/generated_*_screen.h` (or `generated_screen.h`) and commit them.
- Prefer fixing both `svg_screen.c` and `xml_screen.c` when changing shared
  update/read_field behavior (they are near-forks).
- Do not enable firmware `LV_USE_SVG` / ThorVG for decoration; use offline
  I1/I2 embeds.
- Do not edit Cursor plan files under `~/.cursor/plans/` unless the user asks.

## Dev Rules

- Commit changes at each milestone. Ensure pre-commit works and never bypass pre-commit.
- Write simple and sufficient tests for new features.
  - Host/unit: extend `test_nice_view_svg.py` and/or `test_nice_view_xml.py`.
  - Firmware unit: `tests/<case>` via `west zmk-test` when behavior is on-device.
  - Build: enable features in `tests/zmk-config/*` and assert in `test.py`.
- Update `README.md` for keyboard users; keep guides short.
- Create a PR to origin after finishing a task when asked.

## Workspace repositories and integration

Sibling repos (typical local layout):

- `zmk-sofle` — Sofle shield, keymap, `west.yml`, `build.yaml`.
- `zmk` — custom fork (`MicheleYin/zmk`), often `feature/nice-view`; **not**
  upstream `zmkfirmware/zmk` for Nice!View work.
- This module — remote may be `MicheleYin/zmk-module-template` or
  `MicheleYin/zmk-module-svg`; Zephyr name remains `zmk-svg`.

Sofle `config/west.yml` pins ZMK and this module. For end-to-end firmware:

```sh
# from zmk-sofle
west init -l config && west update && west zephyr-export
# then west zmk-build per build.yaml
```

Standalone `west/` manifests may still fetch upstream ZMK `main`; use Sofle for
custom-fork validation.

## Commands

Host tooling needs `uv` and (for SVG/XML raster) `rsvg-convert` on `PATH`.

```sh
# Lint / hooks
pre-commit run

# Host unit tests (SVG + XML)
python3 -m unittest
python3 -m unittest test_nice_view_xml test_nice_view_svg

# XML validate / generate / live (example: default theme)
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml.py validate docs/ui/screens/status_screen.xml
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml.py generate docs/ui/screens/status_screen.xml \
  --output-dir src/generated_xml/default
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml_live.py docs/ui/screens/status_screen.xml

# SVG (legacy path)
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_svg.py validate docs/screens/default.svg

# Module west tests / build
west zmk-test tests -m .
west zmk-build tests/zmk-config
```

## XML theme to output directory

| Screen | `--output-dir` |
| --- | --- |
| `docs/ui/screens/status_screen.xml` | `src/generated_xml/default` |
| `docs/ui/screens/day.xml` | `src/generated_xml/day` |
| `docs/ui/screens/night.xml` | `src/generated_xml/night` |
| `docs/ui/screens/oled-128x32.xml` | `src/generated_xml/oled` |
| `docs/ui/screens/oled-128x32-mirror.xml` | `src/generated_xml/oled_mirror` |

## Firmware Kconfig (XML)

```conf
CONFIG_ZMK_SVG=y
CONFIG_ZMK_SVG_SCREEN=y
CONFIG_ZMK_SVG_LVGL_XML=y
```

For 128x32 OLED automatic theme selection, also set `CONFIG_ZMK_SVG_LVGL_XML_OLED=y`
(and `CONFIG_ZMK_SVG_RIGHT_HALF=y` on the mirrored half).

## Codacy / local analysis

If Codacy MCP is configured, analyze edited files after substantive changes.
Use provider/org/repo settings from workspace Codacy rules when calling remote APIs.
