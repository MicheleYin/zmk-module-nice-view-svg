"""Expand reusable widget fragments in LVGL XML screens."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

PARAMETER = re.compile(r"\{\{([A-Za-z_]\w*)\}\}")


def _substitute(root: ET.Element, parameters: dict[str, str], source: Path) -> None:
    used: set[str] = set()

    def replace(value: str | None) -> str | None:
        if value is None:
            return None

        def replacement(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in parameters:
                raise ValueError(f"{source}: missing widget parameter '{name}'")
            used.add(name)
            return parameters[name]

        return PARAMETER.sub(replacement, value)

    for element in root.iter():
        element.attrib.update(
            {name: replace(value) or "" for name, value in element.attrib.items()}
        )
        element.text = replace(element.text)

    unused = set(parameters) - used
    if unused:
        raise ValueError(
            f"{source}: unused widget parameters: {', '.join(sorted(unused))}"
        )


def _read_fragment(widget_path: Path) -> ET.Element:
    try:
        fragment = ET.parse(widget_path).getroot()
    except (OSError, ET.ParseError) as error:
        raise ValueError(f"cannot load XML widget '{widget_path}': {error}") from error
    if fragment.tag != "fragment":
        raise ValueError(f"XML widget '{widget_path}' root must be <fragment>")
    return fragment


def _rebase_images(fragment: ET.Element, widget_path: Path, screen_dir: Path) -> None:
    for image in fragment.iter("lv_image"):
        source = image.get("src")
        if not source or Path(source).is_absolute():
            continue
        asset_path = (widget_path.parent / source).resolve()
        image.set("src", Path(os.path.relpath(asset_path, screen_dir)).as_posix())


def _expand_include(
    include: ET.Element,
    source: Path,
    screen_dir: Path,
    stack: tuple[Path, ...],
) -> list[ET.Element]:
    if len(include):
        raise ValueError("<zmk_include> cannot have child elements")
    include_source = include.get("src")
    if not include_source:
        raise ValueError("<zmk_include> needs a src attribute")
    widget_path = (source.parent / include_source).resolve()
    if widget_path in stack:
        cycle = " -> ".join(str(path) for path in (*stack, widget_path))
        raise ValueError(f"cyclic XML widget include: {cycle}")

    fragment = _read_fragment(widget_path)
    parameters = {
        name: value for name, value in include.attrib.items() if name != "src"
    }
    _substitute(fragment, parameters, widget_path)
    _rebase_images(fragment, widget_path, screen_dir)
    _expand_children(fragment, widget_path, screen_dir, (*stack, widget_path))
    replacements = list(fragment)
    if not replacements:
        raise ValueError(f"XML widget '{widget_path}' has no elements")
    return replacements


def _replace_include(
    parent: ET.Element, include: ET.Element, replacements: list[ET.Element]
) -> None:
    index = tuple(parent).index(include)
    parent.remove(include)
    for offset, replacement in enumerate(replacements):
        parent.insert(index + offset, replacement)
    replacements[-1].tail = (replacements[-1].tail or "") + (include.tail or "")


def _expand_children(
    parent: ET.Element,
    source: Path,
    screen_directory: Path,
    stack: tuple[Path, ...],
) -> None:
    for child in tuple(parent):
        if child.tag == "zmk_include":
            replacements = _expand_include(child, source, screen_directory, stack)
            _replace_include(parent, child, replacements)
        else:
            _expand_children(child, source, screen_directory, stack)


def expand_screen_file(screen_path: Path) -> str:
    """Return a screen with all reusable widget fragments expanded inline."""
    screen_path = screen_path.resolve()
    try:
        root = ET.parse(screen_path).getroot()
    except (OSError, ET.ParseError) as error:
        raise ValueError(f"cannot load XML screen '{screen_path}': {error}") from error
    _expand_children(root, screen_path, screen_path.parent, (screen_path,))
    return ET.tostring(root, encoding="unicode")