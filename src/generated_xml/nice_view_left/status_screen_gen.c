#include "status_screen_gen.h"
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include <lvgl.h>

static const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST uint8_t
    zmk_nvp_svg_visible_0_data[] = {
#if CONFIG_NICE_VIEW_WIDGET_INVERTED && !CONFIG_ZMK_SVG_WHITE_BACKGROUND
    0x00, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,
    0x00, 0x00, 0x00, 0xff, 0x00, 0x00, 0x00, 0x00,
#else
    0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00, 0xff,
    0xff, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00,
#endif
    0x01, 0x50, 0x05, 0x40, 0x05, 0x40, 0x15, 0x00, 0x01, 0x50, 0x05, 0x40, 0x05, 0x00, 0x04, 0x00,
    0x00, 0x00,
};
static const lv_image_dsc_t zmk_nvp_svg_visible_0 = {
    .header = {
        .magic = LV_IMAGE_HEADER_MAGIC,
        .cf = LV_COLOR_FORMAT_I2,
        .w = 7,
        .h = 9,
        .stride = 2,
    },
    .data_size = sizeof(zmk_nvp_svg_visible_0_data),
    .data = zmk_nvp_svg_visible_0_data,
};

static const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST uint8_t
    zmk_nvp_svg_visible_1_data[] = {
#if CONFIG_NICE_VIEW_WIDGET_INVERTED && !CONFIG_ZMK_SVG_WHITE_BACKGROUND
    0x00, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,
    0x00, 0x00, 0x00, 0xff, 0x00, 0x00, 0x00, 0x00,
#else
    0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00, 0xff,
    0xff, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00,
#endif
    0x01, 0x50, 0x05, 0x40, 0x05, 0x40, 0x15, 0x00, 0x01, 0x50, 0x05, 0x40, 0x05, 0x00, 0x04, 0x00,
    0x00, 0x00,
};
static const lv_image_dsc_t zmk_nvp_svg_visible_1 = {
    .header = {
        .magic = LV_IMAGE_HEADER_MAGIC,
        .cf = LV_COLOR_FORMAT_I2,
        .w = 7,
        .h = 9,
        .stride = 2,
    },
    .data_size = sizeof(zmk_nvp_svg_visible_1_data),
    .data = zmk_nvp_svg_visible_1_data,
};

static const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST uint8_t
    zmk_nvp_svg_visible_2_data[] = {
#if CONFIG_NICE_VIEW_WIDGET_INVERTED && !CONFIG_ZMK_SVG_WHITE_BACKGROUND
    0x00, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,
    0x00, 0x00, 0x00, 0xff, 0x00, 0x00, 0x00, 0x00,
#else
    0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00, 0xff,
    0xff, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00,
#endif
    0x15, 0x55, 0x55, 0x55, 0x50, 0x40, 0x00, 0x00, 0x00, 0x04, 0x40, 0x00, 0x00, 0x00, 0x04, 0x40,
    0x00, 0x00, 0x00, 0x04, 0x40, 0x00, 0x00, 0x00, 0x04, 0x40, 0x00, 0x00, 0x00, 0x04, 0x40, 0x00,
    0x00, 0x00, 0x04, 0x40, 0x00, 0x00, 0x00, 0x04, 0x40, 0x00, 0x00, 0x00, 0x04, 0x40, 0x00, 0x00,
    0x00, 0x04, 0x40, 0x00, 0x00, 0x00, 0x04, 0x40, 0x00, 0x00, 0x00, 0x04, 0x40, 0x00, 0x00, 0x00,
    0x04, 0x40, 0x00, 0x00, 0x00, 0x04, 0x15, 0x55, 0x55, 0x55, 0x50,
};
static const lv_image_dsc_t zmk_nvp_svg_visible_2 = {
    .header = {
        .magic = LV_IMAGE_HEADER_MAGIC,
        .cf = LV_COLOR_FORMAT_I2,
        .w = 19,
        .h = 15,
        .stride = 5,
    },
    .data_size = sizeof(zmk_nvp_svg_visible_2_data),
    .data = zmk_nvp_svg_visible_2_data,
};

const lv_image_dsc_t *const zmk_nvp_svg_visible_assets[] = {
    &zmk_nvp_svg_visible_0,
    &zmk_nvp_svg_visible_1,
    &zmk_nvp_svg_visible_2,
};

const struct zmk_nvp_svg_binding zmk_nvp_svg_bindings[] = {
    { "battery.left.percent", ZMK_NVP_SVG_RENDER_BAR, 3, 255, 6, 7, 12, 3, 0, 0, 0, 0, 0, "monospace", "start", "value", "", "", "", 0 },
    { "battery.left.percent", ZMK_NVP_SVG_RENDER_PERCENT, 3, 255, 35, 12, 0, 0, 0, 0, 0, 8, 0, "monospace", "start", "percent", "", "", "", 0 },
    { "battery.left.charge", ZMK_NVP_SVG_RENDER_VISIBLE, 3, 0, 57, 4, 7, 9, 0, 0, 0, 10, 0, "monospace", "start", "value", "", "", "charging", 0 },
    { "battery.right.percent", ZMK_NVP_SVG_RENDER_BAR, 3, 255, 6, 20, 12, 3, 0, 0, 0, 0, 0, "monospace", "start", "value", "", "", "", 0 },
    { "battery.right.percent", ZMK_NVP_SVG_RENDER_PERCENT, 3, 255, 35, 26, 0, 0, 0, 0, 0, 8, 0, "monospace", "start", "percent", "", "", "", 0 },
    { "battery.right.charge", ZMK_NVP_SVG_RENDER_VISIBLE, 3, 1, 57, 18, 7, 9, 0, 0, 0, 10, 0, "monospace", "start", "value", "", "", "charging", 0 },
    { "layer.index", ZMK_NVP_SVG_RENDER_TEXT, 3, 255, 155, 26, 0, 0, 0, 0, 0, 12, 0, "monospace", "end", "value", "", "", "", 0 },
    { "ble.active_profile", ZMK_NVP_SVG_RENDER_VISIBLE, 3, 2, 70, 37, 19, 15, 0, 0, 0, 10, 0, "monospace", "start", "value", "", "", "", 0 },
    { "ble.active_profile", ZMK_NVP_SVG_RENDER_TEXT, 3, 255, 80, 48, 0, 0, 0, 0, 0, 8, 0, "monospace", "middle", "profile-number", "", "", "", 0 },
    { "output.selected", ZMK_NVP_SVG_RENDER_TEXT, 3, 255, 4, 61, 0, 0, 0, 0, 0, 8, 0, "monospace", "start", "output-label", "", "", "", 0 },
    { "split.connected", ZMK_NVP_SVG_RENDER_VISIBLE, 3, 255, 147, 53, 24, 12, 0, 0, 0, 8, 0, "monospace", "start", "value", "+", "", "true", 0 },
    { "split.connected", ZMK_NVP_SVG_RENDER_VISIBLE, 3, 255, 147, 53, 24, 12, 0, 0, 0, 8, 0, "monospace", "start", "value", "-", "", "false", 0 },
};

static lv_color_t xml_foreground(void)
{
#if CONFIG_NICE_VIEW_WIDGET_INVERTED && !CONFIG_ZMK_SVG_WHITE_BACKGROUND
    return lv_color_white();
#else
    return lv_color_black();
#endif
}

void zmk_nvp_xml_layout_create(lv_obj_t *screen)
{
    if (screen == NULL) {
        return;
    }
    lv_obj_set_style_pad_all(screen, 0, LV_PART_MAIN);
    {
        lv_obj_t *label = lv_label_create(screen);
        lv_label_set_text(label, "L");
        lv_obj_set_style_text_font(label, &lv_font_unscii_8, LV_PART_MAIN);
        lv_obj_set_pos(label, 24, 4);
        lv_obj_set_style_text_color(label, xml_foreground(), LV_PART_MAIN);
    }
    {
        lv_obj_t *label = lv_label_create(screen);
        lv_label_set_text(label, "R");
        lv_obj_set_style_text_font(label, &lv_font_unscii_8, LV_PART_MAIN);
        lv_obj_set_pos(label, 24, 18);
        lv_obj_set_style_text_color(label, xml_foreground(), LV_PART_MAIN);
    }
    {
        lv_obj_t *label = lv_label_create(screen);
        lv_label_set_text(label, "LAYER");
        lv_obj_set_style_text_font(label, &lv_font_unscii_8, LV_PART_MAIN);
        lv_obj_set_pos(label, 98, 3);
        lv_obj_set_style_text_color(label, xml_foreground(), LV_PART_MAIN);
    }
    {
        lv_obj_t *label = lv_label_create(screen);
        lv_label_set_text(label, "LINK");
        lv_obj_set_style_text_font(label, &lv_font_unscii_8, LV_PART_MAIN);
        lv_obj_set_pos(label, 104, 53);
        lv_obj_set_style_text_color(label, xml_foreground(), LV_PART_MAIN);
    }
}
