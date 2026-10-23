import shutil
import threading
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw
from watchdog.observers import Observer

from tools.nice_view_xml import (
    generate,
    load_catalog,
    validate_screen,
    validate_screen_text,
)
from tools.nice_view_xml_assets import (
    export_static_svg_background,
    monochrome_pixels_from_png,
)
from tools.nice_view_xml_codegen import write_generated
from tools.nice_view_xml_components import expand_screen_file
from tools.nice_view_xml_live import (
    LivePreviewHandler,
    LivePreviewServer,
    build_paired_preview_config,
    build_preview_config,
)
from tools.nice_view_xml_preview import preview_png, preview_xml_text


FIELDS = load_catalog()
XML_EXAMPLE = Path(__file__).parent / "docs" / "examples" / "basic-status.xml"


def make_screen(body: str = "", width: int = 160, height: int = 68) -> str:
    return (
        '<component><view extends="lv_obj" '
        f'width="{width}" height="{height}">{body}</view></component>'
    )


class NiceViewXmlValidationTests(unittest.TestCase):
    def test_preview_keeps_file_backed_images_below_lvgl_widgets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            asset_path = Path(temp_dir) / "background.png"
            output_path = Path(temp_dir) / "preview.png"
            background = Image.new("RGB", (24, 20), "white")
            ImageDraw.Draw(background).point((0, 0), fill="black")
            background.save(asset_path)
            root = ET.parse(XML_EXAMPLE).getroot()
            view = root.find("view")
            self.assertIsNotNone(view)
            view.insert(0, ET.Element("lv_image", src="background.png", x="0", y="0"))
            xml = ET.tostring(root, encoding="unicode")
            screen_path.write_text(xml)

            normalized = preview_xml_text(
                xml,
                FIELDS,
                {"battery.left.percent": 87, "layer.index": 0, "split.connected": True},
                "central",
            )
            preview_png(normalized, output_path, screen_path)

            rendered = Image.open(output_path).convert("1")
            self.assertEqual(rendered.size, (160, 68))
            self.assertEqual(rendered.getpixel((0, 0)), 0)
            label_pixels = rendered.crop((2, 2, 55, 18)).getdata()
            self.assertIn(0, label_pixels)

    def test_preview_status_text_matches_firmware_baseline_and_anchor(self):
        xml = make_screen(
            '<zmk_status_text field="battery.left.percent" format="percent" '
            'x="158" y="18" font_size="11" anchor="end" />',
            width=128,
            height=32,
        )

        normalized = ET.fromstring(
            preview_xml_text(
                xml,
                FIELDS,
                {"battery.left.percent": 87},
                "central",
            )
        )
        label = normalized.find(".//lv_label")

        self.assertIsNotNone(label)
        self.assertEqual(label.get("x"), "30")
        self.assertEqual(label.get("y"), "7")
        self.assertEqual(label.get("width"), "128")
        self.assertEqual(label.get("height"), "13")
        self.assertEqual(label.get("style_text_align"), "right")
        self.assertEqual(label.get("style_text_font"), "lv_montserrat_12")

    def test_static_label_font_size_is_shared_by_preview_and_codegen(self):
        xml = make_screen('<lv_label text="LINK" x="4" y="4" font_size="8" />')
        normalized = ET.fromstring(preview_xml_text(xml, FIELDS, {}, "central"))
        label = normalized.find(".//lv_label")
        self.assertIsNotNone(label)
        self.assertEqual(label.get("style_text_font"), "lv_montserrat_8")

        status_xml = make_screen(
            '<zmk_status_text field="battery.left.percent" format="percent" '
            'x="4" y="12" font_size="8" />'
        )
        status_label = ET.fromstring(
            preview_xml_text(
                status_xml, FIELDS, {"battery.left.percent": 87}, "central"
            )
        ).find(".//lv_label")
        self.assertIsNotNone(status_label)
        self.assertEqual(status_label.get("style_text_font"), "lv_unscii_8")

        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            output_dir = Path(temp_dir) / "generated"
            _, source_path = write_generated(screen_path, output_dir, xml)

            source = source_path.read_text()
            self.assertIn(
                "lv_obj_set_style_text_font(label, &lv_font_montserrat_8, LV_PART_MAIN);",
                source,
            )
            self.assertIn("lv_obj_set_style_pad_all(screen, 0, LV_PART_MAIN);", source)

    @unittest.skipUnless(shutil.which("rsvg-convert"), "rsvg-convert is required")
    def test_background_export_removes_svg_text(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="8">'
            '<rect width="16" height="8" fill="white"/>'
            '<text x="0" y="7" fill="black">DUPLICATE</text></svg>'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "screen.svg"
            output = Path(temp_dir) / "background.png"
            source.write_text(svg)

            export_static_svg_background(source, output)
            dimensions, pixels = monochrome_pixels_from_png(output.read_bytes())

        self.assertEqual(dimensions, (16, 8))
        self.assertEqual(set(pixels), {1})

    def test_authored_example_validates_for_its_panel(self):
        errors = validate_screen_text(
            XML_EXAMPLE.read_text(), FIELDS, expected_dimensions=(160, 68)
        )

        self.assertEqual(errors, [])

    def test_validates_native_screen_and_typed_status_widgets(self):
        xml = make_screen(
            '<zmk_status_text field="battery.central.percent" format="percent"/>'
            '<zmk_status_bar field="battery.peripheral.percent"/>'
            '<zmk_status_when field="ble.connected_profiles" test="bit_set" bit="2">'
            '<lv_label text="Connected"/></zmk_status_when>'
        )

        self.assertEqual(
            validate_screen_text(xml, FIELDS, expected_dimensions=(160, 68)), []
        )

    def test_rejects_invalid_xml_and_non_component_root(self):
        self.assertTrue(
            validate_screen_text("<component>", FIELDS)[0].startswith("invalid XML:")
        )
        self.assertIn(
            "root element must be <component>",
            validate_screen_text("<view width='160' height='68'/>", FIELDS),
        )

    def test_checks_dimensions_and_panel_selection(self):
        errors = validate_screen_text(
            make_screen(width=128, height=32), FIELDS, (160, 68)
        )

        self.assertIn("screen dimensions are 128x32, expected 160x68", errors)

    def test_checks_field_existence_type_and_role(self):
        xml = make_screen(
            '<zmk_status_bar field="layer.name"/>'
            '<zmk_status_text field="not.a.field"/>'
            '<zmk_status_text field="usb.powered" role="peripheral"/>'
        )

        errors = validate_screen_text(xml, FIELDS)

        self.assertTrue(
            any("cannot bind string field 'layer.name'" in error for error in errors)
        )
        self.assertTrue(
            any("references unknown field 'not.a.field'" in error for error in errors)
        )
        self.assertTrue(
            any("not available on role 'peripheral'" in error for error in errors)
        )

    def test_checks_status_values_and_bit_indices(self):
        xml = make_screen(
            '<zmk_status_when field="output.selected" test="equals" value="wifi"/>'
            '<zmk_status_when field="ble.connected_profiles" test="bit_set" bit="8"/>'
            '<zmk_status_when field="split.connected" test="equals"/>'
        )

        errors = validate_screen_text(xml, FIELDS)

        self.assertTrue(any("value 'wifi' is invalid" in error for error in errors))
        self.assertTrue(any("bit 8 is outside" in error for error in errors))
        self.assertTrue(any("needs a value" in error for error in errors))
        self.assertTrue(
            any("needs a nested <lv_label> or <lv_image>" in error for error in errors)
        )

    def test_rejects_unknown_status_attributes_and_formats(self):
        xml = make_screen(
            '<zmk_status_text field="layer.name" format="uppercase" magic="yes"/>'
        )

        errors = validate_screen_text(xml, FIELDS)

        self.assertTrue(
            any("unsupported attributes: magic" in error for error in errors)
        )
        self.assertTrue(
            any("unsupported format 'uppercase'" in error for error in errors)
        )

    def test_generate_writes_binding_table(self):
        xml = make_screen(
            '<zmk_status_text field="layer.index" x="4" y="4"/>'
            '<zmk_status_bar field="battery.central.percent" x="10" y="20" '
            'width="40" height="4"/>'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            screen_path = output_dir / "screen.xml"
            screen_path.write_text(xml)
            header_path, source_path = write_generated(screen_path, output_dir)
            header = header_path.read_text()
            source = source_path.read_text()

        self.assertIn("ZMK_NVP_SVG_BINDING_COUNT 2", header)
        self.assertIn("zmk_nvp_svg_bindings", header)
        self.assertIn("zmk_nvp_xml_layout_create", source)

    def test_widget_includes_expand_validate_and_generate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            screen_dir = Path(temp_dir) / "screens"
            widget_dir = Path(temp_dir) / "widgets"
            screen_dir.mkdir()
            widget_dir.mkdir()
            (widget_dir / "layer.xml").write_text(
                '<fragment><zmk_include src="layer-value.xml" '
                'kind="{{kind}}" x="{{x}}"/></fragment>'
            )
            (widget_dir / "layer-value.xml").write_text(
                '<fragment><zmk_status_text field="layer.{{kind}}" '
                'x="{{x}}" y="4"/></fragment>'
            )
            screen_path = screen_dir / "sample.xml"
            screen_path.write_text(
                '<component><view width="160" height="68">'
                '<zmk_include src="../widgets/layer.xml" kind="index" x="8"/>'
                "</view></component>"
            )

            dependencies: set[Path] = set()
            expanded = expand_screen_file(screen_path, dependencies)
            self.assertIn('field="layer.index"', expanded)
            self.assertNotIn("zmk_include", expanded)
            self.assertEqual(
                dependencies,
                {
                    screen_path.resolve(),
                    (widget_dir / "layer.xml").resolve(),
                    (widget_dir / "layer-value.xml").resolve(),
                },
            )
            self.assertEqual(validate_screen(screen_path), [])
            header_path, _ = write_generated(
                screen_path, screen_dir / "generated", expanded
            )
            header = header_path.read_text()

        self.assertIn("ZMK_NVP_SVG_BINDING_COUNT 1", header)

    def test_modular_samples_expand_validate_and_generate(self):
        samples = Path(__file__).parent / "docs" / "ui" / "samples"
        for path in sorted(samples.glob("*.xml")):
            with (
                self.subTest(sample=path.name),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                self.assertEqual(validate_screen(path), [])
                expanded = expand_screen_file(path)
                self.assertNotIn("zmk_include", expanded)
                preview = build_preview_config(path)
                self.assertTrue(preview["bindings"])
                generate(path, Path(temp_dir))
                header_path = Path(temp_dir) / "status_screen_gen.h"
                header = header_path.read_text()
                self.assertIn("ZMK_NVP_SVG_BINDING_COUNT", header)

    def test_preview_matches_boolean_when_values(self):
        xml = make_screen(
            '<zmk_status_when field="split.connected" test="equals" value="true">'
            '<lv_label text="LINKED"/></zmk_status_when>'
            '<zmk_status_when field="split.connected" test="equals" value="false">'
            '<lv_label text="LOST"/></zmk_status_when>'
        )

        for value, expected in ((True, "LINKED"), (False, "LOST")):
            with self.subTest(value=value):
                rendered = preview_xml_text(
                    xml, FIELDS, {"split.connected": value}, "central"
                )
                self.assertIn(f'text="{expected}"', rendered)

    def test_paired_preview_merges_screen_bindings_and_dimensions(self):
        screens = Path(__file__).parent / "docs" / "ui" / "screens"
        config = build_paired_preview_config(
            screens / "nice-view-left.xml", screens / "nice-view-right.xml"
        )

        self.assertTrue(config["paired"])
        self.assertEqual(
            config["panelRoles"], {"left": "central", "right": "peripheral"}
        )
        self.assertEqual(config["screens"]["left"]["width"], 160)
        self.assertIn(
            "battery.left.percent", {field["id"] for field in config["bindings"]}
        )
        self.assertIn(
            "battery.right.percent", {field["id"] for field in config["bindings"]}
        )

    def test_oled_left_and_right_keep_the_same_layout(self):
        screens = Path(__file__).parent / "docs" / "ui" / "screens"
        left = ET.parse(screens / "oled-left.xml").getroot()
        right = ET.parse(screens / "oled-right.xml").getroot()

        for field_id in ("output.selected", "layer.index"):
            left_binding = left.find(f".//zmk_status_text[@field='{field_id}']")
            right_binding = right.find(f".//zmk_status_text[@field='{field_id}']")
            self.assertIsNotNone(left_binding)
            self.assertIsNotNone(right_binding)
            self.assertEqual(
                (left_binding.get("x"), left_binding.get("y")),
                (right_binding.get("x"), right_binding.get("y")),
            )

    def test_firmware_selector_routes_all_four_screen_outputs(self):
        source_root = Path(__file__).parent / "src"
        header_selector = (source_root / "xml_screen.c").read_text()
        source_selector = (source_root / "generated_xml_screen.c").read_text()

        for theme in (
            "nice_view_left",
            "nice_view_right",
            "oled_left",
            "oled_right",
        ):
            with self.subTest(theme=theme):
                self.assertIn(
                    f'generated_xml/{theme}/status_screen_gen.h', header_selector
                )
                self.assertIn(
                    f'generated_xml/{theme}/status_screen_gen.c', source_selector
                )

    def test_ui_screens_validate_and_embed_background(self):
        from tools.nice_view_xml import validate_screen

        screens = Path(__file__).parent / "docs" / "ui" / "screens"
        for name in (
            "nice-view-left.xml",
            "nice-view-right.xml",
            "oled-left.xml",
            "oled-right.xml",
        ):
            path = screens / name
            errors = validate_screen(path)
            self.assertEqual(errors, [], msg=f"{name}: {errors}")

        generated = (
            Path(__file__).parent
            / "src"
            / "generated_xml"
            / "nice_view_left"
            / "status_screen_gen.c"
        )
        header = generated.with_suffix(".h").read_text()
        source = generated.read_text()
        self.assertIn("ZMK_NVP_XML_HAS_BACKGROUND 1", header)
        self.assertRegex(header, r"ZMK_NVP_SVG_VISIBLE_ASSET_COUNT [1-9]")
        self.assertIn("zmk_nvp_svg_background", source)
        self.assertIn("zmk_nvp_svg_visible_assets", source)
        self.assertIn("lv_image_create", source)
        self.assertIn("LV_COLOR_FORMAT_I2", source)

    def test_generated_firmware_themes_match_xml_sources(self):
        screens = Path(__file__).parent / "docs" / "ui" / "screens"
        generated_root = Path(__file__).parent / "src" / "generated_xml"
        themes = {
            "nice_view_left": "nice-view-left.xml",
            "nice_view_right": "nice-view-right.xml",
            "oled_left": "oled-left.xml",
            "oled_right": "oled-right.xml",
        }
        for theme, screen_name in themes.items():
            with self.subTest(theme=theme), tempfile.TemporaryDirectory() as temp_dir:
                generate(screens / screen_name, Path(temp_dir))
                for extension in (".c", ".h"):
                    generated = Path(temp_dir) / f"status_screen_gen{extension}"
                    committed = generated_root / theme / f"status_screen_gen{extension}"
                    self.assertEqual(generated.read_bytes(), committed.read_bytes())

    def test_live_reload_keeps_last_good_snapshot_on_invalid_xml(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            screen_path.write_text(
                make_screen(
                    '<zmk_status_text field="battery.left.percent" x="1" y="1"/>'
                )
            )
            server = LivePreviewServer(("127.0.0.1", 0), LivePreviewHandler)
            server.fields = FIELDS
            server.screen_paths = (screen_path,)
            server.left_role = "central"
            server.right_role = "peripheral"
            server.legacy_inverted = False
            server.observer = Observer()
            server.watched_dirs = set()
            server.state_lock = threading.RLock()
            server.change_condition = threading.Condition()
            server.revision = 0
            server.reload_error = None
            try:
                self.assertTrue(server.reload_sources())
                initial_xml = server.xml_text
                self.assertIn(
                    screen_path.resolve().parent,
                    server.watched_dirs,
                )

                screen_path.write_text(
                    make_screen(
                        '<zmk_status_text field="battery.left.percent" x="2" y="1"/>'
                    )
                )
                self.assertTrue(server.reload_sources())
                last_good_xml = server.xml_text
                self.assertNotEqual(initial_xml, last_good_xml)

                screen_path.write_text("<component")
                self.assertFalse(server.reload_sources())
                self.assertEqual(server.xml_text, last_good_xml)
                self.assertIsNotNone(server.reload_error)
            finally:
                server.observer.unschedule_all()
                server.server_close()

    def test_live_watcher_refreshes_nested_widget_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            screen_dir = Path(temp_dir)
            widget_dir = screen_dir / "widgets"
            widget_dir.mkdir()
            screen_path = screen_dir / "screen.xml"
            widget_path = widget_dir / "label.xml"
            widget_path.write_text(
                '<fragment><lv_label text="{{label}}" x="1" y="1"/></fragment>'
            )
            screen_path.write_text(
                '<component><view width="160" height="68">'
                '<zmk_include src="widgets/label.xml" label="BEFORE"/>'
                "</view></component>"
            )
            server = LivePreviewServer(("127.0.0.1", 0), LivePreviewHandler)
            server.fields = FIELDS
            server.screen_paths = (screen_path,)
            server.left_role = "central"
            server.right_role = "peripheral"
            server.legacy_inverted = False
            server.observer = Observer()
            server.watched_dirs = set()
            server.state_lock = threading.RLock()
            server.change_condition = threading.Condition()
            server.revision = 0
            server.reload_error = None
            try:
                self.assertTrue(server.reload_sources())
                self.assertIn("BEFORE", server.xml_text)
                server.observer.start()
                initial_revision = server.revision
                widget_path.write_text(
                    '<fragment><lv_label text="{{label}}" x="2" y="1"/></fragment>'
                )
                with server.change_condition:
                    changed = server.change_condition.wait_for(
                        lambda: server.revision > initial_revision, timeout=3
                    )
                self.assertTrue(changed, "nested widget change was not observed")
                self.assertIn('x="2"', server.xml_text)
                self.assertIsNone(server.reload_error)
            finally:
                server.observer.stop()
                server.observer.join()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
