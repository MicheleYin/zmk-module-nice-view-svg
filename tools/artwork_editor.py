"""Image placement settings and transforms for the artwork gallery editor."""

from __future__ import annotations

import json
import io
import mimetypes
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from PIL import Image, ImageOps
from watchdog.observers import Observer

if __package__:
    from tools.nice_view_xml import load_catalog
    from tools.nice_view_xml_live import (
        LivePreviewHandler,
        LivePreviewServer,
        available_screen_choices,
        build_preview_config,
    )
    from tools.nice_view_xml_components import expand_screen_file
    from tools.nice_view_xml_preview import preview_png, preview_xml_text
    from tools.screen_designer import (
        HALVES,
        PROFILE_SIZES,
        ROOT,
        export_profile_design,
        load_profile_design,
        load_visual_modules,
        save_profile_design,
        validate_screen_design,
        write_profile_preview,
    )
else:
    from nice_view_xml import load_catalog
    from nice_view_xml_live import (
        LivePreviewHandler,
        LivePreviewServer,
        available_screen_choices,
        build_preview_config,
    )
    from nice_view_xml_components import expand_screen_file
    from nice_view_xml_preview import preview_png, preview_xml_text
    from screen_designer import (
        HALVES,
        PROFILE_SIZES,
        ROOT,
        export_profile_design,
        load_profile_design,
        load_visual_modules,
        save_profile_design,
        validate_screen_design,
        write_profile_preview,
    )

SETTINGS_FILE = ".artwork-settings.json"
PROFILES = {
    "nice-view": (160, 68),
    "oled": (128, 32),
}
DEFAULT_PROFILE = "nice-view"
DEFAULT_ROTATIONS = {"blossom-meadow.jpeg": 90}
SUPPORTED_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
PAGE_PATH = Path(__file__).with_name("artwork_editor.html")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def load_settings(input_dir: Path) -> dict[str, Any]:
    path = input_dir / SETTINGS_FILE
    if not path.is_file():
        return {"profile": DEFAULT_PROFILE, "images": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    profile = data.get("profile", DEFAULT_PROFILE)
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    images = data.get("images", {})
    return {"profile": profile, "images": images if isinstance(images, dict) else {}}


def settings_for_image(settings: dict[str, Any], name: str) -> dict[str, Any]:
    stored = settings.get("images", {}).get(name, {})
    if not isinstance(stored, dict):
        stored = {}
    fit = stored.get("fit", "cover")
    if fit not in {"cover", "contain"}:
        fit = "cover"
    rotation = stored.get("rotation", DEFAULT_ROTATIONS.get(name, 0))
    if rotation not in {0, 90, 180, 270}:
        rotation = DEFAULT_ROTATIONS.get(name, 0)
    try:
        x = min(1.0, max(0.0, float(stored.get("x", 0.5))))
        y = min(1.0, max(0.0, float(stored.get("y", 0.5))))
    except (TypeError, ValueError):
        x, y = 0.5, 0.5
    return {"fit": fit, "x": x, "y": y, "rotation": rotation}


def fit_image(
    image: Image.Image, size: tuple[int, int], settings: dict[str, Any]
) -> Image.Image:
    rotation = settings["rotation"]
    if rotation:
        image = image.rotate(rotation, expand=True)

    if settings["fit"] == "cover":
        return ImageOps.fit(
            image,
            size,
            method=Image.Resampling.LANCZOS,
            centering=(settings["x"], settings["y"]),
        )

    contained = ImageOps.contain(image, size, method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (255, 255, 255, 255))
    position = (
        round((size[0] - contained.width) * settings["x"]),
        round((size[1] - contained.height) * settings["y"]),
    )
    canvas.alpha_composite(contained, position)
    return canvas


def save_settings(input_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    profile = data.get("profile", DEFAULT_PROFILE)
    images = data.get("images", {})
    if profile not in PROFILES or not isinstance(images, dict):
        raise ValueError("invalid artwork settings")

    clean_images = {}
    for name, value in images.items():
        path = Path(name)
        if path.name != name or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"invalid artwork filename: {name}")
        if not (input_dir / name).is_file():
            raise ValueError(f"artwork not found: {name}")
        if not isinstance(value, dict):
            raise ValueError(f"invalid settings for {name}")
        normalized = settings_for_image({"images": {name: value}}, name)
        if value.get("fit", "cover") not in {"cover", "contain"}:
            raise ValueError(f"invalid fit mode for {name}")
        for coordinate in ("x", "y"):
            try:
                number = float(value.get(coordinate, 0.5))
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid {coordinate} position for {name}") from error
            if not 0 <= number <= 1:
                raise ValueError(f"invalid {coordinate} position for {name}")
        rotation = value.get("rotation", normalized["rotation"])
        if rotation not in {0, 90, 180, 270}:
            raise ValueError(f"invalid rotation for {name}")
        normalized["rotation"] = rotation
        clean_images[name] = normalized

    payload = {"profile": profile, "images": clean_images}
    (input_dir / SETTINGS_FILE).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return payload


class ArtworkEditorServer(ThreadingHTTPServer):
    input_dir: Path
    xml_preview_url: str
    preview_server: LivePreviewServer


class ArtworkEditorHandler(BaseHTTPRequestHandler):
    server: ArtworkEditorServer

    def _read_json(self) -> dict[str, Any]:
        body = self._read_body()
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def _render_design_preview(self, side: str) -> bytes:
        if side not in HALVES:
            raise ValueError("preview side must be left or right")
        preview_server = self.server.preview_server
        role = "central" if side == "left" else "peripheral"
        with preview_server.state_lock:
            screen_path = preview_server.screen_paths[HALVES.index(side)]
            fields = preview_server.fields
            values = preview_server.preview_config["values"][role]
        xml_text = expand_screen_file(screen_path)
        rendered = preview_xml_text(xml_text, fields, values, role)
        with tempfile.TemporaryDirectory(prefix="screen-designer-preview-") as directory:
            output = Path(directory) / "preview.png"
            preview_png(rendered, output, screen_path)
            return output.read_bytes()

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: Any) -> None:
        self._send(
            status,
            "application/json; charset=utf-8",
            json.dumps(data).encode("utf-8"),
        )

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            raise ValueError("request body is empty or too large")
        return self.rfile.read(length)

    def _image_path(self, name: str) -> Path:
        path = Path(name)
        if path.name != name or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError("unsupported image")
        image_path = self.server.input_dir / name
        if not image_path.is_file():
            raise ValueError("image not found")
        return image_path

    def do_GET(self) -> None:
        path = urlsplit(self.path)
        if path.path in {"/", "/index.html"}:
            self._send(200, "text/html; charset=utf-8", PAGE_PATH.read_bytes())
            return
        if path.path == "/api/settings":
            self._json(200, load_settings(self.server.input_dir))
            return
        if path.path == "/api/modules":
            modules = load_visual_modules()
            self._json(200, {"modules": list(modules.values())})
            return
        if path.path == "/api/design":
            query = parse_qs(path.query)
            profile = query.get("profile", [DEFAULT_PROFILE])[0]
            if profile not in PROFILE_SIZES:
                self._json(400, {"error": "unknown display profile"})
                return
            self._json(
                200,
                {"profile": profile, "halves": load_profile_design(profile)},
            )
            return
        if path.path == "/api/design/preview":
            query = parse_qs(path.query)
            try:
                png = self._render_design_preview(query.get("side", ["left"])[0])
            except (OSError, TypeError, ValueError, RuntimeError) as error:
                self._json(400, {"error": str(error)})
                return
            self._send(200, "image/png", png)
            return
        if path.path == "/api/xml-preview":
            self._json(200, {"url": self.server.xml_preview_url})
            return
        if path.path == "/api/images":
            settings = load_settings(self.server.input_dir)
            images = []
            for image_path in sorted(self.server.input_dir.iterdir()):
                if not image_path.is_file() or image_path.suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue
                try:
                    with Image.open(image_path) as image:
                        images.append(
                            {
                                "name": image_path.name,
                                "width": image.width,
                                "height": image.height,
                                "frames": getattr(image, "n_frames", 1),
                                **settings_for_image(settings, image_path.name),
                            }
                        )
                except OSError:
                    continue
            self._json(200, {"profile": settings["profile"], "images": images})
            return
        if path.path.startswith("/api/image/"):
            try:
                image_path = self._image_path(unquote(path.path.removeprefix("/api/image/")))
            except ValueError as error:
                self._json(404, {"error": str(error)})
                return
            content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
            self._send(200, content_type, image_path.read_bytes())
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            body = self._read_body()
            if path == "/api/settings":
                data = json.loads(body)
                self._json(200, save_settings(self.server.input_dir, data))
                return
            if path in {"/api/design/preview", "/api/design/save", "/api/design/build"}:
                data = json.loads(body)
                profile = data.get("profile")
                halves = data.get("halves")
                if profile not in PROFILE_SIZES or not isinstance(halves, dict):
                    raise ValueError("design needs a valid profile and half layouts")
                for side in HALVES:
                    validate_screen_design(
                        profile,
                        side,
                        halves.get(side, {"background": None, "widgets": []}),
                        self.server.input_dir,
                    )
                if path == "/api/design/preview":
                    screen_paths = write_profile_preview(
                        profile, halves, self.server.input_dir
                    )
                    preview_server = self.server.preview_server
                    preview_server.screen_paths = screen_paths
                    preview_server.screen_choice = f"designer:{profile}"
                    if not preview_server.reload_sources():
                        raise ValueError(
                            preview_server.reload_error or "could not render design"
                        )
                    self._json(200, {"profile": profile, "preview": "ready"})
                    return
                if path == "/api/design/save":
                    save_profile_design(profile, halves, self.server.input_dir)
                    self._json(200, {"profile": profile, "saved": True})
                    return

                screen_paths = export_profile_design(
                    profile, halves, self.server.input_dir
                )
                renderer = ROOT / "build" / "lvgl_wasm" / "web" / "preview.js"
                gallery_built = False
                gallery_message = ""
                if renderer.is_file():
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "tools" / "render_xml_gallery.py")],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    gallery_built = result.returncode == 0
                    gallery_message = (
                        result.stdout[-1000:]
                        if gallery_built
                        else (result.stderr or result.stdout)[-1000:]
                    )
                else:
                    gallery_message = "LVGL WASM renderer is not built; gallery was skipped."
                self._json(
                    200,
                    {
                        "profile": profile,
                        "screens": [path.name for path in screen_paths],
                        "galleryBuilt": gallery_built,
                        "message": gallery_message,
                    },
                )
                return
            if path == "/api/upload":
                requested_name = Path(unquote(self.headers.get("X-File-Name", ""))).name
                suffix = Path(requested_name).suffix.lower()
                if not requested_name or suffix not in SUPPORTED_SUFFIXES:
                    raise ValueError("choose a supported image file")
                try:
                    with Image.open(io.BytesIO(body)) as image:
                        image.verify()
                except (OSError, Image.DecompressionBombError) as error:
                    raise ValueError("the selected file is not a readable image") from error
                stem = Path(requested_name).stem
                image_path = self.server.input_dir / requested_name
                suffix = Path(requested_name).suffix
                duplicate = 2
                while image_path.exists():
                    image_path = self.server.input_dir / f"{stem}-{duplicate}{suffix}"
                    duplicate += 1
                image_path.write_bytes(body)
                self._json(201, {"name": image_path.name})
                return
            if path == "/api/build":
                settings = load_settings(self.server.input_dir)
                if __package__:
                    from tools.artwork_gallery import build_gallery
                else:
                    from artwork_gallery import build_gallery
                count = build_gallery(self.server.input_dir, PROFILES[settings["profile"]])
                self._json(200, {"images": count})
                return
            self._json(404, {"error": "not found"})
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})


def _start_xml_preview_server() -> LivePreviewServer:
    choices = available_screen_choices()
    choice_id = "nice-view-pair" if "nice-view-pair" in choices else next(iter(choices))
    preview_server = LivePreviewServer(
        ("127.0.0.1", 0), LivePreviewHandler
    )
    preview_server.fields = load_catalog()
    preview_server.screen_paths = choices[choice_id][1]
    preview_server.left_role = "central"
    preview_server.right_role = "peripheral"
    preview_server.legacy_inverted = False
    preview_server.observer = Observer()
    preview_server.watched_dirs = set()
    preview_server.state_lock = threading.RLock()
    preview_server.change_condition = threading.Condition()
    preview_server.revision = 0
    preview_server.reload_error = None
    preview_server.allow_screen_select = True
    preview_server.screen_choice = choice_id
    if not preview_server.reload_sources():
        preview_server.server_close()
        raise ValueError(preview_server.reload_error or "could not load XML preview")
    preview_server.observer.start()
    preview_thread = threading.Thread(
        target=preview_server.serve_forever, daemon=True
    )
    preview_thread.start()
    preview_server.preview_thread = preview_thread
    return preview_server


def run_editor(input_dir: Path, port: int = 0) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    preview_server = _start_xml_preview_server()
    try:
        server = ArtworkEditorServer(("127.0.0.1", port), ArtworkEditorHandler)
        server.input_dir = input_dir.resolve()
        server.preview_server = preview_server
        server.xml_preview_url = (
            f"http://127.0.0.1:{preview_server.server_port}/"
        )
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Screen design editor: {url}", flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping screen design editor.")
        finally:
            server.server_close()
    finally:
        preview_server.shutdown()
        preview_server.observer.stop()
        preview_server.observer.join()
        preview_server.server_close()
