# Merge plan: `feature/lvgl` → `main` (and Sofle)

Target branch for the module: `feature/lvgl` (local WIP with XML + offline SVG embeds).
Integration with Sofle remains on `feature/nice-view` pins until you intentionally bump
`zmk-sofle/config/west.yml`.

## Before merge

1. **Commit remaining WIP** on `feature/lvgl` (embeds, docs, regenerated `generated_xml`).
2. **Rebase or merge `main`** into `feature/lvgl` and resolve conflicts in:
   - `README.md`, `AGENTS.md`, `CMakeLists.txt`, `Kconfig`
   - Any overlapping `src/generated_*.h` if `main` regenerated SVG headers
3. **Regenerate** all five XML themes after conflict resolution.
4. **Run** `pre-commit run` and `python3 -m unittest`.
5. **Optional device smoke**: Sofle build with `CONFIG_ZMK_SVG_LVGL_XML=y` on one half.

## PR shape (recommended)

Prefer **one PR into `main`** that:

- Keeps SVG as default (`CONFIG_ZMK_SVG_LVGL_XML` default `n`)
- Adds XML as opt-in
- Documents both paths ([xml-vs-svg.md](xml-vs-svg.md), README, AGENTS.md)

Avoid deleting the SVG pipeline in the same PR.

## Sofle follow-up (separate)

1. Merge/publish module `feature/lvgl` (or tag).
2. Point `zmk-sofle` west.yml module revision at that commit/branch.
3. Enable XML only in the shield configs you want to dogfood.
4. Keep ZMK fork pin on `feature/nice-view` unless LVGL XML needs new ZMK APIs
   (it should not: device path is compiled C only).

## Post-merge backlog (parity with SVG)

Tracked in [xml-vs-svg.md](xml-vs-svg.md). Highest value next:

1. prefix/suffix + color on XML text bindings
2. Fix `not_equals` codegen
3. OLED AUTO without extra `LVGL_XML_OLED` flag (align CMake with DT like SVG)
4. Optional `widget_types.json` validation for XML
5. Share `read_field` / update helpers between `svg_screen.c` and `xml_screen.c`
