import unittest
from pathlib import Path

from tools.nice_view_xml import load_catalog, validate_screen_text
from tools.nice_view_xml_codegen import write_generated


FIELDS = load_catalog()
XML_EXAMPLE = Path(__file__).parent / "docs" / "examples" / "basic-status.xml"


def make_screen(body: str = "", width: int = 160, height: int = 68) -> str:
    return (
        '<component><view extends="lv_obj" '
        f'width="{width}" height="{height}">{body}</view></component>'
    )


class NiceViewXmlValidationTests(unittest.TestCase):
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

        self.assertTrue(any("unsupported attributes: magic" in error for error in errors))
        self.assertTrue(
            any("unsupported format 'uppercase'" in error for error in errors)
        )

    def test_generate_writes_binding_table(self):
        import tempfile

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

    def test_ui_screens_validate_and_embed_background(self):
        from tools.nice_view_xml import validate_screen

        screens = Path(__file__).parent / "docs" / "ui" / "screens"
        for name in (
            "status_screen.xml",
            "day.xml",
            "night.xml",
            "oled-128x32.xml",
            "oled-128x32-mirror.xml",
        ):
            path = screens / name
            errors = validate_screen(path)
            self.assertEqual(errors, [], msg=f"{name}: {errors}")

        generated = (
            Path(__file__).parent
            / "src"
            / "generated_xml"
            / "default"
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


if __name__ == "__main__":
    unittest.main()