"""Serve a live raster preview for a Nice!View LVGL component XML screen."""

import argparse
import json
import webbrowser
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

if __package__:
    from tools.nice_view_xml import (
        WIDGETS,
        expand_screen_file,
        load_catalog,
        validate_screen_text,
    )
    from tools.nice_view_xml_preview import (
        ROLES,
        preview_png,
        preview_xml_text,
    )
else:
    from nice_view_xml import (
        WIDGETS,
        expand_screen_file,
        load_catalog,
        validate_screen_text,
    )
    from nice_view_xml_preview import ROLES, preview_png, preview_xml_text

TOOLS_DIR = Path(__file__).parent
PAGE_PATH = TOOLS_DIR / "nice_view_svg_live.html"
TEXT_CONTENT_TYPE = "text/plain; charset=utf-8"

RENDERER_BY_TAG = {
    "zmk_status_text": "text",
    "zmk_status_bar": "bar",
    "zmk_status_arc": "ring",
    "zmk_status_when": "visible",
}


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


def _binding_roles(element: ET.Element) -> set[str]:
    role = element.get("role")
    if role is None:
        return set(ROLES)
    if role in ROLES:
        return {role}
    return set(ROLES)


def build_preview_config(
    screen_path: Path,
    initial_role: str = "central",
    legacy_inverted: bool = False,
) -> dict[str, Any]:
    if initial_role not in ROLES:
        raise ValueError(f"unknown display role: {initial_role}")

    fields = load_catalog(TOOLS_DIR / "status_fields.json")
    xml_text = expand_screen_file(screen_path)
    errors = validate_screen_text(xml_text, fields)
    if errors:
        raise ValueError("\n".join(errors))

    root = ET.fromstring(xml_text)
    view = root.find("view")
    if view is None:
        raise ValueError("component must contain a <view>")
    width = int(view.get("width", "160"))
    height = int(view.get("height", "68"))

    bindings: dict[str, dict[str, Any]] = {}
    for element in root.iter():
        if element.tag not in WIDGETS:
            continue
        field_id = element.get("field")
        if not field_id:
            continue
        renderer = RENDERER_BY_TAG[element.tag]
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
        "title": screen_path.name,
        "screenPath": str(screen_path.resolve()),
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
    xml_text: str
    fields: dict[str, Any]


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
            expanded = preview_xml_text(
                self.server.xml_text,
                self.server.fields,
                values,
                role,
            )
            output = Path("/tmp") / f"nice_view_xml_live_{id(self)}.png"
            screen_path_value = self.server.preview_config.get("screenPath")
            screen_path = Path(screen_path_value) if screen_path_value else None
            preview_png(expanded, output, screen_path)
            png_bytes = output.read_bytes()
            if (
                inversion_mode == "legacy"
                and self.server.preview_config["legacyInverted"]
            ):
                png_bytes = _invert_png(png_bytes)
            self._send(200, "image/png", png_bytes)
        except (TypeError, ValueError, RuntimeError, OSError) as error:
            self._send(400, TEXT_CONTENT_TYPE, str(error).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        return


def _invert_png(png_bytes: bytes) -> bytes:
    from io import BytesIO

    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "live preview requires Pillow; run with uv and tools/requirements.txt"
        ) from error
    image = Image.open(BytesIO(png_bytes)).convert("1")
    inverted = Image.eval(image, lambda pixel: 1 - pixel)
    buffer = BytesIO()
    inverted.save(buffer, format="PNG")
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screen", type=Path, help="component XML screen to preview")
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
            arguments.screen, arguments.role, arguments.legacy_inverted
        )
        fields = load_catalog(TOOLS_DIR / "status_fields.json")
        server = LivePreviewServer(("127.0.0.1", arguments.port), LivePreviewHandler)
        server.preview_config = config
        server.xml_text = expand_screen_file(arguments.screen)
        server.fields = fields
    except (OSError, TypeError, ValueError) as error:
        print(error)
        return 1

    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Nice!View LVGL XML live preview: {url}", flush=True)
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
