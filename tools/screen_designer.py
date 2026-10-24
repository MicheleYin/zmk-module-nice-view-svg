"""Compose editable screen modules into the existing LVGL XML pipeline."""

from __future__ import annotations

import json
import math
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

if __package__:
    from tools.nice_view_xml_assets import DITHER_ALGORITHMS
else:
    from nice_view_xml_assets import DITHER_ALGORITHMS

ROOT = Path(__file__).resolve().parents[1]
PROFILE_SIZES = {"nice-view": (160, 68), "oled": (128, 32)}
HALVES = ("left", "right")
INSTANCE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
SCREEN_NAMES = {
    ("nice-view", "left"): "nice-view-left.xml",
    ("nice-view", "right"): "nice-view-right.xml",
    ("oled", "left"): "oled-left.xml",
    ("oled", "right"): "oled-right.xml",
}


def load_visual_modules(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    catalog_path = root / "tools" / "visual_modules.json"
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("modules"), list):
        raise ValueError("invalid visual module catalog")

    modules = {}
    for module in data["modules"]:
        module_id = module.get("id")
        if not isinstance(module_id, str) or module_id in modules:
            raise ValueError("visual module IDs must be unique strings")
        if not (root / module["source"]).is_file():
            raise ValueError(f"visual module source is missing: {module_id}")
        if not isinstance(module.get("defaults"), dict) or not isinstance(
            module.get("bounds"), dict
        ):
            raise ValueError(f"visual module needs defaults and bounds: {module_id}")
        modules[module_id] = module
    return modules


def empty_screen_design() -> dict[str, Any]:
    return {"background": None, "widgets": []}


def _number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _validate_box(
    instance: dict[str, Any], size: tuple[int, int], label: str
) -> dict[str, int]:
    width, height = size
    box = {}
    for key in ("x", "y", "width", "height"):
        value = round(_number(instance.get(key), f"{label} {key}"))
        box[key] = value
    if box["x"] < 0 or box["y"] < 0 or box["width"] < 1 or box["height"] < 1:
        raise ValueError(f"{label} must have positive size and non-negative position")
    if box["x"] + box["width"] > width or box["y"] + box["height"] > height:
        raise ValueError(f"{label} must fit within the {width}x{height} display")
    return box


def validate_screen_design(
    profile: str,
    side: str,
    design: dict[str, Any],
    input_dir: Path,
    modules: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if profile not in PROFILE_SIZES:
        raise ValueError(f"unknown display profile: {profile}")
    if side not in HALVES:
        raise ValueError(f"unknown display half: {side}")
    if not isinstance(design, dict) or not isinstance(design.get("widgets", []), list):
        raise ValueError("screen design needs a widget list")

    modules = modules or load_visual_modules()
    size = PROFILE_SIZES[profile]
    background = design.get("background")
    clean_background = None
    if background is not None:
        if not isinstance(background, dict):
            raise ValueError("background settings must be an object")
        image_name = background.get("image")
        if not isinstance(image_name, str) or Path(image_name).name != image_name:
            raise ValueError("choose an image from the artwork library")
        if not (input_dir / image_name).is_file():
            raise ValueError(f"background image not found: {image_name}")
        fit = background.get("fit", "cover")
        dither = background.get("dither", "none")
        if fit not in {"cover", "contain"}:
            raise ValueError("background fit must be cover or contain")
        if dither not in DITHER_ALGORITHMS:
            raise ValueError(f"unknown dithering mode: {dither}")
        rotation = background.get("rotation", 0)
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("background rotation must be 0, 90, 180, or 270")
        clean_background = {
            "image": image_name,
            "fit": fit,
            "focal_x": min(1, max(0, _number(background.get("focal_x", 0.5), "focal x"))),
            "focal_y": min(1, max(0, _number(background.get("focal_y", 0.5), "focal y"))),
            "rotation": rotation,
            "dither": dither,
        }

    clean_widgets = []
    seen_ids = set()
    for index, widget in enumerate(design.get("widgets", [])):
        if not isinstance(widget, dict):
            raise ValueError(f"widget {index + 1} must be an object")
        widget_id = widget.get("id")
        module_id = widget.get("module")
        if not isinstance(widget_id, str) or not INSTANCE_ID.fullmatch(widget_id):
            raise ValueError(f"widget {index + 1} has an invalid instance ID")
        if widget_id in seen_ids:
            raise ValueError(f"duplicate widget instance ID: {widget_id}")
        seen_ids.add(widget_id)
        module = modules.get(module_id)
        if module is None or module_id == "background-image":
            raise ValueError(f"unknown widget module: {module_id}")
        box = _validate_box(widget, size, f"widget {widget_id}")
        properties = widget.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError(f"widget {widget_id} properties must be an object")
        unknown = set(properties) - set(module.get("controls", []))
        if unknown:
            raise ValueError(
                f"widget {widget_id} has unsupported properties: "
                + ", ".join(sorted(unknown))
            )
        clean_properties = {**module["defaults"], **properties}
        if "side" in module.get("controls", []) and clean_properties["side"] not in {
            "left",
            "right",
        }:
            raise ValueError(f"widget {widget_id} side must be left or right")
        if "side" in module.get("controls", []):
            clean_properties["label"] = clean_properties["side"][0].upper()
        clean_widgets.append(
            {
                "id": widget_id,
                "module": module_id,
                **box,
                "properties": clean_properties,
            }
        )

    return {"background": clean_background, "widgets": clean_widgets}


def _render_background(
    source: Path,
    destination: Path,
    size: tuple[int, int],
    settings: dict[str, Any],
) -> Path:
    if __package__:
        from tools.artwork_editor import fit_image
    else:
        from artwork_editor import fit_image

    destination.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    durations = []
    with Image.open(source) as image:
        frame_count = getattr(image, "n_frames", 1)
        loop = int(image.info.get("loop", 0))
        for frame_index in range(frame_count):
            image.seek(frame_index)
            frame = ImageOps.exif_transpose(image.convert("RGBA"))
            frames.append(fit_image(frame, size, settings))
            durations.append(max(20, min(int(image.info.get("duration") or 100), 60000)))

    if len(frames) > 1:
        destination = destination.with_suffix(".gif")
        frames[0].save(
            destination,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=loop,
            disposal=2,
            optimize=True,
        )
    else:
        frames[0].save(destination, format="PNG", optimize=True)
    return destination


def _geometry_attributes(
    module: dict[str, Any], instance: dict[str, Any]
) -> dict[str, str]:
    bounds = module["bounds"]
    attributes = {
        "editor_id": instance["id"],
        "editor_module": module["id"],
        "editor_x": str(instance["x"]),
        "editor_y": str(instance["y"]),
        "editor_width": str(instance["width"]),
        "editor_height": str(instance["height"]),
    }
    for key in ("x", "y", "width", "height"):
        attributes[f"editor_base_{key}"] = str(bounds[key])
    return attributes


def write_design_screen(
    profile: str,
    side: str,
    design: dict[str, Any],
    destination: Path,
    input_dir: Path,
    asset_output_dir: Path,
    root: Path = ROOT,
) -> Path:
    modules = load_visual_modules(root)
    design = validate_screen_design(profile, side, design, input_dir, modules)
    width, height = PROFILE_SIZES[profile]
    component = ET.Element("component")
    view = ET.SubElement(
        component,
        "view",
        {
            "extends": "lv_obj",
            "width": str(width),
            "height": str(height),
            "style_bg_color": "0xffffff",
            "style_pad_all": "0",
            "scrollable": "false",
        },
    )

    instances = []
    if design["background"] is not None:
        background = design["background"]
        module = modules["background-image"]
        asset_path = _render_background(
            input_dir / background["image"],
            asset_output_dir / f"background-{profile}-{side}.png",
            (width, height),
            {
                "fit": background["fit"],
                "x": background["focal_x"],
                "y": background["focal_y"],
                "rotation": background["rotation"],
            },
        )
        module_path = root / module["source"]
        params = {
            "image_src": Path(os.path.relpath(asset_path, module_path.parent)).as_posix(),
            "width": str(width),
            "height": str(height),
            "dither": background["dither"],
        }
        instance = {
            "id": "background",
            "x": 0,
            "y": 0,
            "width": width,
            "height": height,
        }
        attributes = {
            "editor_image": background["image"],
            "editor_fit": background["fit"],
            "editor_focal_x": str(background["focal_x"]),
            "editor_focal_y": str(background["focal_y"]),
            "editor_rotation": str(background["rotation"]),
        }
        instances.append((module, instance, params, attributes))

    for widget in design["widgets"]:
        module = modules[widget["module"]]
        params = dict(widget["properties"])
        instances.append((module, widget, params, {}))

    for module, instance, params, metadata in instances:
        module_path = root / module["source"]
        source = Path(os.path.relpath(module_path, destination.parent)).as_posix()
        attributes = {"src": source, **_geometry_attributes(module, instance), **metadata}
        attributes.update({name: str(value) for name, value in params.items()})
        ET.SubElement(view, "zmk_include", attributes)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "<!-- Generated by the screen designer; edit with tools/artwork_editor.py. -->\n"
        + ET.tostring(component, encoding="unicode")
        + "\n",
        encoding="utf-8",
    )
    return destination


def load_design_screen(path: Path, root: Path = ROOT) -> dict[str, Any]:
    if not path.is_file():
        return empty_screen_design()
    modules = load_visual_modules(root)
    root = ET.parse(path).getroot()
    design = empty_screen_design()
    for include in root.iter("zmk_include"):
        module_id = include.get("editor_module")
        if module_id not in modules:
            continue
        module = modules[module_id]
        box = {
            key: int(float(include.get(f"editor_{key}", module["bounds"][key])))
            for key in ("x", "y", "width", "height")
        }
        if module_id == "background-image":
            design["background"] = {
                "image": include.get("editor_image", ""),
                "fit": include.get("editor_fit", "cover"),
                "focal_x": float(include.get("editor_focal_x", "0.5")),
                "focal_y": float(include.get("editor_focal_y", "0.5")),
                "rotation": int(include.get("editor_rotation", "0")),
                "dither": include.get("dither", "none"),
            }
            continue
        design["widgets"].append(
            {
                "id": include.get("editor_id", "widget"),
                "module": module_id,
                **box,
                "properties": {
                    key: include.get(key, str(value))
                    for key, value in module["defaults"].items()
                    if key in module.get("controls", [])
                },
            }
        )
    return design


def design_path(profile: str, side: str, root: Path = ROOT) -> Path:
    if profile not in PROFILE_SIZES or side not in HALVES:
        raise ValueError("unknown profile or display half")
    return root / "docs" / "ui" / "screens" / "designer" / f"{profile}-{side}.xml"


def load_profile_design(profile: str, root: Path = ROOT) -> dict[str, Any]:
    if profile not in PROFILE_SIZES:
        raise ValueError(f"unknown display profile: {profile}")
    return {
        side: load_design_screen(design_path(profile, side, root), root)
        for side in HALVES
    }


def write_profile_preview(
    profile: str,
    halves: dict[str, Any],
    input_dir: Path,
    root: Path = ROOT,
) -> tuple[Path, Path]:
    preview_dir = root / "build" / "screen_designer_preview"
    asset_dir = preview_dir / "assets"
    paths = []
    for side in HALVES:
        path = preview_dir / f"{profile}-{side}.xml"
        write_design_screen(
            profile,
            side,
            halves.get(side, empty_screen_design()),
            path,
            input_dir,
            asset_dir,
            root,
        )
        paths.append(path)
    return paths[0], paths[1]


def save_profile_design(
    profile: str,
    halves: dict[str, Any],
    input_dir: Path,
    root: Path = ROOT,
) -> tuple[Path, Path]:
    asset_dir = root / "docs" / "ui" / "assets" / "designer"
    paths = []
    for side in HALVES:
        path = design_path(profile, side, root)
        write_design_screen(
            profile,
            side,
            halves.get(side, empty_screen_design()),
            path,
            input_dir,
            asset_dir,
            root,
        )
        paths.append(path)
    return paths[0], paths[1]


def export_profile_design(
    profile: str,
    halves: dict[str, Any],
    input_dir: Path,
    root: Path = ROOT,
) -> tuple[Path, Path]:
    from tools.nice_view_xml import generate

    save_profile_design(profile, halves, input_dir, root)
    output_paths = []
    for side in HALVES:
        screen_path = root / "docs" / "ui" / "screens" / SCREEN_NAMES[(profile, side)]
        write_design_screen(
            profile,
            side,
            halves.get(side, empty_screen_design()),
            screen_path,
            input_dir,
            root / "docs" / "ui" / "assets" / "designer",
            root,
        )
        theme = f"{profile.replace('-', '_')}_{side}"
        generate(screen_path, root / "src" / "generated_xml" / theme)
        output_paths.append(screen_path)
    return output_paths[0], output_paths[1]