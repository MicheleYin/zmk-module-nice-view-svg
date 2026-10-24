from io import BytesIO
from pathlib import Path
import shutil
import threading
import tempfile
import unittest
import xml.etree.ElementTree as ET

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
    load_i1_gif_frames,
    load_i2_gif_frames,
    monochrome_pixels_from_png,
    pack_i2_png,
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
from tools.render_xml_gallery import (
    render_animated_screen_gif,
    render_animation_sheets,
)


FIELDS = load_catalog()
XML_EXAMPLE = Path(__file__).parent / "docs" / "examples" / "basic-status.xml"


def make_screen(body: str = "", width: int = 160, height: int = 68) -> str:
    return (
        '<component><view extends="lv_obj" '
        f'width="{width}" height="{height}">{body}</view></component>'
    )


def make_test_gif(path: Path, loop: int = 0) -> None:
    frames = [Image.new("RGB", (8, 1), "white") for _ in range(2)]
    ImageDraw.Draw(frames[0]).point((0, 0), fill="black")
    ImageDraw.Draw(frames[1]).point((1, 0), fill="black")
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=[50, 120],
        loop=loop,
        disposal=2,
        optimize=False,
    )


class NiceViewXmlValidationTests(unittest.TestCase):
    def test_png_dither_algorithms_produce_distinct_pixels(self):
        gradient = Image.linear_gradient("L").resize((16, 16))
        output = BytesIO()
        gradient.save(output, format="PNG")

        results = {
            algorithm: tuple(monochrome_pixels_from_png(output.getvalue(), algorithm)[1])
            for algorithm in ("none", "floyd-steinberg", "atkinson", "bayer")
        }

        self.assertEqual(len(set(results.values())), 4)

    def test_i2_png_dithering_preserves_transparent_pixels(self):
        image = Image.new("RGBA", (8, 8), (128, 128, 128, 255))
        image.putpixel((0, 0), (0, 0, 0, 0))
        output = BytesIO()
        image.save(output, format="PNG")

        width, height, packed = pack_i2_png(
            output.getvalue(), dither="floyd-steinberg"
        )

        self.assertEqual((width, height), (8, 8))
        self.assertEqual(packed[0] >> 6, 0)

    def test_codegen_honors_image_dither_and_cli_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            output_dir = Path(temp_dir) / "generated"
            image_path = Path(temp_dir) / "gradient.png"
            Image.linear_gradient("L").resize((16, 16)).save(image_path)
            xml = make_screen(
                '<lv_image src="gradient.png" x="0" y="0" dither="none" />'
            )
            screen_path.write_text(xml)

            _, threshold_source = write_generated(
                screen_path, output_dir / "threshold", xml
            )
            bayer_xml = xml.replace('dither="none"', 'dither="bayer"')
            _, attribute_source = write_generated(
                screen_path, output_dir / "attribute", bayer_xml
            )
            _, override_source = write_generated(
                screen_path, output_dir / "override", xml, "bayer"
            )
            threshold_text = threshold_source.read_text()
            attribute_text = attribute_source.read_text()
            override_text = override_source.read_text()

        self.assertNotEqual(threshold_text, override_text)
        self.assertEqual(attribute_text, override_text)

    def test_validation_rejects_unknown_image_dither(self):
        xml = make_screen('<lv_image src="unused.png" dither="jarvis-judice" />')

        errors = validate_screen_text(xml, FIELDS)

        self.assertTrue(any("unsupported dither" in error for error in errors))

    def test_preview_dither_changes_images_but_not_status_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            image_path = Path(temp_dir) / "gradient.png"
            none_path = Path(temp_dir) / "none.png"
            bayer_path = Path(temp_dir) / "bayer.png"
            Image.linear_gradient("L").resize((16, 16)).save(image_path)
            xml = make_screen(
                '<lv_image src="gradient.png" x="0" y="0" width="16" '
                'height="16" dither="bayer" />'
                '<lv_label text="LAYER" x="20" y="50" font_size="8" />'
            )
            screen_path.write_text(xml)
            fields = FIELDS
            rendered = preview_xml_text(xml, fields, {}, "central")
            preview_png(rendered, none_path, screen_path, "none")
            preview_png(rendered, bayer_path, screen_path, "bayer")

            none = Image.open(none_path).convert("1")
            bayer = Image.open(bayer_path).convert("1")

        self.assertNotEqual(
            list(none.crop((0, 0, 16, 16)).getdata()),
            list(bayer.crop((0, 0, 16, 16)).getdata()),
        )
        self.assertEqual(
            list(none.crop((20, 50, 60, 64)).getdata()),
            list(bayer.crop((20, 50, 60, 64)).getdata()),
        )

    def test_gif_frames_are_packed_with_individual_delays(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            gif_path = Path(temp_dir) / "animation.gif"
            make_test_gif(gif_path)

            width, height, packed_frames, play_count = load_i1_gif_frames(gif_path)

        self.assertEqual((width, height), (8, 1))
        self.assertEqual([duration for _, duration in packed_frames], [50, 120])
        self.assertEqual([bitmap[0] for bitmap, _ in packed_frames], [0x80, 0x40])
        self.assertEqual(play_count, 0)

    def test_i2_gif_frames_preserve_transparency(self):
        frames = [Image.new("P", (4, 1), 0) for _ in range(2)]
        palette = [255, 255, 255, 0, 0, 0] + [0, 0, 0] * 254
        for frame in frames:
            frame.putpalette(palette)
        frames[0].putpixel((0, 0), 1)
        frames[1].putpixel((1, 0), 1)

        with tempfile.TemporaryDirectory() as temp_dir:
            gif_path = Path(temp_dir) / "transparent.gif"
            frames[0].save(
                gif_path,
                save_all=True,
                append_images=frames[1:],
                duration=[50, 120],
                loop=0,
                transparency=0,
                disposal=2,
                optimize=False,
            )

            width, height, packed_frames, _ = load_i2_gif_frames(gif_path)

        self.assertEqual((width, height), (4, 1))
        self.assertEqual([bitmap[0] for bitmap, _ in packed_frames], [0x40, 0x10])

    def test_codegen_emits_animated_gif_frames_and_repeat_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            gif_path = Path(temp_dir) / "animation.gif"
            output_dir = Path(temp_dir) / "generated"
            make_test_gif(gif_path, loop=1)
            screen_path.write_text(
                make_screen('<lv_image src="animation.gif" x="3" y="4"/>')
            )

            header_path, source_path = write_generated(screen_path, output_dir)
            header = header_path.read_text()
            source = source_path.read_text()

        self.assertIn("ZMK_NVP_SVG_ANIMATION_COUNT 1", header)
        self.assertIn("zmk_nvp_svg_animation_0_frame_0", source)
        self.assertIn("zmk_nvp_svg_animation_0_frame_1", source)
        self.assertIn("    50U,", source)
        self.assertIn("    120U,", source)
        self.assertIn("{ zmk_nvp_svg_animation_0_frames,", source)
        self.assertIn("2, 2U", source)
        self.assertIn("screen, &zmk_nvp_svg_animations[0],", source)

    def test_codegen_emits_conditional_gif_as_transparent_i2_animation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            gif_path = Path(temp_dir) / "animation.gif"
            output_dir = Path(temp_dir) / "generated"
            make_test_gif(gif_path)
            screen_path.write_text(
                make_screen(
                    '<zmk_status_when field="split.connected" test="equals" '
                    'value="true"><lv_image src="animation.gif" x="3" y="4"/>'
                    '</zmk_status_when>'
                )
            )

            header_path, source_path = write_generated(screen_path, output_dir)
            header = header_path.read_text()
            source = source_path.read_text()

        self.assertIn("ZMK_NVP_SVG_ANIMATION_COUNT 1", header)
        self.assertIn(".cf = LV_COLOR_FORMAT_I2", source)
        self.assertIn("zmk_nvp_svg_visible_animation_indices[] = {\n    0,", source)
        self.assertIn("zmk_nvp_svg_animation_0_frame_1", source)

    def test_gallery_writes_animation_contact_sheet(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            gif_path = Path(temp_dir) / "animation.gif"
            output_dir = Path(temp_dir) / "gallery"
            make_test_gif(gif_path)
            screen_path.write_text(make_screen('<lv_image src="animation.gif"/>'))

            outputs = render_animation_sheets(
                screen_path.read_text(), screen_path, output_dir, "screen"
            )

            self.assertEqual(len(outputs), 1)
            sheet = Image.open(outputs[0]).convert("1")

        self.assertEqual(sheet.size, (16, 15))
        self.assertEqual(sheet.getpixel((0, 14)), 0)
        self.assertEqual(sheet.getpixel((9, 14)), 0)

    def test_gallery_writes_full_screen_animated_gif(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            gif_path = Path(temp_dir) / "animation.gif"
            output_dir = Path(temp_dir) / "gallery"
            make_test_gif(gif_path)
            xml = make_screen(
                '<lv_label text="ANIM" x="2" y="2" />'
                '<lv_image src="animation.gif" x="40" y="10" '
                'width="8" height="1" dither="atkinson" />'
            )
            screen_path.write_text(xml)
            rendered_xml = preview_xml_text(xml, FIELDS, {}, "central")

            output_path = render_animated_screen_gif(
                rendered_xml, screen_path, output_dir, "sample", "atkinson"
            )

            self.assertIsNotNone(output_path)
            with Image.open(output_path) as animation:
                self.assertEqual(animation.size, (160, 68))
                self.assertEqual(animation.n_frames, 2)
                animation.seek(0)
                first_frame = animation.convert("1").tobytes()
                animation.seek(1)
                second_frame = animation.convert("1").tobytes()
                self.assertNotEqual(first_frame, second_frame)

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

        monospace_xml = make_screen(
            '<lv_label text="LAYER" x="4" y="4" font_size="8" '
            'font_family="monospace" />'
        )
        monospace_label = ET.fromstring(
            preview_xml_text(monospace_xml, FIELDS, {}, "central")
        ).find(".//lv_label")
        self.assertIsNotNone(monospace_label)
        self.assertEqual(monospace_label.get("style_text_font"), "lv_unscii_8")

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

        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            output_dir = Path(temp_dir) / "generated"
            _, source_path = write_generated(screen_path, output_dir, monospace_xml)
            self.assertIn(
                "lv_obj_set_style_text_font(label, &lv_font_unscii_8, LV_PART_MAIN);",
                source_path.read_text(),
            )

    def test_profile_labels_use_fixed_centered_cells(self):
        xml = make_screen(
            '<lv_label text="1" x="35" y="40" width="19" height="8" '
            'font_size="8" font_family="monospace" style_text_align="center" />'
        )
        preview_label = ET.fromstring(
            preview_xml_text(xml, FIELDS, {}, "central")
        ).find(".//lv_label")
        self.assertIsNotNone(preview_label)
        self.assertEqual(preview_label.get("width"), "19")
        self.assertEqual(preview_label.get("height"), "8")
        self.assertEqual(preview_label.get("style_text_align"), "center")

        with tempfile.TemporaryDirectory() as temp_dir:
            screen_path = Path(temp_dir) / "screen.xml"
            output_dir = Path(temp_dir) / "generated"
            _, source_path = write_generated(screen_path, output_dir, xml)
            source = source_path.read_text()
            self.assertIn("lv_obj_set_size(label, 19, 8);", source)
            self.assertIn(
                "lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);",
                source,
            )

    def test_profile_number_format_matches_firmware_numbering(self):
        xml = make_screen(
            '<zmk_status_text field="ble.active_profile" format="profile-number" '
            'x="80" y="48" font_size="8" anchor="middle" />'
        )
        for profile_index, expected in ((0, "1"), (4, "5"), (-1, "-")):
            with self.subTest(profile_index=profile_index):
                label = ET.fromstring(
                    preview_xml_text(
                        xml, FIELDS, {"ble.active_profile": profile_index}, "central"
                    )
                ).find(".//lv_label")
                self.assertIsNotNone(label)
                self.assertEqual(label.get("text"), expected)

    def test_nice_view_shows_one_profile_number_at_a_fixed_position(self):
        screens = Path(__file__).parent / "docs" / "ui" / "screens"
        for name in ("nice-view-left.xml", "nice-view-right.xml"):
            with self.subTest(screen=name):
                root = ET.parse(screens / name).getroot()
                profile_numbers = root.findall(
                    ".//zmk_status_text[@field='ble.active_profile']"
                )
                self.assertEqual(len(profile_numbers), 1)
                self.assertEqual(profile_numbers[0].get("format"), "profile-number")
                self.assertEqual(profile_numbers[0].get("x"), "80")
                self.assertEqual(profile_numbers[0].get("y"), "48")
                self.assertEqual(profile_numbers[0].get("anchor"), "middle")
                self.assertIsNone(
                    root.find(".//zmk_status_when[@field='display.half']")
                )

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
                    f"generated_xml/{theme}/status_screen_gen.h", header_selector
                )
                self.assertIn(
                    f"generated_xml/{theme}/status_screen_gen.c", source_selector
                )

    def test_ui_screens_validate_and_embed_assets_without_background(self):
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
        self.assertIn("ZMK_NVP_XML_HAS_BACKGROUND 0", header)
        self.assertRegex(header, r"ZMK_NVP_SVG_VISIBLE_ASSET_COUNT [1-9]")
        self.assertNotIn("zmk_nvp_svg_background", source)
        self.assertIn("zmk_nvp_svg_visible_assets", source)
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
