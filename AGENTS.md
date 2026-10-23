# ZMK XML Screen Module Instructions

This repository is the **ZMK LVGL XML status-screen module** (Zephyr module
name and compatibility Kconfig prefix remain `zmk-svg` / `CONFIG_ZMK_SVG`).
Keyboard users enable it from a ZMK config; use sibling Sofle/ZMK forks as the
integration workspace, not upstream ZMK alone.

## XML Screen Pipeline

`docs/ui/screens/`, `docs/ui/widgets/`, and `docs/ui/assets/` are the only screen
sources. Generate firmware into `src/generated_xml/<theme>/`; runtime is
`src/xml_screen.c`. SVG and PNG files are allowed only as offline artwork inputs.

### Agent rules

- After editing XML screens or assets, regenerate the matching
  `src/generated_xml/<theme>/status_screen_gen.{c,h}` and commit them.
- Regenerate the paired image gallery with `tools/render_xml_gallery.py` after
  changing screens, widgets, or artwork.
- Do not enable firmware `LV_USE_SVG` / ThorVG; use offline I1/I2 embeds.
- Do not edit Cursor plan files under `~/.cursor/plans/` unless the user asks.

## Dev Rules

- Commit changes at each milestone. Ensure pre-commit works and never bypass pre-commit.
- Write simple and sufficient tests for new features.
  - Host/unit: extend `test_nice_view_xml.py`.
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

Host tooling needs `uv`, Node.js, Emscripten, and `rsvg-convert` on `PATH` for
the LVGL-native PNG gallery; XML preview/unit tests use Pillow and watchdog.

```sh
# Lint / hooks
pre-commit run

# Host unit tests
uv run --isolated --with-requirements tools/requirements.txt python -m unittest

# XML validate / generate / live (example: default theme)
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml.py validate docs/ui/screens/nice-view-left.xml
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml.py generate docs/ui/screens/nice-view-left.xml \
  --output-dir src/generated_xml/nice_view_left
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/nice_view_xml_live.py docs/ui/screens/nice-view-left.xml

# Paired LVGL-native PNG gallery
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/render_xml_gallery.py

# Module west tests / build
west zmk-test tests -m .
west zmk-build tests/zmk-config
```

## XML theme to output directory

| Screen | `--output-dir` |
| --- | --- |
| `docs/ui/screens/nice-view-left.xml` | `src/generated_xml/nice_view_left` |
| `docs/ui/screens/nice-view-right.xml` | `src/generated_xml/nice_view_right` |
| `docs/ui/screens/oled-left.xml` | `src/generated_xml/oled_left` |
| `docs/ui/screens/oled-right.xml` | `src/generated_xml/oled_right` |

## Firmware Kconfig (XML)

```conf
CONFIG_ZMK_SVG=y
CONFIG_ZMK_SVG_SCREEN=y
```

Screen selection is automatic from display dimensions and physical half. Set
`CONFIG_ZMK_SVG_RIGHT_HALF=y` on the right half.

## Codacy / local analysis

If Codacy MCP is configured, analyze edited files after substantive changes.
Use provider/org/repo settings from workspace Codacy rules when calling remote APIs.
