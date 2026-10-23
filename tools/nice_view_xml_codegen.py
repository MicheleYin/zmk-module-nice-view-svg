"""Generate LVGL screen C/H sources from validated component XML."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from tools.nice_view_xml_assets import load_i1_png
else:
    from nice_view_xml_assets import load_i1_png

MAX_DYNAMIC_BINDINGS = 22
ROLES = {"central": 1, "peripheral": 2}
RENDERERS = {
    "text": "ZMK_NVP_SVG_RENDER_TEXT",
    "percent": "ZMK_NVP_SVG_RENDER_PERCENT",
    "bar": "ZMK_NVP_SVG_RENDER_BAR",
    "ring": "ZMK_NVP_SVG_RENDER_RING",
    "visible": "ZMK_NVP_SVG_RENDER_VISIBLE",
}


@dataclass
class StaticLabel:
    text: str
    x: int
    y: int
    font_size: int = 10


@dataclass
class BackgroundImage:
    path: Path
    x: int
    y: int
    width: int
    height: int
    bitmap: bytes


@dataclass
class BindingSpec:
    field_id: str
    renderer: str
    roles: int
    x: int
    y: int
    width: int
    height: int
    ring_radius: int
    ring_width: int
    ring_rounded: int
    font_size: int
    format_name: str
    prefix: str
    when: str
    match_bit: int
    visible_child_text: str
    anchor: str = "start"


def _int_attr(element: ET.Element, name: str, default: int = 0) -> int:
    value = element.get(name)
    if value is None or not re.fullmatch(r"-?\d+", value):
        return default
    return int(value)


def _binding_roles(element: ET.Element) -> int:
    role = element.get("role")
    if role is None:
        return ROLES["central"] | ROLES["peripheral"]
    if role == "central":
        return ROLES["central"]
    if role == "peripheral":
        return ROLES["peripheral"]
    return ROLES["central"] | ROLES["peripheral"]


def _when_string(element: ET.Element) -> str:
    test = element.get("test")
    if test == "equals":
        return element.get("value", "")
    if test == "bit_set":
        return "set"
    if test == "bit_clear":
        return "clear"
    return ""


def _resolve_image_path(src: str, screen_path: Path | None) -> Path:
    path = Path(src)
    if path.is_absolute() and path.exists():
        return path
    candidates: list[Path] = []
    if screen_path is not None:
        candidates.append((screen_path.parent / path).resolve())
    candidates.append((Path.cwd() / path).resolve())
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise ValueError(f"lv_image src not found: {src}")


def collect_bindings(
    root: ET.Element, screen_path: Path | None = None
) -> tuple[int, int, list[StaticLabel], list[BindingSpec], BackgroundImage | None]:
    views = root.findall("view")
    if len(views) != 1:
        raise ValueError("component must contain exactly one direct <view>")
    view = views[0]
    width = _int_attr(view, "width")
    height = _int_attr(view, "height")
    if width <= 0 or height <= 0:
        raise ValueError("<view> needs positive width and height")

    static_labels: list[StaticLabel] = []
    bindings: list[BindingSpec] = []
    background: BackgroundImage | None = None

    for element in root.iter():
        if element.tag == "lv_image":
            src = element.get("src")
            if not src:
                raise ValueError("<lv_image> needs a src attribute")
            image_path = _resolve_image_path(src, screen_path)
            img_w, img_h, bitmap = load_i1_png(image_path)
            if background is not None:
                raise ValueError("only one <lv_image> background is supported")
            background = BackgroundImage(
                path=image_path,
                x=_int_attr(element, "x"),
                y=_int_attr(element, "y"),
                width=img_w,
                height=img_h,
                bitmap=bitmap,
            )
        elif element.tag == "lv_label" and element.get("field") is None:
            # Skip labels nested under zmk_status_when; those become visible bindings.
            parent_is_when = False
            for parent in root.iter():
                if element in list(parent) and parent.tag == "zmk_status_when":
                    parent_is_when = True
                    break
            if parent_is_when:
                continue
            text = element.get("text")
            if text:
                static_labels.append(
                    StaticLabel(
                        text=text,
                        x=_int_attr(element, "x"),
                        y=_int_attr(element, "y"),
                        font_size=_int_attr(element, "font_size", 10),
                    )
                )
        elif element.tag == "zmk_status_text":
            fmt = element.get("format", "text")
            renderer = "percent" if fmt == "percent" else "text"
            format_name = {
                "percent": "percent",
                "output-label": "output-label",
                "profile-number": "profile-number",
                "text": "value",
            }.get(fmt, "value")
            bindings.append(
                BindingSpec(
                    field_id=element.get("field", ""),
                    renderer=renderer,
                    roles=_binding_roles(element),
                    x=_int_attr(element, "x"),
                    y=_int_attr(element, "y"),
                    width=0,
                    height=0,
                    ring_radius=0,
                    ring_width=0,
                    ring_rounded=0,
                    font_size=_int_attr(element, "font_size", 11 if renderer == "percent" else 10),
                    format_name=format_name,
                    prefix="",
                    when="",
                    match_bit=0,
                    visible_child_text="",
                    anchor=element.get("anchor", "start"),
                )
            )
        elif element.tag == "zmk_status_bar":
            bindings.append(
                BindingSpec(
                    field_id=element.get("field", ""),
                    renderer="bar",
                    roles=_binding_roles(element),
                    x=_int_attr(element, "x"),
                    y=_int_attr(element, "y"),
                    width=_int_attr(element, "width", 1),
                    height=_int_attr(element, "height", 4),
                    ring_radius=0,
                    ring_width=0,
                    ring_rounded=0,
                    font_size=0,
                    format_name="value",
                    prefix="",
                    when="",
                    match_bit=0,
                    visible_child_text="",
                )
            )
        elif element.tag == "zmk_status_arc":
            radius = _int_attr(element, "radius", 10)
            bindings.append(
                BindingSpec(
                    field_id=element.get("field", ""),
                    renderer="ring",
                    roles=_binding_roles(element),
                    x=_int_attr(element, "x"),
                    y=_int_attr(element, "y"),
                    width=0,
                    height=0,
                    ring_radius=radius,
                    ring_width=_int_attr(element, "ring_width", 2),
                    ring_rounded=1,
                    font_size=0,
                    format_name="value",
                    prefix="",
                    when="",
                    match_bit=0,
                    visible_child_text="",
                )
            )
        elif element.tag == "zmk_status_when":
            child = next((node for node in element if node.tag == "lv_label"), None)
            child_text = child.get("text", "") if child is not None else ""
            bindings.append(
                BindingSpec(
                    field_id=element.get("field", ""),
                    renderer="visible",
                    roles=_binding_roles(element),
                    x=_int_attr(child or element, "x"),
                    y=_int_attr(child or element, "y"),
                    width=_int_attr(child or element, "width", 24),
                    height=_int_attr(child or element, "height", 12),
                    ring_radius=0,
                    ring_width=0,
                    ring_rounded=0,
                    font_size=_int_attr(child or element, "font_size", 10),
                    format_name="value",
                    prefix=child_text,
                    when=_when_string(element),
                    match_bit=_int_attr(element, "bit"),
                    visible_child_text=child_text,
                )
            )

    if len(bindings) > MAX_DYNAMIC_BINDINGS:
        raise ValueError(
            f"screen has {len(bindings)} dynamic bindings; budget is {MAX_DYNAMIC_BINDINGS}"
        )
    return width, height, static_labels, bindings, background


def _c_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _emit_background_c(lines: list[str], background: BackgroundImage) -> None:
    stride = (background.width + 7) // 8
    lines.extend(
        [
            "static const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST uint8_t",
            "    zmk_nvp_svg_background_data[] = {",
            "#if CONFIG_NICE_VIEW_WIDGET_INVERTED && !CONFIG_ZMK_SVG_WHITE_BACKGROUND",
            "    0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff,",
            "#else",
            "    0xff, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0xff,",
            "#endif",
        ]
    )
    for offset in range(0, len(background.bitmap), 16):
        chunk = background.bitmap[offset : offset + 16]
        lines.append("    " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
    lines.extend(
        [
            "};",
            "",
            "static const lv_image_dsc_t zmk_nvp_svg_background = {",
            "    .header = {",
            "        .magic = LV_IMAGE_HEADER_MAGIC,",
            "        .cf = LV_COLOR_FORMAT_I1,",
            f"        .w = {background.width},",
            f"        .h = {background.height},",
            f"        .stride = {stride},",
            "    },",
            "    .data_size = sizeof(zmk_nvp_svg_background_data),",
            "    .data = zmk_nvp_svg_background_data,",
            "};",
            "",
        ]
    )


def generate_sources(
    xml_text: str, screen_path: Path | None = None
) -> tuple[str, str]:
    root = ET.fromstring(xml_text)
    if root.tag != "component":
        raise ValueError("root element must be <component>")
    width, height, static_labels, bindings, background = collect_bindings(
        root, screen_path
    )
    has_background = 1 if background is not None else 0

    header_lines = [
        "#pragma once",
        "#include <lvgl.h>",
        "#include <stdint.h>",
        "",
        f"#define ZMK_NVP_SVG_WIDTH {width}",
        f"#define ZMK_NVP_SVG_HEIGHT {height}",
        f"#define ZMK_NVP_SVG_BINDING_COUNT {len(bindings)}",
        "#define ZMK_NVP_SVG_VISIBLE_ASSET_COUNT 0",
        f"#define ZMK_NVP_XML_HAS_BACKGROUND {has_background}",
        "",
        "enum zmk_nvp_svg_renderer {",
        "    ZMK_NVP_SVG_RENDER_BAR = 0,",
        "    ZMK_NVP_SVG_RENDER_PERCENT = 1,",
        "    ZMK_NVP_SVG_RENDER_RING = 2,",
        "    ZMK_NVP_SVG_RENDER_TEXT = 3,",
        "    ZMK_NVP_SVG_RENDER_VISIBLE = 4,",
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
        f"extern const struct zmk_nvp_svg_binding zmk_nvp_svg_bindings[{len(bindings) or 1}];",
        "void zmk_nvp_xml_layout_create(lv_obj_t *screen);",
        "",
    ]

    binding_rows = []
    for binding in bindings:
        binding_rows.append(
            "    { "
            + ", ".join(
                [
                    _c_string(binding.field_id),
                    RENDERERS[binding.renderer],
                    str(binding.roles),
                    "255",
                    str(binding.x),
                    str(binding.y),
                    str(binding.width),
                    str(binding.height),
                    str(binding.ring_radius),
                    str(binding.ring_width),
                    str(binding.ring_rounded),
                    str(binding.font_size),
                    "0",
                    _c_string("monospace"),
                    _c_string(binding.anchor),
                    _c_string(binding.format_name),
                    _c_string(binding.prefix),
                    _c_string(""),
                    _c_string(binding.when),
                    str(binding.match_bit),
                ]
            )
            + " },"
        )
    if not binding_rows:
        binding_rows.append("    { 0 },")

    c_lines = [
        '#include "status_screen_gen.h"',
        "#include <stdbool.h>",
        "#include <stdio.h>",
        "#include <string.h>",
        "",
        "#include <lvgl.h>",
        "",
    ]
    if background is not None:
        _emit_background_c(c_lines, background)

    c_lines.extend(
        [
            "const struct zmk_nvp_svg_binding zmk_nvp_svg_bindings[] = {",
            *binding_rows,
            "};",
            "",
            "static lv_color_t xml_foreground(void)",
            "{",
            "#if CONFIG_NICE_VIEW_WIDGET_INVERTED && !CONFIG_ZMK_SVG_WHITE_BACKGROUND",
            "    return lv_color_white();",
            "#else",
            "    return lv_color_black();",
            "#endif",
            "}",
            "",
            "void zmk_nvp_xml_layout_create(lv_obj_t *screen)",
            "{",
            "    if (screen == NULL) {",
            "        return;",
            "    }",
        ]
    )

    if background is not None:
        c_lines.extend(
            [
                "    {",
                "        lv_obj_t *background = lv_image_create(screen);",
                "        lv_image_set_src(background, &zmk_nvp_svg_background);",
                f"        lv_obj_set_pos(background, {background.x}, {background.y});",
                "    }",
            ]
        )

    for label in static_labels:
        c_lines.extend(
            [
                "    {",
                "        lv_obj_t *label = lv_label_create(screen);",
                f"        lv_label_set_text(label, {_c_string(label.text)});",
                f"        lv_obj_set_pos(label, {label.x}, {label.y});",
                "        lv_obj_set_style_text_color(label, xml_foreground(), LV_PART_MAIN);",
                "    }",
            ]
        )

    c_lines.extend(["}", ""])

    return "\n".join(header_lines).rstrip() + "\n", "\n".join(c_lines).rstrip() + "\n"


def write_generated(screen_path: Path, output_dir: Path) -> tuple[Path, Path]:
    xml_text = screen_path.read_text()
    header, source = generate_sources(xml_text, screen_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    header_path = output_dir / "status_screen_gen.h"
    source_path = output_dir / "status_screen_gen.c"
    header_path.write_text(header)
    source_path.write_text(source)
    return header_path, source_path
