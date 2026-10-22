# ZMK SVG

[![Build](https://github.com/MicheleYin/zmk-module-svg/actions/workflows/zmk-module.yml/badge.svg?branch=main)](https://github.com/MicheleYin/zmk-module-svg/actions/workflows/zmk-module.yml)

ZMK SVG is a ZMK module for status screens on Nice!View displays and 128 x 32 SSD1306 OLEDs. It provides native LVGL layouts for 160 x 68 and 128 x 32 panels, plus authored SVG screens that must match the panel's native resolution. WPM is not enabled by this module, but remains in the optional status packet if another configuration enables it.

## Screen preview

The five widget groups follow the SVG on the 160 x 68 pixel display: paired battery meters and a large layer tile at the top, profile buttons across the middle, then host and split status along the bottom. A lightning bolt inside a filled battery marks charging.

Both halves show this same screen and the same central/peripheral values. The preview uses the native 160 x 68 landscape proportions and current widget coordinates; glyph shapes and font rendering are approximations.

The split-link indicator shows connected or disconnected state on both halves. On the central it means at least one peripheral is connected; on a peripheral it means its link to the central is connected.

![Approximate ZMK SVG screen preview at 160 x 68](docs/nice-view-plus-preview.svg)

The pixel positions and widget bounds are listed in [the widget restyle proposal](docs/widget-restyle-proposal.md).

## SVG tooling

The validator, previewer, and bitmap-header generator use `uv` to provide Python dependencies in an isolated cached environment; Pillow is not installed into your selected Python. `rsvg-convert` must be available on `PATH` for rasterization.

```sh
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py validate docs/nice-view-plus-preview.svg
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py preview docs/nice-view-plus-preview.svg --values tools/sample_status.central.json --role central --output /tmp/nice_view_plus_central.png
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py preview docs/nice-view-plus-preview.svg --values tools/sample_status.peripheral.json --role peripheral --output /tmp/nice_view_plus_peripheral.png
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py generate docs/nice-view-plus-preview.svg --output /tmp/nice_view_plus_svg.h
# Live preview with the same image on both sides
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg_live.py docs/screens/niceview-left.svg --right-svg docs/screens/niceview-left.svg
# Live preview with different left and right images
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg_live.py docs/screens/niceview-left.svg --right-svg docs/screens/niceview-right.svg
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py generate-defaults
uv run --isolated --with-requirements tools/requirements.txt python -m unittest test_nice_view_svg
```

The live preview opens a 1-bit monochrome raster at the source SVG's dimensions, using the same black/white threshold as firmware generation. Change any bound status field to simulate text, percentages, bars, rings, or conditional elements; switch between central and peripheral roles and choose legacy or white-background polarity. Each preview has independent rotate, flip, and reset controls for checking physical orientation; these controls affect only the editor view and never modify the SVG or generated firmware. Set the final artwork orientation in the SVG itself before regenerating headers. Use `--legacy-inverted` when firmware has `CONFIG_NICE_VIEW_WIDGET_INVERTED=y`. Stop the preview server with `Ctrl+C`.

WPM values are available when `CONFIG_ZMK_WPM` is enabled.

The static preview also supports `--invert` and `--rotate-180` for inspecting output polarity and artwork orientation. These affect preview images only, not firmware display orientation.

Dynamic elements use `data-nvp-bind`, `data-nvp-render`, and optional `data-nvp-role` SVG attributes. Their typed field definitions live in `tools/status_fields.json`; sample values for each half are in `tools/sample_status.*.json`. SVGs are limited to 22 dynamic bindings to keep the LVGL object budget bounded; firmware pool use still needs to be verified on device.

For the screen and widget authoring format, supported widget types, dynamic icon states, and new-screen workflow, see [Screen and Widget Authoring](docs/widget-authoring.md). A validated example is available at [widget-example.svg](docs/widget-example.svg).

The designs in [docs/examples](docs/examples/) and themes in [docs/screens](docs/screens/) can be validated, previewed, and generated as firmware theme headers using the commands in the authoring guide.

| Example | Preview | Highlights |
| --- | --- | --- |
| [activity.svg](docs/examples/activity.svg) | <img src="docs/examples/activity.svg" alt="Activity ring example" width="160"> | Paired battery progress rings with charging marks and compact status details. |
| [cards.svg](docs/examples/cards.svg) | <img src="docs/examples/cards.svg" alt="Segmented cards example" width="160"> | Segmented battery, layer, and host cards above a BLE profile row. |
| [compact.svg](docs/examples/compact.svg) | <img src="docs/examples/compact.svg" alt="Compact status example" width="160"> | Prominent battery meters and layer number with host and split status in the footer. |
| [niceview-left.svg](docs/screens/niceview-left.svg) | <img src="docs/screens/niceview-left.svg" alt="Left Nice!View screen" width="160"> | 160 x 68 screen for the physical left half. |
| [infograph.svg](docs/examples/infograph.svg) | <img src="docs/examples/infograph.svg" alt="Infograph example" width="160"> | Circular battery complications with layer, host, and BLE profile status. |
| [niceview-right.svg](docs/screens/niceview-right.svg) | <img src="docs/screens/niceview-right.svg" alt="Right Nice!View screen" width="160"> | 160 x 68 screen for the physical right half. |
| [oled-left.svg](docs/screens/oled-left.svg) | <img src="docs/screens/oled-left.svg" alt="Left OLED screen" width="160"> | 128 x 32 screen for the physical left half. |
| [oled-right.svg](docs/screens/oled-right.svg) | <img src="docs/screens/oled-right.svg" alt="Right OLED screen" width="160"> | 128 x 32 screen for the physical right half. |
| [rounded.svg](docs/examples/rounded.svg) | <img src="docs/examples/rounded.svg" alt="Rounded interface example" width="160"> | Rounded battery panels, a pill-shaped layer display, and BLE profile selector. |
| [terminal.svg](docs/examples/terminal.svg) | <img src="docs/examples/terminal.svg" alt="Terminal status example" width="160"> | Monospace status readout with battery bars, host output, and profile indicators. |
| [three-column.svg](docs/examples/three-column.svg) | <img src="docs/examples/three-column.svg" alt="Three-column status example" width="160"> | Narrow battery, layer, and host columns with BLE profiles along the bottom. |
| [wpm.svg](docs/examples/wpm.svg) | <img src="docs/examples/wpm.svg" alt="WPM readout example" width="160"> | Large WPM value in a clean monochrome panel. |
| [wpm-tile.svg](docs/examples/wpm-tile.svg) | <img src="docs/examples/wpm-tile.svg" alt="High-contrast WPM tile example" width="160"> | High-contrast WPM tile with a compact pace label. |
| [watch.svg](docs/examples/watch.svg) | <img src="docs/examples/watch.svg" alt="Watch face example" width="160"> | Watch-face layout with battery bars, a circular layer complication, and host status. |

### Left and Right Screens

The generated screen is selected automatically from the display dimensions and physical half. Enable it for both firmware images:

```conf
# Both halves
CONFIG_ZMK_SVG=y
CONFIG_ZMK_SVG_SCREEN=y
CONFIG_NICE_VIEW_WIDGET_STATUS=n
```

```conf
# Right-half firmware only. The left half leaves this unset.
CONFIG_ZMK_SVG_RIGHT_HALF=y
```

Edit the matching `docs/screens/niceview-*.svg` or `docs/screens/oled-*.svg` source, then run `uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py generate-defaults` before building firmware. This refreshes all four checked-in headers.

## Compatibility and setup

This module is currently supported with MicheleYin's ZMK fork on the `feature/nice-view` branch. It depends on that branch's split-BLE status synchronization and peripheral battery level/charge-state fetching, which let both Nice!View displays show central-owned status and the remote half's battery data. The module enables these fork-specific Kconfig features, so upstream ZMK or another revision is not a supported replacement.

Pin both ZMK and this module in your configuration's `config/west.yml`:

```yaml
manifest:
    projects:
        - name: zmk
            url: https://github.com/MicheleYin/zmk.git
            revision: feature/nice-view
            import: app/west.yml
        - name: zmk-module-svg
            url: https://github.com/MicheleYin/zmk-module-svg
            revision: feature/nice-view
```

Update the projects after changing the manifest:

```sh
west update
```

For a new West workspace, initialize it from your configuration repository, then update and export Zephyr:

```sh
west init -l config
west update
west zephyr-export
```

## Use the module

Enable ZMK SVG in the configuration used by each display:

```conf
CONFIG_ZMK_SVG=y
```

For Nice!View shields only, also disable the built-in Nice!View status screen:

```conf
CONFIG_NICE_VIEW_WIDGET_STATUS=n
```

### Nice!View color polarity

Nice!View uses black for a set pixel and white for a clear pixel. ZMK SVG defaults to black artwork on a white background; leave `CONFIG_NICE_VIEW_WIDGET_INVERTED` unset for this usual appearance. You can reverse black and white by enabling the Nice!View option in each half's configuration:

```conf
CONFIG_NICE_VIEW_WIDGET_INVERTED=y
```

Inverted white-on-black LVGL text can appear thinner. If that is undesirable, leave the inversion option unset. If it must be enabled for another part of the display but ZMK SVG should stay black-on-white, set this module option in each half's configuration:

```conf
CONFIG_ZMK_SVG_WHITE_BACKGROUND=y
```

To highlight the right side in the split indicator, set this only in the right half's configuration:

```conf
CONFIG_ZMK_SVG_RIGHT_HALF=y
```

Keep `nice_view` in the shield list for Nice!View panels. For SSD1306 panels, enable `ZMK_DISPLAY` in the shield configuration. The module requires `ZMK_DISPLAY` and Settings; native layouts support 160 x 68 and 128 x 32. SVG headers are selected at build time from the chosen display's Devicetree dimensions, and a mismatched header stops the build. Split BLE status synchronization is selected automatically for split BLE builds.

The status screen supports generated SVG artwork with `CONFIG_ZMK_SVG_SCREEN=y`. Display dimensions select Nice!View (160 x 68) or OLED (128 x 32); `CONFIG_ZMK_SVG_RIGHT_HALF=y` selects the right-side artwork on either panel. `CONFIG_ZMK_SVG_WHITE_BACKGROUND=y` keeps empty areas white even when legacy Nice!View widget inversion is enabled. See [Screen and Widget Authoring](docs/widget-authoring.md) for the source-to-firmware workflow. Version-1 saved layout records fall back to the version-2 defaults.
