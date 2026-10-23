#!/usr/bin/env python3
"""Render a component XML screen to PNG for host tooling and CI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR.parent))

from tools.nice_view_xml import load_catalog  # noqa: E402
from tools.nice_view_xml_preview import preview_png, preview_xml_text  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screen", type=Path)
    parser.add_argument("--values", type=Path, required=True)
    parser.add_argument("--role", choices=["central", "peripheral"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        fields = load_catalog()
        values = json.loads(args.values.read_text()).get("values", {})
        expanded = preview_xml_text(args.screen.read_text(), fields, values, args.role)
        preview_png(expanded, args.output, args.screen)
    except (OSError, TypeError, ValueError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
