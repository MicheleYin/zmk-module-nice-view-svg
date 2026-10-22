"""Serve a live raster preview for a Nice!view SVG screen."""

import argparse
import hashlib
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


def build_live_preview_config(
    sources: dict[str, dict[str, Path]],
    central_side: str = "left",
    legacy_inverted: bool = False,
) -> dict[str, Any]:
    if central_side not in {"left", "right"}:
        raise ValueError(f"unknown central side: {central_side}")

    displays: dict[str, Any] = {}
    for display, paths in sources.items():
        if set(paths) != {"left", "right"}:
            raise ValueError(f"{display} needs left and right SVG sources")
        screens = {
            side: build_preview_config(path, legacy_inverted=legacy_inverted)
            for side, path in paths.items()
        }
        dimensions = {
            (screen["width"], screen["height"]) for screen in screens.values()
        }
        if len(dimensions) != 1:
            raise ValueError(
                f"{display} left and right SVGs must have matching dimensions"
            )
        bindings_by_id: dict[str, dict[str, Any]] = {}
        for screen in screens.values():
            for descriptor in screen["bindings"]:
                binding = bindings_by_id.get(descriptor["id"])
                if binding is None:
                    bindings_by_id[descriptor["id"]] = {
                        **descriptor,
                        "roles": set(descriptor["roles"]),
                        "renderers": set(descriptor["renderers"]),
                    }
                else:
                    binding["roles"].update(descriptor["roles"])
                    binding["renderers"].update(descriptor["renderers"])

        bindings = []
        for binding in bindings_by_id.values():
            binding["roles"] = sorted(binding["roles"])
            binding["renderers"] = sorted(binding["renderers"])
            bindings.append(binding)
        values_by_role = {
            role: {
                binding["id"]: fixture_value
                for binding in bindings
                if (fixture_value := next(
                    (
                        screen["values"][role][binding["id"]]
                        for screen in screens.values()
                        if binding["id"] in screen["values"][role]
                    ),
                    _default_value(binding),
                )) is not None
            }
            for role in ROLES
        }
        displays[display] = {
            "screens": {
                side: {
                    "title": screen["title"],
                    "width": screen["width"],
                    "height": screen["height"],
                    "bindings": screen["bindings"],
                }
                for side, screen in screens.items()
            },
            "bindings": bindings,
            "values": values_by_role,
        }

    if not displays:
        raise ValueError("at least one display source set is required")
    return {
        "title": "Two-Sided SVG Preview",
        "initialCentralSide": central_side,
        "initialDisplay": "niceview" if "niceview" in displays else next(iter(displays)),
        "legacyInverted": legacy_inverted,
        "initialInversionMode": "legacy",
        "displays": displays,
    }


class LivePreviewServer(ThreadingHTTPServer):
    preview_config: dict[str, Any]
    sources: dict[str, dict[str, Path]]
    svg_texts: dict[str, dict[str, str]]
    source_revision: str
    source_error: str | None
    fields: dict[str, Any]
    widget_catalog: dict[str, Any]

    def refresh_sources(self) -> None:
        try:
            svg_texts = {
                display: {side: path.read_text() for side, path in paths.items()}
                for display, paths in self.sources.items()
            }
            preview_config = build_live_preview_config(
                self.sources,
                legacy_inverted=self.preview_config["legacyInverted"],
            )
            revision = hashlib.sha256(
                json.dumps(svg_texts, sort_keys=True).encode("utf-8")
            ).hexdigest()
        except (OSError, TypeError, ValueError) as error:
            self.source_error = str(error)
            return

        if revision != getattr(self, "source_revision", None):
            self.svg_texts = svg_texts
            self.preview_config = preview_config
            self.source_revision = revision
        self.source_error = None


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
            self.server.refresh_sources()
            config = {
                **self.server.preview_config,
                "revision": self.server.source_revision,
                "reloadError": getattr(self.server, "source_error", None),
            }
            body = json.dumps(config).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        else:
            self._send(404, TEXT_CONTENT_TYPE, b"Not found")

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/render":
            self._send(404, TEXT_CONTENT_TYPE, b"Not found")
            return
        try:
            self.server.refresh_sources()
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ValueError("invalid request size")
            request = json.loads(self.rfile.read(length))
            display = request.get("display")
            side = request.get("side")
            central_side = request.get(
                "centralSide", self.server.preview_config["initialCentralSide"]
            )
            values = request.get("values")
            inversion_mode = request.get("inversionMode", "legacy")
            if (
                display not in self.server.sources
                or side not in {"left", "right"}
                or central_side not in {"left", "right"}
                or not isinstance(values, dict)
            ):
                raise ValueError(
                    "request needs a display, side, central side, and values"
                )
            if inversion_mode not in {"legacy", "white-background"}:
                raise ValueError("unknown inversion mode")
            role = "central" if side == central_side else "peripheral"
            svg_path = self.server.sources[display][side]
            svg = preview_svg_text(
                self.server.svg_texts[display][side],
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
                _monochrome_preview_png(
                    _rasterize_png(svg, base_path=svg_path), inverted
                ),
            )
        except (TypeError, ValueError, RuntimeError) as error:
            self._send(400, TEXT_CONTENT_TYPE, str(error).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "svg",
        type=Path,
        nargs="?",
        help="left-side SVG; a matching right-side sibling is used when present",
    )
    parser.add_argument(
        "--right-svg", type=Path, help="explicit right-side SVG, overriding sibling inference"
    )
    parser.add_argument("--panel", choices=("niceview", "oled"))
    parser.add_argument("--central-side", choices=("left", "right"), default="left")
    parser.add_argument(
        "--legacy-inverted",
        action="store_true",
        help="preview the legacy CONFIG_NICE_VIEW_WIDGET_INVERTED output",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args(argv)

    try:
        screen_directory = Path(__file__).resolve().parent.parent / "docs" / "screens"
        sources: dict[str, dict[str, Path]] = {
            "niceview": {
                side: screen_directory / f"niceview-{side}.svg"
                for side in ("left", "right")
            },
            "oled": {
                side: screen_directory / f"oled-{side}.svg"
                for side in ("left", "right")
            },
        }
        if arguments.svg is not None:
            display = arguments.panel or (
                "oled" if arguments.svg.name.startswith("oled-") else "niceview"
            )
            sources[display]["left"] = arguments.svg
            if arguments.right_svg is not None:
                sources[display]["right"] = arguments.right_svg
            else:
                inferred_right = arguments.svg.with_name(
                    arguments.svg.name.replace("left", "right", 1)
                )
                sources[display]["right"] = (
                    inferred_right if inferred_right.exists() else arguments.svg
                )
        if arguments.right_svg is not None and arguments.svg is None:
            raise ValueError("--right-svg requires a left-side SVG argument")

        config = build_live_preview_config(
            sources, arguments.central_side, arguments.legacy_inverted
        )
        fields = load_catalog(TOOLS_DIR / "status_fields.json")
        widget_catalog = load_widget_catalog(TOOLS_DIR / "widget_types.json")
        server = LivePreviewServer(("127.0.0.1", arguments.port), LivePreviewHandler)
        server.sources = sources
        server.svg_texts = {
            display: {side: path.read_text() for side, path in paths.items()}
            for display, paths in sources.items()
        }
        server.source_revision = hashlib.sha256(
            json.dumps(server.svg_texts, sort_keys=True).encode("utf-8")
        ).hexdigest()
        server.source_error = None
        server.preview_config = config
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
