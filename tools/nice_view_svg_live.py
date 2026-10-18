"""Serve a live raster preview for a Nice!view SVG screen."""

import argparse
import json
import webbrowser
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

if __package__:
    from tools.nice_view_svg import (
        ROLES,
        _binding_roles,
        _monochrome_preview_png,
        _rasterize_png,
        load_catalog,
        load_widget_catalog,
        preview_svg_text,
        validate_svg_text,
    )
else:
    from nice_view_svg import (
        ROLES,
        _binding_roles,
        _monochrome_preview_png,
        _rasterize_png,
        load_catalog,
        load_widget_catalog,
        preview_svg_text,
        validate_svg_text,
    )

TOOLS_DIR = Path(__file__).parent
PAGE_PATH = TOOLS_DIR / "nice_view_svg_live.html"
TEXT_CONTENT_TYPE = "text/plain; charset=utf-8"


def _default_value(field: dict[str, Any]) -> Any:
    field_type = field["type"]
    if field_type == "enum":
        return field["values"][0]
    if field_type == "boolean":
        return False
    if field_type == "bitmask":
        return 0
    if field_type == "string":
        return field.get("default", "")
    return field.get("minimum", 0)


def build_preview_config(
    svg_path: Path,
    initial_role: str = "central",
    legacy_inverted: bool = False,
) -> dict[str, Any]:
    if initial_role not in ROLES:
        raise ValueError(f"unknown display role: {initial_role}")

    fields = load_catalog(TOOLS_DIR / "status_fields.json")
    widget_catalog = load_widget_catalog(TOOLS_DIR / "widget_types.json")
    svg_text = svg_path.read_text()
    errors = validate_svg_text(svg_text, fields, widget_catalog=widget_catalog)
    if errors:
        raise ValueError("\n".join(errors))

    root = ET.fromstring(svg_text)
    view_box = root.get("viewBox", "").replace(",", " ").split()
    width, height = int(view_box[2]), int(view_box[3])
    bindings: dict[str, dict[str, Any]] = {}
    for element in root.iter():
        field_id = element.get("data-nvp-bind")
        renderer = element.get("data-nvp-render")
        if field_id is None or renderer is None:
            continue
        binding = bindings.setdefault(
            field_id,
            {
                **fields[field_id],
                "id": field_id,
                "roles": set(),
                "renderers": set(),
            },
        )
        binding["roles"].update(_binding_roles(element))
        binding["renderers"].add(renderer)

    descriptors = []
    for binding in bindings.values():
        binding["roles"] &= set(binding["available_on"])
        binding["roles"] = sorted(binding["roles"])
        binding["renderers"] = sorted(binding["renderers"])
        if binding["type"] == "bitmask":
            binding["bits"] = min(32, max(1, binding.get("maximum", 255).bit_length()))
        descriptors.append(binding)

    values_by_role = {}
    for role in ROLES:
        fixture_path = TOOLS_DIR / f"sample_status.{role}.json"
        fixture = json.loads(fixture_path.read_text()).get("values", {})
        values_by_role[role] = {
            binding["id"]: fixture.get(binding["id"], _default_value(binding))
            for binding in descriptors
        }

    return {
        "title": svg_path.name,
        "width": width,
        "height": height,
        "initialRole": initial_role,
        "legacyInverted": legacy_inverted,
        "initialInversionMode": "legacy",
        "bindings": descriptors,
        "values": values_by_role,
    }


class LivePreviewServer(ThreadingHTTPServer):
    preview_config: dict[str, Any]
    svg_text: str
    fields: dict[str, Any]
    widget_catalog: dict[str, Any]


class LivePreviewHandler(BaseHTTPRequestHandler):
    server: LivePreviewServer

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            self._send(200, "text/html; charset=utf-8", PAGE_PATH.read_bytes())
        elif path == "/config":
            body = json.dumps(self.server.preview_config).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        else:
            self._send(404, TEXT_CONTENT_TYPE, b"Not found")

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/render":
            self._send(404, TEXT_CONTENT_TYPE, b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ValueError("invalid request size")
            request = json.loads(self.rfile.read(length))
            role = request.get("role")
            values = request.get("values")
            inversion_mode = request.get("inversionMode", "legacy")
            if role not in ROLES or not isinstance(values, dict):
                raise ValueError("request needs a role and values object")
            if inversion_mode not in {"legacy", "white-background"}:
                raise ValueError("unknown inversion mode")
            svg = preview_svg_text(
                self.server.svg_text,
                self.server.fields,
                values,
                role,
                self.server.widget_catalog,
            )
            inverted = (
                inversion_mode == "legacy"
                and self.server.preview_config["legacyInverted"]
            )
            self._send(
                200,
                "image/png",
                _monochrome_preview_png(_rasterize_png(svg), inverted),
            )
        except (TypeError, ValueError, RuntimeError) as error:
            self._send(400, TEXT_CONTENT_TYPE, str(error).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path, help="screen SVG to preview")
    parser.add_argument("--role", choices=sorted(ROLES), default="central")
    parser.add_argument(
        "--legacy-inverted",
        action="store_true",
        help="preview the legacy CONFIG_NICE_VIEW_WIDGET_INVERTED output",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args(argv)

    try:
        config = build_preview_config(
            arguments.svg, arguments.role, arguments.legacy_inverted
        )
        fields = load_catalog(TOOLS_DIR / "status_fields.json")
        widget_catalog = load_widget_catalog(TOOLS_DIR / "widget_types.json")
        server = LivePreviewServer(("127.0.0.1", arguments.port), LivePreviewHandler)
        server.preview_config = config
        server.svg_text = arguments.svg.read_text()
        server.fields = fields
        server.widget_catalog = widget_catalog
    except (OSError, TypeError, ValueError) as error:
        print(error)
        return 1

    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Nice!view live preview: {url}", flush=True)
    if not arguments.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping live preview.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
