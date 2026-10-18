import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

from tools.nice_view_svg import (
    MAX_DYNAMIC_BINDINGS,
    _compile_visible_assets,
    _generate_header,
    _isolated_visible_svg,
    _load_pillow_image,
    _monochrome_preview_png,
    _pack_i2_pixels,
    _pack_monochrome_pixels,
    _rotate_png_180,
    load_catalog,
    load_widget_catalog,
    preview_svg_text,
    validate_svg_text,
)
from tools.nice_view_svg_live import build_preview_config

ROOT = Path(__file__).parent
CATALOG_PATH = ROOT / "tools" / "status_fields.json"
WIDGET_CATALOG_PATH = ROOT / "tools" / "widget_types.json"
SOURCE_SVG = ROOT / "docs" / "nice-view-plus-preview.svg"
WIDGET_EXAMPLE = ROOT / "docs" / "widget-example.svg"
FIELDS = load_catalog(CATALOG_PATH)
WIDGETS = load_widget_catalog(WIDGET_CATALOG_PATH)


def make_svg(body: str, view_box: str = "0 0 160 68") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">{body}</svg>'


class NiceViewSvgValidationTests(unittest.TestCase):
    def test_authored_svg_validates_for_both_roles(self):
        errors = validate_svg_text(SOURCE_SVG.read_text(), FIELDS)
        self.assertEqual(errors, [])

    def test_widget_example_validates_against_widget_catalog(self):
        errors = validate_svg_text(
            WIDGET_EXAMPLE.read_text(), FIELDS, widget_catalog=WIDGETS
        )
        self.assertEqual(errors, [])

    def test_screen_theme_sources_validate_against_widget_catalog(self):
        header_names = {
            "default": "generated_screen.h",
            "day": "generated_day_screen.h",
            "night": "generated_night_screen.h",
            "oled-128x32": "generated_oled_screen.h",
            "oled-128x32-mirror": "generated_oled_mirror_screen.h",
        }
        for theme in (
            "default",
            "day",
            "night",
            "oled-128x32",
            "oled-128x32-mirror",
        ):
            with self.subTest(theme=theme):
                svg_path = ROOT / "docs" / "screens" / f"{theme}.svg"
                errors = validate_svg_text(
                    svg_path.read_text(), FIELDS, widget_catalog=WIDGETS
                )
                self.assertEqual(errors, [])
                header = (ROOT / "src" / header_names[theme]).read_text()
                width, height = (
                    (128, 32) if theme.startswith("oled-128x32") else (160, 68)
                )
                self.assertIn(f"#define ZMK_NVP_SVG_WIDTH {width}", header)
                self.assertIn(f"#define ZMK_NVP_SVG_HEIGHT {height}", header)

    def test_day_and_night_ble_assets_contain_visible_pixels(self):
        for theme in ("day", "night"):
            with self.subTest(theme=theme):
                svg_text = (ROOT / "docs" / "screens" / f"{theme}.svg").read_text()
                root = ET.fromstring(svg_text)
                assets = _compile_visible_assets(svg_text)
                for index, element in enumerate(root.iter()):
                    if element.get("data-nvp-bind") not in {
                        "ble.active_profile",
                        "ble.connected_profiles",
                    }:
                        continue
                    with self.subTest(
                        field=element.get("data-nvp-bind"),
                        slot=element.get("data-nvp-slot"),
                    ):
                        self.assertTrue(
                            any(assets[index][2]),
                            "BLE state asset rasterized as transparent",
                        )

    def test_time_field_is_removed_from_themes_and_catalog(self):
        self.assertNotIn("time.current", FIELDS)
        for theme in ("day", "night"):
            with self.subTest(theme=theme):
                root = ET.parse(ROOT / "docs" / "screens" / f"{theme}.svg").getroot()
                bindings = {element.get("data-nvp-bind") for element in root.iter()}
                self.assertNotIn("time.current", bindings)

    def test_documentation_examples_validate_against_widget_catalog(self):
        examples = sorted((ROOT / "docs" / "examples").glob("*.svg"))
        self.assertTrue(examples, "No documentation SVG examples found")
        for svg_path in examples:
            with self.subTest(example=svg_path.name):
                svg_text = svg_path.read_text()
                errors = validate_svg_text(svg_text, FIELDS, widget_catalog=WIDGETS)
                self.assertEqual(errors, [])
                _generate_header(svg_text, bytes(1360))
                for role in ("central", "peripheral"):
                    values_path = ROOT / "tools" / f"sample_status.{role}.json"
                    values_document = json.loads(values_path.read_text())
                    values = values_document.get("values", values_document)
                    preview = preview_svg_text(svg_text, FIELDS, values, role, WIDGETS)
                    ET.fromstring(preview)

    def test_live_preview_config_exposes_all_bound_fields_and_renderers(self):
        examples = sorted((ROOT / "docs" / "examples").glob("*.svg"))
        renderer_types = set()
        for svg_path in examples:
            config = build_preview_config(svg_path)
            source = ET.parse(svg_path).getroot()
            expected_fields = {
                element.get("data-nvp-bind")
                for element in source.iter()
                if element.get("data-nvp-bind")
            }
            bindings = {binding["id"]: binding for binding in config["bindings"]}
            self.assertEqual(set(bindings), expected_fields)
            self.assertIn("central", config["values"])
            self.assertIn("peripheral", config["values"])
            for binding in bindings.values():
                renderer_types.update(binding["renderers"])
                self.assertIn(binding["id"], config["values"]["central"])
                self.assertIn(binding["id"], config["values"]["peripheral"])
        self.assertEqual(renderer_types, {"bar", "percent", "ring", "text", "visible"})

    def test_live_preview_config_exposes_canvas_and_inversion(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            svg_path = Path(temporary_directory) / "custom.svg"
            svg_path.write_text(make_svg("", "0 0 128 32"))
            config = build_preview_config(svg_path, legacy_inverted=True)

        self.assertEqual((config["width"], config["height"]), (128, 32))
        self.assertTrue(config["legacyInverted"])
        self.assertEqual(config["initialInversionMode"], "legacy")

    def test_split_connected_is_available_on_both_roles(self):
        field = FIELDS["split.connected"]
        self.assertEqual(set(field["available_on"]), {"central", "peripheral"})
        self.assertEqual(
            set(field["sources"]),
            {"central", "peripheral"},
        )
        for theme in ("default", "day", "night"):
            with self.subTest(theme=theme):
                path = ROOT / "docs" / "screens" / f"{theme}.svg"
                config = build_preview_config(path)
                binding = next(
                    item
                    for item in config["bindings"]
                    if item["id"] == "split.connected"
                )
                self.assertEqual(binding["roles"], ["central", "peripheral"])
                for role in ("central", "peripheral"):
                    rendered = preview_svg_text(
                        path.read_text(),
                        FIELDS,
                        {"split.connected": True},
                        role,
                        WIDGETS,
                    )
                    indicator = next(
                        element
                        for element in ET.fromstring(rendered).iter()
                        if element.get("data-nvp-bind") == "split.connected"
                    )
                    self.assertIsNone(indicator.get("display"))

    def test_wpm_examples_bind_wpm_for_both_roles(self):
        for example in ("wpm.svg", "wpm-tile.svg"):
            with self.subTest(example=example):
                config = build_preview_config(ROOT / "docs" / "examples" / example)
                bindings = {binding["id"]: binding for binding in config["bindings"]}
                self.assertEqual(set(bindings), {"wpm.current"})
                for binding in bindings.values():
                    self.assertEqual(binding["roles"], ["central", "peripheral"])
                self.assertEqual(config["values"]["central"]["wpm.current"], 42)

    def test_day_theme_shows_both_split_connection_states(self):
        svg = (ROOT / "docs" / "screens" / "day.svg").read_text()
        for role in ("central", "peripheral"):
            for connected in (True, False):
                with self.subTest(role=role, connected=connected):
                    rendered = preview_svg_text(
                        svg,
                        FIELDS,
                        {"split.connected": connected},
                        role,
                        WIDGETS,
                    )
                    indicators = [
                        element
                        for element in ET.fromstring(rendered).iter()
                        if element.get("data-nvp-bind") == "split.connected"
                    ]
                    visible = next(
                        element
                        for element in indicators
                        if element.get("data-nvp-when") == str(connected).lower()
                    )
                    hidden = next(
                        element
                        for element in indicators
                        if element.get("data-nvp-when") != str(connected).lower()
                    )
                    self.assertIsNone(visible.get("display"))
                    self.assertEqual(hidden.get("display"), "none")

    def test_widget_slot_rejects_incompatible_field(self):
        svg = make_svg(
            '<g id="battery" data-nvp-widget="battery">'
            '<text data-nvp-slot="level" data-nvp-bind="layer.index" '
            'data-nvp-render="text">0</text></g>'
        )
        errors = validate_svg_text(svg, FIELDS, widget_catalog=WIDGETS)
        self.assertIn("field layer.index is not allowed in battery.level", errors)

    def test_widget_state_preview_switches_shape_variants(self):
        svg = make_svg(
            '<g id="connection" data-nvp-widget="connection">'
            '<g data-nvp-slot="selected" data-nvp-bind="output.selected" '
            'data-nvp-render="visible" data-nvp-when="usb" '
            'data-nvp-bounds="0,0,10,10"><rect/></g>'
            '<g data-nvp-slot="selected" data-nvp-bind="output.selected" '
            'data-nvp-render="visible" data-nvp-when="ble" '
            'data-nvp-bounds="0,0,10,10"><circle/></g>'
            "</g>"
        )
        rendered = preview_svg_text(
            svg, FIELDS, {"output.selected": "ble"}, "central", WIDGETS
        )
        root = ET.fromstring(rendered)
        variants = [
            element
            for element in root.iter()
            if element.get("data-nvp-slot") == "selected"
        ]
        self.assertEqual(
            [element.get("display") for element in variants], ["none", None]
        )

    def test_static_svg_with_native_canvas_is_valid(self):
        errors = validate_svg_text(make_svg('<rect width="160" height="68"/>'), FIELDS)
        self.assertEqual(errors, [])

    def test_percent_text_binding_is_valid_for_both_roles(self):
        svg = make_svg(
            '<text x="4" y="10" data-nvp-bind="battery.central.percent" '
            'data-nvp-render="percent">--</text>'
        )
        self.assertEqual(validate_svg_text(svg, FIELDS), [])

    def test_unknown_field_is_rejected(self):
        svg = make_svg(
            '<text data-nvp-bind="battery.magic.percent" data-nvp-render="percent">--</text>'
        )
        self.assertIn(
            "unknown status field: battery.magic.percent",
            validate_svg_text(svg, FIELDS),
        )

    def test_role_inaccessible_field_is_rejected(self):
        svg = make_svg(
            '<text data-nvp-bind="usb.powered" data-nvp-render="text">USB</text>'
        )
        errors = validate_svg_text(svg, FIELDS, {"peripheral"})
        self.assertIn(
            "field usb.powered is unavailable on the peripheral display", errors
        )

    def test_layer_name_is_not_available_on_peripheral(self):
        svg = make_svg(
            '<text data-nvp-bind="layer.name" data-nvp-render="text">BASE</text>'
        )
        errors = validate_svg_text(svg, FIELDS, {"peripheral"})
        self.assertIn(
            "field layer.name is unavailable on the peripheral display", errors
        )

    def test_bar_requires_percent_rect_and_geometry(self):
        svg = make_svg(
            '<rect x="1" y="2" width="10" height="3" '
            'data-nvp-bind="battery.central.percent" data-nvp-render="bar"/>'
        )
        self.assertEqual(validate_svg_text(svg, FIELDS), [])

    def test_bar_rejects_bad_geometry(self):
        svg = make_svg(
            '<rect x="1" y="2" width="auto" height="3" '
            'data-nvp-bind="battery.central.percent" data-nvp-render="bar"/>'
        )
        self.assertTrue(
            any("numeric width" in error for error in validate_svg_text(svg, FIELDS))
        )

    def test_ring_requires_percent_circle_and_valid_geometry(self):
        svg = make_svg(
            '<circle cx="20" cy="20" r="8" fill="none" stroke="#000" '
            'stroke-width="3" data-nvp-bind="battery.central.percent" '
            'data-nvp-render="ring"/>'
        )
        self.assertEqual(validate_svg_text(svg, FIELDS), [])

        invalid = make_svg(
            '<circle cx="20" cy="20" r="8" fill="none" stroke="#000" '
            'data-nvp-bind="battery.central.percent" data-nvp-render="ring"/>'
        )
        self.assertIn(
            "ring battery.central.percent needs numeric stroke-width",
            validate_svg_text(invalid, FIELDS),
        )

    def test_ring_rejects_transformed_ancestors(self):
        svg = make_svg(
            '<g transform="translate(1 1)"><circle cx="20" cy="20" r="8" '
            'fill="none" stroke="#000" stroke-width="3" '
            'data-nvp-bind="battery.central.percent" '
            'data-nvp-render="ring"/></g>'
        )
        self.assertIn(
            "ring battery.central.percent cannot have a transformed ancestor",
            validate_svg_text(svg, FIELDS),
        )

    def test_ring_allows_rotation_about_its_center(self):
        svg = make_svg(
            '<circle cx="20" cy="20" r="8" fill="none" stroke="#000" '
            'stroke-width="3" transform="rotate(-90 20 20)" '
            'data-nvp-bind="battery.central.percent" data-nvp-render="ring"/>'
        )
        self.assertEqual(validate_svg_text(svg, FIELDS), [])

    def test_ring_preview_scales_arc_and_hides_empty_value(self):
        svg = make_svg(
            '<circle cx="20" cy="20" r="8" fill="none" stroke="#000" '
            'stroke-width="3" data-nvp-bind="battery.central.percent" '
            'data-nvp-render="ring"/>'
        )
        rendered = preview_svg_text(
            svg, FIELDS, {"battery.central.percent": 25}, "central"
        )
        ring = next(
            element
            for element in ET.fromstring(rendered).iter()
            if element.tag.endswith("circle")
        )
        dash_length, gap_length = map(float, ring.get("stroke-dasharray").split())
        self.assertAlmostEqual(dash_length / (dash_length + gap_length), 0.25, places=3)
        self.assertEqual(ring.get("transform"), "rotate(-90 20 20)")

        empty = preview_svg_text(svg, FIELDS, {"battery.central.percent": 0}, "central")
        empty_ring = next(
            element
            for element in ET.fromstring(empty).iter()
            if element.tag.endswith("circle")
        )
        self.assertEqual(empty_ring.get("display"), "none")

    def test_ring_header_includes_center_radius_and_stroke_width(self):
        svg = make_svg(
            '<circle cx="20" cy="20" r="8" fill="none" stroke="#fff" '
            'stroke-width="3" data-nvp-bind="battery.central.percent" '
            'data-nvp-render="ring"/>'
        )
        header = _generate_header(svg, bytes(1360))
        self.assertIn("int16_t ring_radius;", header)
        self.assertIn("uint8_t ring_width;", header)
        self.assertIn("uint8_t ring_rounded;", header)
        self.assertIn("ZMK_NVP_SVG_RENDER_RING", header)
        self.assertIn(
            '"battery.central.percent", ZMK_NVP_SVG_RENDER_RING, 3, 255, '
            "20, 20, 0, 0, 8, 3",
            header,
        )

    def test_custom_viewbox_is_accepted(self):
        errors = validate_svg_text(make_svg("", "0 0 320 240"), FIELDS)
        self.assertEqual(errors, [])

    def test_viewbox_supports_standard_oled_resolution(self):
        errors = validate_svg_text(make_svg("", "0 0 128 32"), FIELDS)
        self.assertEqual(errors, [])

    def test_viewbox_requires_zero_origin_and_integer_dimensions(self):
        for view_box in ("1 0 128 32", "0 0 128.5 32", "0 0 0 32"):
            with self.subTest(view_box=view_box):
                errors = validate_svg_text(make_svg("", view_box), FIELDS)
                self.assertTrue(errors)

    def test_dynamic_binding_budget_is_enforced(self):
        body = "".join(
            '<text x="1" y="8" data-nvp-bind="layer.index" '
            'data-nvp-render="text">0</text>'
            for _ in range(MAX_DYNAMIC_BINDINGS + 1)
        )
        errors = validate_svg_text(make_svg(body), FIELDS)
        self.assertIn(
            f"SVG has {MAX_DYNAMIC_BINDINGS + 1} dynamic bindings; "
            f"budget is {MAX_DYNAMIC_BINDINGS}",
            errors,
        )

    def test_catalog_has_unique_ids(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            duplicate_path = Path(temporary_directory) / "fields.json"
            duplicate_path.write_text(
                json.dumps(
                    {"schema_version": 1, "fields": [{"id": "same"}, {"id": "same"}]}
                )
            )
            with self.assertRaisesRegex(ValueError, "duplicate catalog field"):
                load_catalog(duplicate_path)

    def test_static_only_header_has_zero_binding_sentinel(self):
        header = _generate_header(
            make_svg('<rect width="160" height="68"/>'), bytes(1360)
        )
        self.assertIn("#define ZMK_NVP_SVG_BINDING_COUNT 0", header)
        self.assertIn("    { 0 },", header)
        self.assertIn("LV_COLOR_FORMAT_I1", header)

    def test_visible_binding_header_includes_i2_image_asset(self):
        svg = make_svg(
            '<g data-nvp-bind="output.selected" data-nvp-render="visible" '
            'data-nvp-when="usb" data-nvp-bounds="0,0,2,2"/>'
        )
        header = _generate_header(svg, bytes(1360), {1: (2, 2, bytes([0x1B]))})
        self.assertIn("#define ZMK_NVP_SVG_VISIBLE_ASSET_COUNT 1", header)
        self.assertIn("LV_COLOR_FORMAT_I2", header)
        self.assertIn("zmk_nvp_svg_visible_assets[]", header)

    def test_visible_bounds_follow_ancestor_y_flip(self):
        svg = make_svg(
            '<g transform="translate(0,68) scale(1,-1)">'
            '<rect x="4" y="5" width="4" height="4" fill="#000" '
            'data-nvp-slot="value" data-nvp-bind="layer.index" '
            'data-nvp-render="visible" data-nvp-when="2" '
            'data-nvp-bounds="4,5,4,4"/></g>'
        )
        assets = _compile_visible_assets(svg)
        self.assertEqual(assets[2], (4, 4, bytes([0x55] * 4)))

        header = _generate_header(svg, bytes(1360), assets)
        self.assertRegex(
            header,
            r'"layer.index", ZMK_NVP_SVG_RENDER_VISIBLE, 3, 0, 4, 59, 4, 4,',
        )

    def test_bar_geometry_follows_ancestor_y_flip(self):
        svg = make_svg(
            '<g transform="translate(0,68) scale(1,-1)">'
            '<rect x="7" y="8" width="19" height="4" fill="#000" '
            'data-nvp-bind="battery.right.percent" data-nvp-render="bar"/>'
            '</g>'
        )
        header = _generate_header(svg, bytes(1360))
        self.assertRegex(
            header,
            r'"battery.right.percent", ZMK_NVP_SVG_RENDER_BAR, 3, 255, 7, 56, 19, 4,',
        )

    def test_i2_pixels_pack_four_indices_msb_first(self):
        self.assertEqual(_pack_i2_pixels([0, 1, 2, 3], 4, 1), bytes([0x1B]))

    def test_isolated_group_keeps_its_icon_children(self):
        svg = make_svg(
            '<rect id="background" width="160" height="68"/>'
            '<g data-nvp-bind="output.selected" data-nvp-render="visible">'
            '<path id="usb-icon" d="M1 1H5V5H1Z"/></g>'
        )
        isolated = ET.fromstring(_isolated_visible_svg(svg, 2))
        self.assertTrue(
            any(element.get("id") == "usb-icon" for element in isolated.iter())
        )
        self.assertFalse(
            any(element.get("id") == "background" for element in isolated.iter())
        )

    def test_header_includes_annotated_binding_metadata(self):
        svg = make_svg(
            '<text x="4" y="10" data-nvp-bind="battery.central.percent" '
            'data-nvp-render="percent">--</text>'
        )
        header = _generate_header(svg, bytes(1360))
        self.assertIn('"battery.central.percent"', header)
        self.assertIn("ZMK_NVP_SVG_RENDER_PERCENT", header)

    def test_preview_substitutes_text_and_scales_bar(self):
        svg = make_svg(
            '<text data-nvp-bind="battery.central.percent" data-nvp-render="percent" '
            'data-nvp-prefix="C ">--</text>'
            '<rect x="2" y="3" width="20" height="4" '
            'data-nvp-bind="battery.central.percent" data-nvp-render="bar"/>'
        )
        rendered = preview_svg_text(
            svg, FIELDS, {"battery.central.percent": 75}, "central"
        )
        root = ET.fromstring(rendered)
        text = next(element for element in root.iter() if element.tag.endswith("text"))
        bar = next(element for element in root.iter() if element.tag.endswith("rect"))
        self.assertEqual(text.text, "C 75%")
        self.assertEqual(float(bar.get("width")), 15)

    def test_preview_hides_nonmatching_enum_visibility(self):
        svg = make_svg(
            '<rect x="1" y="1" width="2" height="2" '
            'data-nvp-bind="output.selected" data-nvp-render="visible" '
            'data-nvp-when="usb"/>'
        )
        rendered = preview_svg_text(svg, FIELDS, {"output.selected": "ble"}, "central")
        root = ET.fromstring(rendered)
        rect = next(element for element in root.iter() if element.tag.endswith("rect"))
        self.assertEqual(rect.get("display"), "none")

    def test_integer_visibility_checks_profile_index_range(self):
        svg = make_svg(
            '<rect x="1" y="1" width="2" height="2" '
            'data-nvp-bind="ble.active_profile" data-nvp-render="visible" '
            'data-nvp-when="4"/>'
        )
        self.assertEqual(validate_svg_text(svg, FIELDS), [])

        out_of_range = make_svg(
            '<rect x="1" y="1" width="2" height="2" '
            'data-nvp-bind="ble.active_profile" data-nvp-render="visible" '
            'data-nvp-when="8"/>'
        )
        self.assertTrue(
            any(
                "out of range" in error
                for error in validate_svg_text(out_of_range, FIELDS)
            )
        )

    def test_bitmask_visibility_selects_individual_connected_profiles(self):
        svg = make_svg(
            '<rect x="1" y="1" width="3" height="3" '
            'data-nvp-bind="ble.connected_profiles" data-nvp-render="visible" '
            'data-nvp-when="set" data-nvp-bit="2" data-nvp-bounds="1,1,3,3"/>'
        )
        self.assertEqual(validate_svg_text(svg, FIELDS), [])
        header = _generate_header(svg, bytes(1360))
        self.assertIn('"set", 2 }', header)
        rendered = preview_svg_text(
            svg, FIELDS, {"ble.connected_profiles": 5}, "central"
        )
        root = ET.fromstring(rendered)
        marker = next(
            element for element in root.iter() if element.tag.endswith("rect")
        )
        self.assertIsNone(marker.get("display"))

        invalid = svg.replace('data-nvp-bit="2"', 'data-nvp-bit="8"')
        self.assertIn(
            "data-nvp-bit is out of range", validate_svg_text(invalid, FIELDS)[0]
        )

    def test_screen_profile_markers_follow_connected_profile_mask(self):
        svg = (ROOT / "docs" / "screens" / "default.svg").read_text()
        values = {"ble.connected_profiles": 5}
        rendered = preview_svg_text(svg, FIELDS, values, "central", WIDGETS)
        root = ET.fromstring(rendered)
        markers = [
            element
            for element in root.iter()
            if element.get("data-nvp-slot") == "connected"
            and element.get("data-nvp-bind") == "ble.connected_profiles"
        ]
        self.assertEqual(len(markers), 5)
        self.assertEqual(
            [marker.get("display") is None for marker in markers],
            [True, False, True, False, False],
        )

    def test_role_fixtures_select_output_profile_and_half(self):
        cases = (
            ("central", "usb", "0", "left", "USB", "1"),
            ("peripheral", "ble", "3", "right", "BLE", "4"),
        )
        for role, output, profile, half, output_label, profile_label in cases:
            with self.subTest(role=role):
                values_path = ROOT / "tools" / f"sample_status.{role}.json"
                values = json.loads(values_path.read_text())["values"]
                self.assertEqual(values["output.selected"], output)
                rendered = preview_svg_text(
                    SOURCE_SVG.read_text(), FIELDS, values, role
                )
                root = ET.fromstring(rendered)
                output_element = next(
                    element
                    for element in root.iter()
                    if element.get("data-nvp-bind") == "output.selected"
                    and element.get("data-nvp-render") == "text"
                )
                self.assertEqual(output_element.text, output_label)

                selected_profile = next(
                    element
                    for element in root.iter()
                    if element.get("data-nvp-bind") == "ble.active_profile"
                    and element.get("data-nvp-render") == "visible"
                    and element.tag.endswith("rect")
                    and element.get("data-nvp-when") == profile
                )
                self.assertIsNone(selected_profile.get("display"))

                selected_profile_label = next(
                    element
                    for element in root.iter()
                    if element.get("data-nvp-bind") == "ble.active_profile"
                    and element.get("data-nvp-render") == "visible"
                    and element.tag.endswith("text")
                    and element.get("data-nvp-when") == profile
                )
                self.assertIsNone(selected_profile_label.get("display"))
                self.assertEqual(selected_profile_label.text, profile_label)

                selected_half = next(
                    element
                    for element in root.iter()
                    if element.get("data-nvp-bind") == "display.half"
                    and element.get("data-nvp-render") == "visible"
                    and element.get("data-nvp-when") == half
                )
                self.assertIsNone(selected_half.get("display"))

    def test_pbm_is_packed_msb_first_with_black_bits_set(self):
        pixels = [0, 1, 1, 0, 1, 0, 0, 1]
        self.assertEqual(
            _pack_monochrome_pixels(pixels, 8, 1, (8, 1)), bytes([0b10010110])
        )

    def test_monochrome_packing_pads_each_non_aligned_row(self):
        pixels = [0, 1, 0, 1, 0, 1, 0, 1, 1, 0]
        self.assertEqual(
            _pack_monochrome_pixels(pixels, 5, 2),
            bytes([0b10101000, 0b01001000]),
        )

    def test_monochrome_preview_png_uses_firmware_threshold(self):
        image_module = _load_pillow_image("tests require uv and tools/requirements.txt")
        source = image_module.new("L", (3, 1))
        source.putdata([127, 128, 255])
        png = BytesIO()
        source.save(png, format="PNG")

        monochrome = _monochrome_preview_png(png.getvalue())
        with image_module.open(BytesIO(monochrome)) as result:
            self.assertEqual(result.mode, "1")
            self.assertEqual(result.get_flattened_data(), (0, 255, 255))

    def test_monochrome_preview_png_can_invert_firmware_pixels(self):
        image_module = _load_pillow_image("tests require uv and tools/requirements.txt")
        source = image_module.new("RGBA", (2, 1), (0, 0, 0, 0))
        source.putpixel((1, 0), (0, 0, 0, 255))
        png = BytesIO()
        source.save(png, format="PNG")

        inverted = _monochrome_preview_png(png.getvalue(), True)
        with image_module.open(BytesIO(inverted)) as result:
            self.assertEqual(result.get_flattened_data(), (0, 255))

    def test_generated_header_uses_custom_canvas_dimensions_and_stride(self):
        header = _generate_header(make_svg("", "0 0 128 32"), bytes(512))

        self.assertIn("#define ZMK_NVP_SVG_WIDTH 128", header)
        self.assertIn("#define ZMK_NVP_SVG_HEIGHT 32", header)
        self.assertIn("#define ZMK_NVP_SVG_BITMAP_SIZE 512", header)
        self.assertIn(".stride = 16,", header)
        self.assertIn(
            "#if CONFIG_NICE_VIEW_WIDGET_INVERTED && !CONFIG_ZMK_SVG_WHITE_BACKGROUND",
            header,
        )

    def test_visible_header_geometry_uses_custom_canvas_bounds(self):
        svg = make_svg(
            '<g id="connection" data-nvp-widget="connection">'
            '<g data-nvp-slot="selected" data-nvp-bind="output.selected" '
            'data-nvp-render="visible" data-nvp-when="usb" '
            'data-nvp-bounds="180,1,15,10"><rect/></g></g>',
            "0 0 200 40",
        )
        errors = validate_svg_text(svg, FIELDS, widget_catalog=WIDGETS)
        self.assertEqual(errors, [])
        header = _generate_header(
            svg, bytes(1000), visible_assets={2: (15, 10, bytes(60))}
        )
        self.assertIn("180, 1, 15, 10", header)

    def test_preview_rotation_flips_both_axes(self):
        image_module = _load_pillow_image("tests require uv and tools/requirements.txt")
        image = image_module.new("RGB", (2, 1))
        image.putpixel((0, 0), (0, 0, 0))
        image.putpixel((1, 0), (255, 255, 255))
        source = BytesIO()
        image.save(source, format="PNG")

        rotated = _rotate_png_180(source.getvalue())
        with image_module.open(BytesIO(rotated)) as result:
            self.assertEqual(result.size, (2, 1))
            self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(result.getpixel((1, 0)), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
