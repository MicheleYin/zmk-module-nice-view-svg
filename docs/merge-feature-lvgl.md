# XML-First Release Checklist

The module branch is `feature/lvgl`. This work prepares a reviewable merge into
`main`; it does not update the Sofle manifest or publish the branch.

## Before merge

1. Regenerate the five firmware XML themes and paired PNG gallery.
2. Run `pre-commit run` and `uv run --isolated --with-requirements tools/requirements.txt python -m unittest`.
3. Confirm CI compiles the XML-enabled Nice!View and OLED configurations.
4. Review the final diff and then merge only when explicitly approved.

## PR shape (recommended)

The release makes XML the default and only screen source. Offline SVG artwork
conversion remains available; SVG screen parsing, generation, and runtime files
are removed.

## Sofle follow-up (separate)

1. After merge, point `zmk-sofle` west.yml module revision at the release.
2. Keep ZMK fork pin on `feature/nice-view` unless the XML screen needs new ZMK APIs
   (it should not: device path is compiled C only).

## Theme Outputs

See [widget-authoring-xml.md](widget-authoring-xml.md) for source screens,
generation commands, and automatic display-size selection.
