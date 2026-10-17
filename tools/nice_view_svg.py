"""Validate Nice!view SVG binding annotations."""

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from importlib import import_module
from io import BytesIO
from pathlib import Path
from typing import Any

SCREEN_WIDTH = 160
SCREEN_HEIGHT = 68
MAX_DYNAMIC_BINDINGS = 22
WIDGET_CATALOG_NAME = "widget_types.json"
PILLOW_UV_ERROR = "run this command with uv and tools/requirements.txt"
PREPROCESSOR_ENDIF = "#endif"
ROLES = {"central", "peripheral"}
RENDERERS = {"text", "percent", "bar", "ring", "visible"}
NUMERIC_TYPES = {"integer", "percent"}


def load_catalog(path: Path) -> dict[str, dict[str, Any]]:
    catalog = json.loads(path.read_text())
    if catalog.get("schema_version") != 1:
        raise ValueError("unsupported status field catalog schema_version")

    fields = {}
    for field in catalog.get("fields", []):
        field_id = field.get("id")
        if not isinstance(field_id, str) or not field_id:
            raise ValueError("every catalog field needs a non-empty id")
        if field_id in fields:
            raise ValueError(f"duplicate catalog field: {field_id}")
        if not set(field.get("available_on", [])) <= ROLES:
            raise ValueError(f"invalid role list for catalog field: {field_id}")
        fields[field_id] = field
    return fields


def load_widget_catalog(path: Path) -> dict[str, dict[str, Any]]:
    catalog = json.loads(path.read_text())
    if catalog.get("schema_version") != 1:
        raise ValueError("unsupported widget catalog schema_version")

    widgets = catalog.get("widgets")
    if not isinstance(widgets, dict):
        raise TypeError("widget catalog needs a widgets object")
    for widget_id, widget in widgets.items():
        _validate_widget_definition(widget_id, widget)
    return widgets


def _validate_widget_definition(widget_id: str, widget: Any) -> None:
    if not isinstance(widget, dict):
        raise TypeError(f"widget {widget_id} needs an object")
    slots = widget.get("slots")
    if not isinstance(slots, dict):
        raise TypeError(f"widget {widget_id} needs a slots object")
    for slot_id, slot in slots.items():
        _validate_widget_slot(widget_id, slot_id, slot)


def _validate_widget_slot(widget_id: str, slot_id: str, slot: Any) -> None:
    if not isinstance(slot, dict):
        raise TypeError(f"widget slot {widget_id}.{slot_id} needs an object")
    if not isinstance(slot.get("fields"), list) or not slot["fields"]:
        raise ValueError(f"widget slot {widget_id}.{slot_id} needs fields")
    if not isinstance(slot.get("renderers"), list) or not slot["renderers"]:
        raise ValueError(f"widget slot {widget_id}.{slot_id} needs renderers")
    if not set(slot["renderers"]) <= RENDERERS:
        raise ValueError(f"widget slot {widget_id}.{slot_id} has an invalid renderer")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _load_pillow_image(error_message: str) -> Any:
    try:
        return import_module("PIL.Image")
    except ImportError as error:
        raise RuntimeError(error_message) from error


def _binding_roles(element: ET.Element) -> set[str]:
    role_text = element.get("data-nvp-role", "both")
    if role_text == "both":
        return set(ROLES)
    roles = {role.strip() for role in role_text.split(",")}
    if not roles or not roles <= ROLES:
        raise ValueError(f"invalid data-nvp-role: {role_text}")
    return roles


def _validate_view_box(root: ET.Element) -> list[str]:
    try:
        view_box = [float(value) for value in root.get("viewBox", "").split()]
    except ValueError:
        view_box = []
    if len(view_box) == 4 and view_box[2:] == [SCREEN_WIDTH, SCREEN_HEIGHT]:
        return []
    return ["viewBox must have width 160 and height 68"]


def _validate_renderer_type(
    field_id: str, renderer: str, tag: str, field_type: str | None
) -> list[str]:
    if renderer in {"text", "percent"} and tag != "text":
        return [f"renderer '{renderer}' requires a <text> element: {field_id}"]
    if renderer == "bar" and (tag != "rect" or field_type != "percent"):
        return [f"renderer 'bar' requires a percent-bound <rect>: {field_id}"]
    if renderer == "ring" and (tag != "circle" or field_type != "percent"):
        return [f"renderer 'ring' requires a percent-bound <circle>: {field_id}"]
    if renderer == "visible" and field_type not in {
        "boolean",
        "enum",
        "integer",
        "bitmask",
    }:
        return [
            f"renderer 'visible' requires a boolean, enum, or integer field: {field_id}"
        ]
    if renderer == "percent" and field_type != "percent":
        return [f"renderer 'percent' requires a percent field: {field_id}"]
    if renderer == "text" and field_type not in NUMERIC_TYPES | {
        "string",
        "enum",
        "bitmask",
        "boolean",
    }:
        return [f"renderer 'text' does not support field type {field_type}: {field_id}"]
    return []


def _validate_bar_geometry(element: ET.Element, field_id: str) -> list[str]:
    for attribute in ("x", "y", "width", "height"):
        value = element.get(attribute, "")
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
            return [f"bar {field_id} needs numeric {attribute}"]
    return []


def _ring_transform_is_supported(
    element: ET.Element, center_x: float, center_y: float
) -> bool:
    transform = element.get("transform")
    if transform is None:
        return True
    match = re.fullmatch(
        r"rotate\(\s*(-?\d+(?:\.\d+)?)\s*(?:,\s*|\s+)"
        r"(-?\d+(?:\.\d+)?)\s*(?:,\s*|\s+)"
        r"(-?\d+(?:\.\d+)?)\s*\)",
        transform,
    )
    if match is None:
        return False
    angle, transform_x, transform_y = (float(value) for value in match.groups())
    return (
        (math.isclose(angle, -90) or math.isclose(angle, 270))
        and math.isclose(transform_x, center_x)
        and math.isclose(transform_y, center_y)
    )


def _has_transformed_ancestor(
    element: ET.Element, parents: dict[ET.Element, ET.Element]
) -> bool:
    parent = parents.get(element)
    while parent is not None:
        if parent.get("transform") is not None:
            return True
        parent = parents.get(parent)
    return False


def _validate_ring_geometry(
    element: ET.Element,
    field_id: str,
    parents: dict[ET.Element, ET.Element],
) -> list[str]:
    values = {}
    for attribute in ("cx", "cy", "r", "stroke-width"):
        try:
            value = float(element.get(attribute, ""))
        except ValueError:
            return [f"ring {field_id} needs numeric {attribute}"]
        if not math.isfinite(value):
            return [f"ring {field_id} needs finite {attribute}"]
        values[attribute] = value
    radius = values["r"]
    stroke_width = values["stroke-width"]
    if radius <= 0 or stroke_width <= 0:
        return [f"ring {field_id} needs positive radius and stroke-width"]
    if element.get("stroke", "none").lower() == "none":
        return [f"ring {field_id} needs a visible stroke"]
    if element.get("fill", "none").lower() not in {"none", "transparent"}:
        return [f"ring {field_id} must use fill=none"]
    if not _ring_transform_is_supported(element, values["cx"], values["cy"]):
        return [f"ring {field_id} only supports rotation about its center"]
    if _has_transformed_ancestor(element, parents):
        return [f"ring {field_id} cannot have a transformed ancestor"]
    extent = radius + stroke_width / 2
    if not (
        extent <= values["cx"] <= SCREEN_WIDTH - extent
        and extent <= values["cy"] <= SCREEN_HEIGHT - extent
    ):
        return [f"ring {field_id} is outside the screen bounds"]
    return []


def _validate_visibility(
    element: ET.Element, field: dict[str, Any], field_id: str
) -> list[str]:
    expected = element.get("data-nvp-when")
    field_type = field.get("type")
    if expected is None:
        return [f"visible renderer needs data-nvp-when: {field_id}"]
    if field_type == "bitmask":
        if expected not in {"set", "clear"}:
            return [f"bitmask visibility needs data-nvp-when=set|clear: {field_id}"]
        try:
            bit = int(element.get("data-nvp-bit", ""))
        except ValueError:
            return [f"bitmask visibility needs a numeric data-nvp-bit: {field_id}"]
        if bit < 0 or bit >= field.get("maximum", 255).bit_length():
            return [f"data-nvp-bit is out of range for {field_id}"]
    elif element.get("data-nvp-bit") is not None:
        return [f"data-nvp-bit requires a bitmask field: {field_id}"]
    if field_type == "boolean" and expected not in {"true", "false"}:
        return [f"boolean visibility needs data-nvp-when=true|false: {field_id}"]
    if field_type == "enum" and expected not in field.get("values", []):
        return [f"invalid enum value '{expected}' for {field_id}"]
    if field_type == "integer":
        try:
            expected_value = int(expected)
        except ValueError:
            return [f"integer visibility needs a numeric data-nvp-when: {field_id}"]
        minimum = field.get("minimum", expected_value)
        maximum = field.get("maximum", expected_value)
        if not minimum <= expected_value <= maximum:
            return [f"integer data-nvp-when is out of range for {field_id}"]
    return []


def _visible_bounds(element: ET.Element) -> tuple[int, int, int, int] | None:
    bounds_text = element.get("data-nvp-bounds", "")
    if not bounds_text and _local_name(element.tag) == "rect":
        bounds_text = " ".join(
            element.get(name, "") for name in ("x", "y", "width", "height")
        )
    elif not bounds_text and _local_name(element.tag) == "circle":
        try:
            center_x = float(element.get("cx", ""))
            center_y = float(element.get("cy", ""))
            radius = float(element.get("r", ""))
            bounds_text = (
                f"{center_x - radius} {center_y - radius} {radius * 2} {radius * 2}"
            )
        except ValueError:
            return None
    values = bounds_text.replace(",", " ").split()
    if len(values) != 4:
        return None
    try:
        x, y, width, height = (float(value) for value in values)
    except ValueError:
        return None
    if width <= 0 or height <= 0 or x < 0 or y < 0:
        return None
    if x + width > SCREEN_WIDTH or y + height > SCREEN_HEIGHT:
        return None
    left, top = math.floor(x), math.floor(y)
    right, bottom = math.ceil(x + width), math.ceil(y + height)
    return left, top, right - left, bottom - top


def _validate_binding(
    element: ET.Element,
    fields: dict[str, dict[str, Any]],
    roles: set[str],
    parents: dict[ET.Element, ET.Element],
) -> list[str]:
    field_id = element.get("data-nvp-bind")
    renderer = element.get("data-nvp-render")
    if not field_id or not renderer:
        return ["each dynamic element needs data-nvp-bind and data-nvp-render"]

    errors = []
    if any(
        child is not element and child.get("data-nvp-bind") is not None
        for child in element.iter()
    ):
        errors.append(f"nested dynamic bindings are unsupported: {field_id}")
    if renderer not in RENDERERS:
        errors.append(f"unsupported renderer '{renderer}' for {field_id}")
        return errors

    field = fields.get(field_id)
    if field is None:
        errors.append(f"unknown status field: {field_id}")
        return errors
    try:
        element_roles = _binding_roles(element)
    except ValueError as error:
        errors.append(str(error))
        return errors
    for role in element_roles & roles:
        if role not in field.get("available_on", []):
            errors.append(f"field {field_id} is unavailable on the {role} display")

    field_type = field.get("type")
    errors.extend(
        _validate_renderer_type(
            field_id, renderer, _local_name(element.tag), field_type
        )
    )
    if renderer == "bar":
        errors.extend(_validate_bar_geometry(element, field_id))
    if renderer == "ring":
        errors.extend(_validate_ring_geometry(element, field_id, parents))
    if renderer == "visible":
        errors.extend(_validate_visibility(element, field, field_id))
        if _visible_bounds(element) is None:
            errors.append(
                f"visible renderer needs in-bounds data-nvp-bounds: {field_id}"
            )
    return errors


def _validate_widget_groups(
    root: ET.Element,
    widget_catalog: dict[str, dict[str, Any]],
) -> list[str]:
    parents = {child: parent for parent in root.iter() for child in parent}
    widget_elements = [
        element for element in root.iter() if element.get("data-nvp-widget")
    ]
    widget_ids: set[str] = set()
    errors = []
    for widget_element in widget_elements:
        errors.extend(
            _validate_widget_group(widget_element, widget_catalog, parents, widget_ids)
        )
    errors.extend(_validate_widget_slot_owners(root, parents))
    return errors


def _validate_widget_group(
    element: ET.Element,
    widget_catalog: dict[str, dict[str, Any]],
    parents: dict[ET.Element, ET.Element],
    widget_ids: set[str],
) -> list[str]:
    widget_type = element.get("data-nvp-widget", "")
    widget_id = element.get("id", "")
    errors = _validate_widget_identity(element, widget_type, widget_id, widget_ids)
    widget = widget_catalog.get(widget_type)
    if widget is None:
        return errors + [f"unknown widget type: {widget_type}"]
    if _has_widget_ancestor(element, parents):
        errors.append(f"nested widgets are unsupported: {widget_id}")
    used_slots, part_errors = _validate_widget_parts(
        element, widget, widget_type, widget_id
    )
    errors.extend(part_errors)
    errors.extend(_validate_required_slots(widget, used_slots, widget_id))
    return errors


def _validate_widget_identity(
    element: ET.Element,
    widget_type: str,
    widget_id: str,
    widget_ids: set[str],
) -> list[str]:
    errors = []
    if _local_name(element.tag) != "g":
        errors.append(f"widget {widget_id or widget_type} must be an SVG <g>")
    if not widget_id:
        errors.append(f"widget {widget_type} needs an id")
    elif widget_id in widget_ids:
        errors.append(f"duplicate widget id: {widget_id}")
    widget_ids.add(widget_id)
    return errors


def _validate_widget_parts(
    element: ET.Element,
    widget: dict[str, Any],
    widget_type: str,
    widget_id: str,
) -> tuple[set[str], list[str]]:
    used_slots = set()
    errors = []
    for part in element.iter():
        field_id = part.get("data-nvp-bind")
        slot_id = part.get("data-nvp-slot")
        if field_id is None and slot_id is None:
            continue
        if field_id is None or slot_id is None:
            errors.append(
                f"widget {widget_id} parts need both data-nvp-slot and data-nvp-bind"
            )
            continue
        slot = widget["slots"].get(slot_id)
        if slot is None:
            errors.append(f"unknown widget slot {slot_id} in {widget_id}")
            continue
        used_slots.add(slot_id)
        renderer = part.get("data-nvp-render")
        if field_id not in slot["fields"]:
            errors.append(f"field {field_id} is not allowed in {widget_type}.{slot_id}")
        if renderer not in slot["renderers"]:
            errors.append(
                f"renderer {renderer} is not allowed in {widget_type}.{slot_id}"
            )
    return used_slots, errors


def _validate_required_slots(
    widget: dict[str, Any], used_slots: set[str], widget_id: str
) -> list[str]:
    return [
        f"widget {widget_id} is missing required slot: {slot_id}"
        for slot_id, slot in widget["slots"].items()
        if slot.get("required", False) and slot_id not in used_slots
    ]


def _validate_widget_slot_owners(
    root: ET.Element,
    parents: dict[ET.Element, ET.Element],
) -> list[str]:
    errors = []
    for element in root.iter():
        if element.get("data-nvp-slot") is None:
            continue
        if not _has_widget_owner(element, parents):
            errors.append(
                f"data-nvp-slot is outside a widget: {element.get('data-nvp-slot')}"
            )
    return errors


def _has_widget_ancestor(
    element: ET.Element, parents: dict[ET.Element, ET.Element]
) -> bool:
    parent = parents.get(element)
    while parent is not None:
        if parent.get("data-nvp-widget") is not None:
            return True
        parent = parents.get(parent)
    return False


def _has_widget_owner(
    element: ET.Element, parents: dict[ET.Element, ET.Element]
) -> bool:
    return element.get("data-nvp-widget") is not None or _has_widget_ancestor(
        element, parents
    )


def validate_svg_text(
    svg_text: str,
    fields: dict[str, dict[str, Any]],
    roles: set[str] | None = None,
    widget_catalog: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as error:
        return [f"invalid SVG XML: {error}"]
    if _local_name(root.tag) != "svg":
        return ["root element must be <svg>"]

    errors = _validate_view_box(root)
    if widget_catalog is not None:
        errors.extend(_validate_widget_groups(root, widget_catalog))
    selected_roles = roles or set(ROLES)
    parents = {child: parent for parent in root.iter() for child in parent}
    binding_count = sum(
        element.get("data-nvp-bind") is not None for element in root.iter()
    )
    if binding_count > MAX_DYNAMIC_BINDINGS:
        errors.append(
            f"SVG has {binding_count} dynamic bindings; budget is {MAX_DYNAMIC_BINDINGS}"
        )
    for element in root.iter():
        if (
            element.get("data-nvp-bind") is not None
            or element.get("data-nvp-render") is not None
        ):
            errors.extend(_validate_binding(element, fields, selected_roles, parents))
    return errors


def validate_svg(
    path: Path,
    catalog_path: Path,
    roles: set[str] | None = None,
    widget_catalog_path: Path | None = None,
) -> list[str]:
    widget_catalog_path = widget_catalog_path or Path(__file__).with_name(
        WIDGET_CATALOG_NAME
    )
    return validate_svg_text(
        path.read_text(),
        load_catalog(catalog_path),
        roles,
        load_widget_catalog(widget_catalog_path),
    )


def _pack_monochrome_pixels(
    pixels: list[int],
    width: int,
    height: int,
    expected_size: tuple[int, int] = (SCREEN_WIDTH, SCREEN_HEIGHT),
) -> bytes:
    if (width, height) != expected_size:
        raise ValueError(f"raster has unexpected dimensions: {width}x{height}")
    if len(pixels) != width * height:
        raise ValueError("raster pixel data is malformed")

    packed = bytearray()
    for offset in range(0, len(pixels), 8):
        value = 0
        for bit, pixel in enumerate(pixels[offset : offset + 8]):
            if pixel == 0:
                value |= 1 << (7 - bit)
        packed.append(value)
    return bytes(packed)


def _pack_i2_pixels(pixels: list[int], width: int, height: int) -> bytes:
    stride = (width + 3) // 4
    packed = bytearray(stride * height)
    for y in range(height):
        for x in range(width):
            pixel = pixels[y * width + x]
            packed[y * stride + x // 4] |= pixel << (6 - 2 * (x % 4))
    return bytes(packed)


def _pack_monochrome_png(data: bytes) -> bytes:
    image_module = _load_pillow_image(PILLOW_UV_ERROR)
    with image_module.open(BytesIO(data)) as source:
        rgba = source.convert("RGBA")
        background = image_module.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        grayscale = background.convert("L")
        pixels = [0 if value < 128 else 1 for value in grayscale.get_flattened_data()]
        return _pack_monochrome_pixels(pixels, *grayscale.size)


def _pack_i2_png(data: bytes, bounds: tuple[int, int, int, int]) -> bytes:
    image_module = _load_pillow_image(PILLOW_UV_ERROR)
    x, y, width, height = bounds
    with image_module.open(BytesIO(data)) as source:
        crop = source.convert("RGBA").crop((x, y, x + width, y + height))
        pixels = []
        for red, green, blue, alpha in crop.get_flattened_data():
            if alpha < 128:
                pixels.append(0)
            elif red + green + blue < 3 * 128:
                pixels.append(1)
            else:
                pixels.append(2)
        return _pack_i2_pixels(pixels, width, height)


def _rasterize(svg_text: str) -> bytes:
    rasterizer = shutil.which("rsvg-convert")
    if not rasterizer:
        raise RuntimeError("preview/generation requires rsvg-convert")
    return _pack_monochrome_png(_rasterize_png(svg_text, rasterizer))


def _isolated_visible_svg(svg_text: str, target_index: int) -> str:
    root = ET.fromstring(svg_text)
    elements = list(root.iter())
    target = elements[target_index]
    parents = {child: parent for parent in root.iter() for child in parent}
    keep = {*target.iter(), *parents_for(target, parents)}

    def prune(parent: ET.Element) -> None:
        for child in tuple(parent):
            if child in keep:
                prune(child)
            elif _local_name(child.tag) not in {"defs", "style"}:
                parent.remove(child)

    prune(root)
    return ET.tostring(root, encoding="unicode")


def parents_for(
    element: ET.Element, parents: dict[ET.Element, ET.Element]
) -> list[ET.Element]:
    chain = []
    parent = parents.get(element)
    while parent is not None:
        chain.append(parent)
        parent = parents.get(parent)
    return chain


def _compile_visible_assets(svg_text: str) -> dict[int, tuple[int, int, bytes]]:
    root = ET.fromstring(svg_text)
    assets = {}
    for element_index, element in enumerate(root.iter()):
        if element.get("data-nvp-render") != "visible":
            continue
        bounds = _visible_bounds(element)
        if bounds is None:
            raise ValueError(
                f"visible renderer needs in-bounds data-nvp-bounds: "
                f"{element.get('data-nvp-bind')}"
            )
        visible_svg = _isolated_visible_svg(svg_text, element_index)
        png = _rasterize_png(visible_svg)
        _, _, width, height = bounds
        assets[element_index] = (width, height, _pack_i2_png(png, bounds))
    return assets


def _format_preview_value(
    value: Any, element: ET.Element, default_format: str = "value"
) -> str:
    prefix = element.get("data-nvp-prefix", "")
    suffix = element.get("data-nvp-suffix", "")
    if value is None:
        return f"{prefix}--{suffix}"
    output_format = element.get("data-nvp-format", default_format)
    if output_format == "percent":
        value = f"{value}%"
    elif output_format == "profile-number":
        value = str(int(value) + 1) if int(value) >= 0 else "-"
    elif output_format == "output-label":
        value = {"usb": "USB", "ble": "BLE", "none": "--"}.get(str(value), "--")
    return f"{prefix}{value}{suffix}"


def _preview_bar(element: ET.Element, value: Any) -> None:
    try:
        if not isinstance(value, (int, float, str)):
            raise TypeError
        percentage = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        percentage = 0.0
    element.set("width", str(float(element.get("width", "0")) * percentage / 100))


def _preview_visible(element: ET.Element, value: Any) -> None:
    bit_text = element.get("data-nvp-bit")
    if bit_text is not None:
        if value is None:
            element.set("display", "none")
            return
        try:
            bit_set = bool(int(value) & (1 << int(bit_text)))
        except (TypeError, ValueError):
            bit_set = False
        is_visible = bit_set == (element.get("data-nvp-when") == "set")
        if not is_visible:
            element.set("display", "none")
        return
    if str(value).lower() != element.get("data-nvp-when"):
        element.set("display", "none")


def _preview_ring(element: ET.Element, value: Any) -> None:
    if value is None:
        element.set("display", "none")
        return
    try:
        percentage = float(value)
    except (TypeError, ValueError):
        element.set("display", "none")
        return
    if not math.isfinite(percentage):
        element.set("display", "none")
        return
    percentage = min(max(percentage, 0), 100)
    if percentage == 0:
        element.set("display", "none")
        return
    element.attrib.pop("display", None)
    radius = float(element.get("r", "0"))
    circumference = 2 * math.pi * radius
    if percentage >= 100:
        element.attrib.pop("stroke-dasharray", None)
        element.attrib.pop("stroke-dashoffset", None)
    else:
        visible_length = circumference * percentage / 100
        element.set(
            "stroke-dasharray",
            f"{visible_length:.3f} {circumference - visible_length:.3f}",
        )
        element.set("stroke-dashoffset", "0")
    center_x = element.get("cx", "0")
    center_y = element.get("cy", "0")
    element.set("transform", f"rotate(-90 {center_x} {center_y})")


def _preview_binding(element: ET.Element, values: dict[str, Any], role: str) -> None:
    field_id = element.get("data-nvp-bind")
    renderer = element.get("data-nvp-render")
    if not field_id or not renderer:
        return
    if role not in _binding_roles(element):
        element.set("display", "none")
        return

    value = values.get(field_id)
    if renderer in {"text", "percent"}:
        default_format = "percent" if renderer == "percent" else "value"
        element.text = _format_preview_value(value, element, default_format)
    elif renderer == "bar":
        _preview_bar(element, value)
    elif renderer == "ring":
        _preview_ring(element, value)
    elif renderer == "visible":
        _preview_visible(element, value)


def preview_svg_text(
    svg_text: str,
    fields: dict[str, dict[str, Any]],
    values: dict[str, Any],
    role: str,
    widget_catalog: dict[str, dict[str, Any]] | None = None,
) -> str:
    errors = validate_svg_text(svg_text, fields, {role}, widget_catalog)
    if errors:
        raise ValueError("\n".join(errors))
    root = ET.fromstring(svg_text)
    for element in root.iter():
        _preview_binding(element, values, role)
    return ET.tostring(root, encoding="unicode")


def _static_svg_text(svg_text: str) -> str:
    root = ET.fromstring(svg_text)
    for parent in root.iter():
        for child in tuple(parent):
            if child.get("data-nvp-bind") is not None:
                parent.remove(child)
    return ET.tostring(root, encoding="unicode")


def _c_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _append_visible_asset_index(lines: list[str], asset_count: int) -> None:
    lines.append("static const lv_image_dsc_t *const zmk_nvp_svg_visible_assets[] = {")
    if asset_count:
        lines.extend(
            f"    &zmk_nvp_svg_visible_{index}," for index in range(asset_count)
        )
    else:
        lines.append("    0,")
    lines.extend(
        ["};", "", "static const struct zmk_nvp_svg_binding zmk_nvp_svg_bindings[] = {"]
    )


def _binding_geometry(
    element: ET.Element, renderer: str
) -> tuple[tuple[int, int, int, int] | None, int, int, int]:
    ring_radius = 0
    ring_width = 0
    ring_rounded = 0
    if renderer == "visible":
        geometry = _visible_bounds(element)
    elif renderer == "ring":
        geometry = (
            round(float(element.get("cx", "0"))),
            round(float(element.get("cy", "0"))),
            0,
            0,
        )
        ring_radius = round(float(element.get("r", "0")))
        ring_width = round(float(element.get("stroke-width", "0")))
        ring_rounded = int(element.get("stroke-linecap", "butt") == "round")
    else:
        geometry = (
            round(float(element.get("x", "0"))),
            round(float(element.get("y", "0"))),
            round(float(element.get("width", "0"))),
            round(float(element.get("height", "0"))),
        )
    return geometry, ring_radius, ring_width, ring_rounded


def _generate_header(
    svg_text: str,
    bitmap: bytes,
    visible_assets: dict[int, tuple[int, int, bytes]] | None = None,
) -> str:
    root = ET.fromstring(svg_text)
    renderers = {name: index for index, name in enumerate(sorted(RENDERERS))}
    role_bits = {"central": 1, "peripheral": 2}
    indexed_elements = [
        (index, element)
        for index, element in enumerate(root.iter())
        if element.get("data-nvp-bind") is not None
    ]
    visible_assets = visible_assets or {}
    asset_indices = {
        element_index: index for index, element_index in enumerate(visible_assets)
    }
    lines = [
        "#pragma once",
        "#include <lvgl.h>",
        "#include <stdint.h>",
        "",
        "#ifndef LV_ATTRIBUTE_MEM_ALIGN",
        "#define LV_ATTRIBUTE_MEM_ALIGN",
        PREPROCESSOR_ENDIF,
        "#ifndef LV_ATTRIBUTE_LARGE_CONST",
        "#define LV_ATTRIBUTE_LARGE_CONST",
        PREPROCESSOR_ENDIF,
        "",
        f"#define ZMK_NVP_SVG_WIDTH {SCREEN_WIDTH}",
        f"#define ZMK_NVP_SVG_HEIGHT {SCREEN_HEIGHT}",
        f"#define ZMK_NVP_SVG_BITMAP_SIZE {len(bitmap)}",
        f"#define ZMK_NVP_SVG_BINDING_COUNT {len(indexed_elements)}",
        f"#define ZMK_NVP_SVG_VISIBLE_ASSET_COUNT {len(visible_assets)}",
        "",
        "enum zmk_nvp_svg_renderer {",
    ]
    for name, value in renderers.items():
        lines.append(f"    ZMK_NVP_SVG_RENDER_{name.upper()} = {value},")
    lines.extend(
        [
            "};",
            "",
            "struct zmk_nvp_svg_binding {",
            "    const char *field_id;",
            "    uint8_t renderer;",
            "    uint8_t roles;",
            "    uint8_t asset_index;",
            "    int16_t x, y, width, height;",
            "    int16_t ring_radius;",
            "    uint8_t ring_width;",
            "    uint8_t ring_rounded;",
            "    uint8_t font_size;",
            "    uint8_t color;",
            "    const char *font_family;",
            "    const char *anchor;",
            "    const char *format;",
            "    const char *prefix;",
            "    const char *suffix;",
            "    const char *when;",
            "    uint8_t match_bit;",
            "};",
            "",
            "static const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST uint8_t",
            "    zmk_nvp_svg_background_data[] = {",
            "#if CONFIG_NICE_VIEW_WIDGET_INVERTED",
            "    0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff,",
            "#else",
            "    0xff, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0xff,",
            PREPROCESSOR_ENDIF,
        ]
    )
    for offset in range(0, len(bitmap), 16):
        lines.append(
            "    "
            + ", ".join(f"0x{byte:02x}" for byte in bitmap[offset : offset + 16])
            + ","
        )
    lines.extend(
        [
            "};",
            "",
            "static const lv_image_dsc_t zmk_nvp_svg_background = {",
            "    .header = {",
            "        .magic = LV_IMAGE_HEADER_MAGIC,",
            "        .cf = LV_COLOR_FORMAT_I1,",
            f"        .w = {SCREEN_WIDTH},",
            f"        .h = {SCREEN_HEIGHT},",
            f"        .stride = {SCREEN_WIDTH // 8},",
            "    },",
            "    .data_size = sizeof(zmk_nvp_svg_background_data),",
            "    .data = zmk_nvp_svg_background_data,",
            "};",
            "",
        ]
    )

    for asset_index, (element_index, asset) in enumerate(visible_assets.items()):
        width, height, data = asset
        lines.extend(
            [
                f"static const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST uint8_t zmk_nvp_svg_visible_{asset_index}_data[] = {{",
                "#if CONFIG_NICE_VIEW_WIDGET_INVERTED",
                "    0x00, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,",
                "    0x00, 0x00, 0x00, 0xff, 0x00, 0x00, 0x00, 0x00,",
                "#else",
                "    0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00, 0xff,",
                "    0xff, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00,",
                PREPROCESSOR_ENDIF,
            ]
        )
        for offset in range(0, len(data), 16):
            lines.append(
                "    "
                + ", ".join(f"0x{byte:02x}" for byte in data[offset : offset + 16])
                + ","
            )
        lines.extend(
            [
                "};",
                f"static const lv_image_dsc_t zmk_nvp_svg_visible_{asset_index} = {{",
                "    .header = {",
                "        .magic = LV_IMAGE_HEADER_MAGIC,",
                "        .cf = LV_COLOR_FORMAT_I2,",
                f"        .w = {width},",
                f"        .h = {height},",
                f"        .stride = {(width + 3) // 4},",
                "    },",
                f"    .data_size = sizeof(zmk_nvp_svg_visible_{asset_index}_data),",
                f"    .data = zmk_nvp_svg_visible_{asset_index}_data,",
                "};",
                "",
            ]
        )
    _append_visible_asset_index(lines, len(visible_assets))

    if not indexed_elements:
        lines.append("    { 0 },")
    for element_index, element in indexed_elements:
        field_id = element.attrib["data-nvp-bind"]
        renderer = element.attrib["data-nvp-render"]
        roles = sum(role_bits[role] for role in _binding_roles(element))
        geometry, ring_radius, ring_width, ring_rounded = _binding_geometry(
            element, renderer
        )
        if geometry is None:
            raise ValueError(f"visible element has invalid bounds: {field_id}")
        font_size = round(float(element.get("font-size", "0")))
        color_attribute = "stroke" if renderer == "ring" else "fill"
        color = (
            1
            if element.get(color_attribute, "#000000").lower()
            in {
                "#fff",
                "#ffffff",
                "white",
            }
            else 0
        )
        values = [
            _c_string(field_id),
            f"ZMK_NVP_SVG_RENDER_{renderer.upper()}",
            str(roles),
            str(asset_indices.get(element_index, 255)),
            *(str(value) for value in geometry),
            str(ring_radius),
            str(ring_width),
            str(ring_rounded),
            str(font_size),
            str(color),
            _c_string(element.get("font-family", "")),
            _c_string(element.get("text-anchor", "start")),
            _c_string(element.get("data-nvp-format", "value")),
            _c_string(element.get("data-nvp-prefix", "")),
            _c_string(element.get("data-nvp-suffix", "")),
            _c_string(element.get("data-nvp-when", "")),
            str(int(element.get("data-nvp-bit", "0"))),
        ]
        lines.append("    { " + ", ".join(values) + " },")
    lines.extend(
        [
            "};",
            "",
            "",
        ]
    )
    return "\n".join(lines)


def generate(svg_path: Path, catalog_path: Path, output_path: Path) -> None:
    svg_text = svg_path.read_text()
    fields = load_catalog(catalog_path)
    widget_catalog = load_widget_catalog(Path(__file__).with_name(WIDGET_CATALOG_NAME))
    errors = validate_svg_text(svg_text, fields, widget_catalog=widget_catalog)
    if errors:
        raise ValueError("\n".join(errors))
    bitmap = _rasterize(_static_svg_text(svg_text))
    visible_assets = _compile_visible_assets(svg_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _generate_header(svg_text, bitmap, visible_assets).rstrip() + "\n"
    )


def preview(
    svg_path: Path,
    catalog_path: Path,
    values_path: Path,
    role: str,
    output_path: Path,
    rotate_180: bool = False,
) -> None:
    svg_text = svg_path.read_text()
    fields = load_catalog(catalog_path)
    widget_catalog = load_widget_catalog(Path(__file__).with_name(WIDGET_CATALOG_NAME))
    values_document = json.loads(values_path.read_text())
    values = values_document.get("values", values_document)
    rendered_svg = preview_svg_text(svg_text, fields, values, role, widget_catalog)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    png = _rasterize_png(rendered_svg)
    output_path.write_bytes(_rotate_png_180(png) if rotate_180 else png)


def _rotate_png_180(data: bytes) -> bytes:
    image_module = _load_pillow_image(PILLOW_UV_ERROR)
    with image_module.open(BytesIO(data)) as source:
        output = BytesIO()
        source.transpose(image_module.Transpose.ROTATE_180).save(output, format="PNG")
        return output.getvalue()


def _rasterize_png(svg_text: str, rasterizer: str | None = None) -> bytes:
    rasterizer = rasterizer or shutil.which("rsvg-convert")
    if not rasterizer:
        raise RuntimeError("preview/generation requires rsvg-convert")
    with tempfile.TemporaryDirectory() as temporary_directory:
        svg_path = Path(temporary_directory) / "screen.svg"
        svg_path.write_text(svg_text)
        return subprocess.run(
            [
                rasterizer,
                "-w",
                str(SCREEN_WIDTH),
                "-h",
                str(SCREEN_HEIGHT),
                str(svg_path),
            ],
            check=True,
            capture_output=True,
        ).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    catalog_default = Path(__file__).with_name("status_fields.json")
    validate_parser = subparsers.add_parser("validate", help="validate SVG bindings")
    validate_parser.add_argument("svg", type=Path)
    validate_parser.add_argument("--catalog", type=Path, default=catalog_default)
    validate_parser.add_argument(
        "--role", choices=["central", "peripheral", "both"], default="both"
    )

    generate_parser = subparsers.add_parser(
        "generate", help="generate a monochrome bitmap header"
    )
    generate_parser.add_argument("svg", type=Path)
    generate_parser.add_argument("--catalog", type=Path, default=catalog_default)
    generate_parser.add_argument("--output", type=Path, required=True)

    preview_parser = subparsers.add_parser(
        "preview", help="render SVG using sample status values"
    )
    preview_parser.add_argument("svg", type=Path)
    preview_parser.add_argument("--catalog", type=Path, default=catalog_default)
    preview_parser.add_argument("--values", type=Path, required=True)
    preview_parser.add_argument(
        "--role", choices=["central", "peripheral"], required=True
    )
    preview_parser.add_argument("--output", type=Path, required=True)
    preview_parser.add_argument("--rotate-180", action="store_true")

    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "validate":
            roles = ROLES if arguments.role == "both" else {arguments.role}
            errors = validate_svg(arguments.svg, arguments.catalog, roles)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print(f"Valid Nice!view SVG: {arguments.svg}")
        elif arguments.command == "generate":
            generate(arguments.svg, arguments.catalog, arguments.output)
            print(f"Generated {arguments.output}")
        else:
            preview(
                arguments.svg,
                arguments.catalog,
                arguments.values,
                arguments.role,
                arguments.output,
                arguments.rotate_180,
            )
            print(f"Rendered {arguments.output}")
    except (
        OSError,
        TypeError,
        ValueError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
