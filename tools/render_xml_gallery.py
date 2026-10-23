"""Render paired PNG previews for the XML screen and widget gallery."""

from __future__ import annotations

import argparse
from pathlib import Path

if __package__:
    from tools.nice_view_xml import load_catalog
    from tools.nice_view_xml_components import expand_screen_file
    from tools.nice_view_xml_live import build_preview_config
    from tools.nice_view_xml_preview import preview_png, preview_xml_text
else:
    from nice_view_xml import load_catalog
    from nice_view_xml_components import expand_screen_file
    from nice_view_xml_live import build_preview_config
    from nice_view_xml_preview import preview_png, preview_xml_text

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "docs" / "ui" / "screens"
DEFAULT_OUTPUT = ROOT / "docs" / "ui" / "gallery"
WASM_RENDERER = ROOT / "build" / "lvgl_wasm" / "web" / "preview.js"

PAIRS = (
    (
        "nice-view",
        SCREENS / "nice-view-left.xml",
        SCREENS / "nice-view-right.xml",
    ),
    (
        "oled",
        SCREENS / "oled-left.xml",
        SCREENS / "oled-right.xml",
    ),
)


def render_pair(name: str, left: Path, right: Path, output_dir: Path) -> None:
    fields = load_catalog(ROOT / "tools" / "status_fields.json")
    for side, screen, role in (
        ("left", left, "central"),
        ("right", right, "peripheral"),
    ):
        config = build_preview_config(screen, role)
        xml_text = expand_screen_file(screen)
        rendered_xml = preview_xml_text(xml_text, fields, config["values"][role], role)
        preview_png(rendered_xml, output_dir / f"{name}-{side}.png", screen)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    if not WASM_RENDERER.is_file():
        parser.error(
            "build the LVGL renderer first with emcmake cmake -S tools/lvgl_wasm "
            "-B build/lvgl_wasm && cmake --build build/lvgl_wasm"
        )
    for name, left, right in PAIRS:
        render_pair(name, left, right, arguments.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
