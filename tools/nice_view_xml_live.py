"""Serve a live raster preview for a Nice!View LVGL component XML screen."""

import argparse
import json
import threading
import webbrowser
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

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
    dependencies: set[Path] | None = None,
) -> dict[str, Any]:
    if initial_role not in ROLES:
        raise ValueError(f"unknown display role: {initial_role}")

    fields = load_catalog(TOOLS_DIR / "status_fields.json")
    xml_text = expand_screen_file(screen_path, dependencies)
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


def build_paired_preview_config(
    left_screen: Path,
    right_screen: Path,
    left_role: str = "central",
    right_role: str = "peripheral",
    legacy_inverted: bool = False,
    dependencies: set[Path] | None = None,
) -> dict[str, Any]:
    left = build_preview_config(left_screen, left_role, legacy_inverted, dependencies)
    right = build_preview_config(right_screen, right_role, legacy_inverted, dependencies)
    bindings: dict[str, dict[str, Any]] = {}
    for config in (left, right):
        for binding in config["bindings"]:
            merged = bindings.setdefault(
                binding["id"],
                {**binding, "roles": set(), "renderers": set()},
            )
            merged["roles"].update(binding["roles"])
            merged["renderers"].update(binding["renderers"])

    descriptors = []
    for binding in bindings.values():
        binding["roles"] = sorted(binding["roles"])
        binding["renderers"] = sorted(binding["renderers"])
        descriptors.append(binding)

    values = {}
    for role in ROLES:
        values[role] = {}
        for field_id in bindings:
            if field_id in left["values"][role]:
                value = left["values"][role][field_id]
            elif field_id in right["values"][role]:
                value = right["values"][role][field_id]
            else:
                value = _default_value(bindings[field_id])
            values[role][field_id] = value

    return {
        "title": f"{left_screen.name} + {right_screen.name}",
        "paired": True,
        "initialRole": "both",
        "initialInversionMode": "legacy",
        "legacyInverted": legacy_inverted,
        "panelRoles": {"left": left_role, "right": right_role},
        "screens": {
            "left": {
                "screenPath": left["screenPath"],
                "width": left["width"],
                "height": left["height"],
            },
            "right": {
                "screenPath": right["screenPath"],
                "width": right["width"],
                "height": right["height"],
            },
        },
        "bindings": descriptors,
        "values": values,
    }


class LivePreviewServer(ThreadingHTTPServer):
    preview_config: dict[str, Any]
    xml_text: str
    panel_xml_texts: dict[str, str]
    fields: dict[str, Any]
    screen_paths: tuple[Path, ...]
    left_role: str
    right_role: str
    legacy_inverted: bool
    observer: Observer
    watched_dirs: set[Path]
    state_lock: threading.RLock
    change_condition: threading.Condition
    revision: int
    reload_error: str | None

    def watch_dependencies(self, dependencies: set[Path]) -> None:
        for dependency in dependencies:
            directory = dependency.parent
            while not directory.exists() and directory != directory.parent:
                directory = directory.parent
            if directory in self.watched_dirs or not directory.is_dir():
                continue
            self.observer.schedule(_DebouncedFileHandler(self), str(directory), recursive=True)
            self.watched_dirs.add(directory)

    def reload_sources(self) -> bool:
        dependencies: set[Path] = set()
        try:
            if len(self.screen_paths) == 2:
                left_path, right_path = self.screen_paths
                config = build_paired_preview_config(
                    left_path,
                    right_path,
                    self.left_role,
                    self.right_role,
                    self.legacy_inverted,
                    dependencies,
                )
                panel_xml_texts = {
                    "left": expand_screen_file(left_path),
                    "right": expand_screen_file(right_path),
                }
                xml_text = ""
            else:
                screen_path = self.screen_paths[0]
                config = build_preview_config(
                    screen_path,
                    self.left_role,
                    self.legacy_inverted,
                    dependencies,
                )
                xml_text = expand_screen_file(screen_path)
                panel_xml_texts = {}
        except (OSError, TypeError, ValueError) as error:
            self.watch_dependencies(dependencies)
            self.publish_change(str(error))
            return False

        self.watch_dependencies(dependencies)
        with self.state_lock:
            self.preview_config = config
            self.xml_text = xml_text
            self.panel_xml_texts = panel_xml_texts
        self.publish_change(None)
        return True

    def publish_change(self, error: str | None) -> None:
        with self.change_condition:
            self.revision += 1
            self.reload_error = error
            self.change_condition.notify_all()


class _DebouncedFileHandler(FileSystemEventHandler):
    def __init__(self, server: LivePreviewServer) -> None:
        self.server = server
        self.lock = threading.Lock()
        self.timer: threading.Timer | None = None

    def on_any_event(self, event: Any) -> None:
        if event.is_directory:
            return
        with self.lock:
            if self.timer is not None:
                self.timer.cancel()
            self.timer = threading.Timer(0.2, self.server.reload_sources)
            self.timer.daemon = True
            self.timer.start()


def _select_preview_source(
    server: LivePreviewServer, panel: str | None, role: str
) -> tuple[str, str | None]:
    if not server.preview_config.get("paired"):
        with server.state_lock:
            return server.xml_text, server.preview_config.get("screenPath")
    if panel not in {"left", "right"}:
        raise ValueError("paired preview needs a left or right panel")
    if role != server.preview_config["panelRoles"][panel]:
        raise ValueError("role does not match the selected preview panel")
    with server.state_lock:
        screen = server.preview_config["screens"][panel]
        return server.panel_xml_texts[panel], screen["screenPath"]


class LivePreviewHandler(BaseHTTPRequestHandler):
    server: LivePreviewServer

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            self._send(200, "text/html; charset=utf-8", PAGE_PATH.read_bytes())
        elif path == "/config":
            with self.server.state_lock:
                body = json.dumps(self.server.preview_config).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        elif path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            revision = -1
            while True:
                with self.server.change_condition:
                    self.server.change_condition.wait_for(
                        lambda: self.server.revision != revision, timeout=15
                    )
                    revision = self.server.revision
                    payload = json.dumps(
                        {"revision": revision, "error": self.server.reload_error}
                    )
                try:
                    self.wfile.write(f"event: change\ndata: {payload}\n\n".encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
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
            panel = request.get("panel")
            values = request.get("values")
            inversion_mode = request.get("inversionMode", "legacy")
            if role not in ROLES or not isinstance(values, dict):
                raise ValueError("request needs a role and values object")
            xml_text, screen_path_value = _select_preview_source(
                self.server, panel, role
            )
            if inversion_mode not in {"legacy", "white-background"}:
                raise ValueError("unknown inversion mode")
            expanded = preview_xml_text(
                xml_text,
                self.server.fields,
                values,
                role,
            )
            output = Path("/tmp") / f"nice_view_xml_live_{id(self)}.png"
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
    parser.add_argument("screen", type=Path, help="screen XML; left screen in paired mode")
    parser.add_argument(
        "--right-screen",
        type=Path,
        help="also preview this XML screen beside the left screen",
    )
    parser.add_argument("--role", choices=sorted(ROLES), default="central")
    parser.add_argument("--left-role", choices=sorted(ROLES), default="central")
    parser.add_argument("--right-role", choices=sorted(ROLES), default="peripheral")
    parser.add_argument(
        "--legacy-inverted",
        action="store_true",
        help="preview the legacy CONFIG_NICE_VIEW_WIDGET_INVERTED output",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args(argv)

    try:
        fields = load_catalog(TOOLS_DIR / "status_fields.json")
        server = LivePreviewServer(("127.0.0.1", arguments.port), LivePreviewHandler)
        server.fields = fields
        server.screen_paths = (
            (arguments.screen.resolve(), arguments.right_screen.resolve())
            if arguments.right_screen
            else (arguments.screen.resolve(),)
        )
        server.left_role = arguments.left_role if arguments.right_screen else arguments.role
        server.right_role = arguments.right_role
        server.legacy_inverted = arguments.legacy_inverted
        server.observer = Observer()
        server.watched_dirs = set()
        server.state_lock = threading.RLock()
        server.change_condition = threading.Condition()
        server.revision = 0
        server.reload_error = None
        if not server.reload_sources():
            server.server_close()
            return 1
        server.observer.start()
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
        server.observer.stop()
        server.observer.join()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
