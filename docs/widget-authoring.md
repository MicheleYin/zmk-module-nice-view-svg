# Screen and Widget Authoring

Nice!view Plus screens are authored as SVGs at the panel's native 160 x 68 resolution. The SVG contains static artwork and marks dynamic fields with `data-nvp-*` attributes. Host tools rasterize the artwork and generate LVGL bindings; firmware does not parse SVG. This is a source-and-preview workflow, not a visual editor.

## Ready-to-Use Screens

These complete examples validate against the current widget and status-field catalogs:

- [three-column.svg](examples/three-column.svg) places battery, layer, and host status in narrow columns, with BLE profiles along the bottom.
- [compact.svg](examples/compact.svg) emphasizes two battery readings and a large layer index, with host and split status in a footer.
- [widget-example.svg](widget-example.svg) demonstrates individual widget types and conditional USB/BLE artwork.
- [screens/default.svg](screens/default.svg), [screens/day.svg](screens/day.svg), and [screens/night.svg](screens/night.svg) are the themes used by the firmware.

To inspect an example, run these commands from the module root:

```sh
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py validate docs/examples/three-column.svg
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py preview docs/examples/three-column.svg --values tools/sample_status.central.json --role central --output /tmp/three-column-central.png
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py preview docs/examples/three-column.svg --values tools/sample_status.peripheral.json --role peripheral --output /tmp/three-column-peripheral.png
```

The preview-only `--rotate-180` switch rotates a PNG for inspection. It does not alter firmware output or rotate the physical display.

## Use an Example in Firmware

Choose a side and generate its header. For example, to use the three-column screen as the left-side design:

```sh
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py generate docs/examples/three-column.svg --output src/generated_day_screen.h
```

Enable the SVG screen and left-side design in that firmware image:

```conf
CONFIG_ZMK_NICE_VIEW_PLUS=y
CONFIG_ZMK_NICE_VIEW_PLUS_SVG_SCREEN=y
CONFIG_ZMK_NICE_VIEW_PLUS_SVG_THEME_LEFT=y
CONFIG_NICE_VIEW_WIDGET_STATUS=n
```

The `default`, `left`, and `right` selectors load `src/generated_screen.h`, `src/generated_day_screen.h`, and `src/generated_night_screen.h`, respectively. The left and right generated headers currently use the sun/day and moon/night artwork from `docs/screens/day.svg` and `docs/screens/night.svg`. Generating an example into one of those paths replaces that header; keep its source SVG so it can be regenerated later. The Sofle build matrix selects left on the left half and right on the right half.

## Authoring Rules

1. Set `viewBox="0 0 160 68"`. Use black and white fills for the monochrome panel.
2. Put each logical widget inside an SVG `<g>` with a unique `id` and a `data-nvp-widget` type from `tools/widget_types.json`.
3. Put dynamic elements inside their widget. Each needs a supported `data-nvp-slot`, `data-nvp-bind` field from `tools/status_fields.json`, and `data-nvp-render` renderer.
4. Add `data-nvp-role="peripheral"` for values unavailable on the central display, or `data-nvp-role="central"` for central-only fields.
5. Validate and preview for both central and peripheral roles before generating a firmware header.

`text` replaces a `<text>` element's content. `percent` formats a percent value with `%`. `bar` scales a `<rect>`'s width from zero to 100 percent. `ring` overlays a circular progress arc on a `<circle>` using `cx`, `cy`, `r`, and `stroke-width`; it starts at 12 o'clock and fills clockwise. Use `fill="none"`, a visible stroke, and no transforms on its ancestors; the ring itself may use `rotate(-90 cx cy)` to start at 12 o'clock. Add `stroke-linecap="round"` for rounded arc ends, and keep a separate unbound circle behind it for a track. `visible` shows an element only when its value matches `data-nvp-when`. Unavailable values remain hidden.

For bitmask fields such as `ble.connected_profiles`, use `data-nvp-when="set"` and a zero-based `data-nvp-bit` for an individual profile connection marker. Use `data-nvp-when="clear"` for the opposite state.

For example, an endpoint widget can use different icon shapes for USB and BLE:

```xml
<g id="connection" data-nvp-widget="connection">
  <g data-nvp-slot="selected" data-nvp-bind="output.selected"
      data-nvp-render="visible" data-nvp-when="usb"
      data-nvp-bounds="4,48,43,15">
    <!-- USB icon paths and shapes -->
  </g>
  <g data-nvp-slot="selected" data-nvp-bind="output.selected"
      data-nvp-render="visible" data-nvp-when="ble"
      data-nvp-bounds="4,48,43,15">
    <!-- BLE icon paths and shapes -->
  </g>
</g>
```

Edit the SVG paths inside a state group to change its icon. The generator rasterizes each conditional element/group into a transparent I2 image; firmware creates a bounded LVGL image object and hides or shows it as the field changes. Rectangles and circles get crop bounds from their geometry. For paths, text, or groups, provide `data-nvp-bounds="x,y,width,height"` in screen coordinates so the generator can crop the asset without capturing neighboring art. Keep dynamic groups small. Nested bindings are unsupported.

To add a widget kind, add its slots to `tools/widget_types.json`. A slot declares compatible field IDs, renderers, and whether at least one bound part is required. The validator checks these declarations against the screen SVG and status field catalog.

## Validate and Preview

`rsvg-convert` must be installed for previews and generation; Pillow is supplied through isolated `uv` commands. Run these commands from the module root:

```sh
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py validate docs/widget-example.svg
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py preview docs/widget-example.svg --values tools/sample_status.central.json --role central --output /tmp/widget-central.png
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py preview docs/widget-example.svg --values tools/sample_status.peripheral.json --role peripheral --output /tmp/widget-peripheral.png
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py generate docs/screens/default.svg --output src/generated_screen.h
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py generate docs/screens/day.svg --output src/generated_day_screen.h
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_svg.py generate docs/screens/night.svg --output src/generated_night_screen.h
```

The preview applies fixture values to bound text, bars, and conditional shapes. SVGs are limited to 22 dynamic bindings. Physical `battery.left.*` and `battery.right.*` fields use `CONFIG_ZMK_NICE_VIEW_PLUS_CENTRAL_RIGHT_HALF` to map central/peripheral providers to physical sides; set it consistently for both halves if the central is physically on the right.

## Firmware Setup

The renderer creates LVGL objects for dynamic bindings, up to the 22-binding guardrail, plus the background. The 16 KiB pool remains enabled; verify key responsiveness on flashed devices before treating a design as production-ready.

The available bindings include physical and role-based battery percentages/charge, active layer index/name, endpoint, USB powered/HID-ready, BLE profile state/count, display half, split connectivity, and optional WPM. USB and WPM providers are compiled only when their corresponding ZMK features are enabled. Profile-count-driven repetition is not automatic; define the desired profile tiles in the SVG. Arbitrary SVG parsing on-device is not part of the design.
