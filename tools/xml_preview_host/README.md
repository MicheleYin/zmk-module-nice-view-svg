# LVGL XML host preview

Host-side rendering for LVGL component XML used by `nice_view_xml_live.py` and
`nice_view_xml.py preview`.

## Quick render (Python)

From the module root:

```sh
uv run --isolated --with-requirements tools/requirements.txt \
  python tools/xml_preview_host/render_png.py \
  docs/ui/screens/status_screen.xml \
  --values tools/sample_status.central.json \
  --role central \
  --output /tmp/status.png
```

When `tools/lvgl_wasm/build/web/preview.js` is built, rendering uses the
WebAssembly LVGL XML runtime. Otherwise a lightweight 1-bit Pillow rasterizer
draws expanded labels and bars (same expansion path as firmware bindings).

## Optional native SDL build

A full SDL + `LV_USE_XML` binary can link against the LVGL tree from a ZMK west
workspace (`modules/lib/gui/lvgl` at the revision pinned in your manifest). That
path is optional; the Python renderer above is the supported default for live
preview without a west checkout.

```sh
# Example (requires ZEPHYR_BASE / west lvgl path on your machine):
cmake -S tools/xml_preview_host -B tools/xml_preview_host/build \
  -DLVGL_DIR=$WEST_TOPDIR/modules/lib/gui/lvgl
cmake --build tools/xml_preview_host/build
```

The CMake target is a stub until `LVGL_DIR` is provided; use `render_png.py` for
day-to-day authoring.
