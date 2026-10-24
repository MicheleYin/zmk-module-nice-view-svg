#include "status_screen_gen.h"
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include <lvgl.h>

const lv_image_dsc_t *const zmk_nvp_svg_visible_assets[] = {
    0,
};

const uint8_t zmk_nvp_svg_visible_animation_indices[] = {
    255,
};

const struct zmk_nvp_svg_animation zmk_nvp_svg_animations[] = {
    { 0 },
};

const struct zmk_nvp_svg_binding zmk_nvp_svg_bindings[] = {
    { "battery.left.percent", ZMK_NVP_SVG_RENDER_PERCENT, 3, 255, 14, 11, 0, 0, 0, 0, 0, 8, 0, "monospace", "start", "percent", "", "", "", 0 },
    { "battery.left.percent", ZMK_NVP_SVG_RENDER_BAR, 3, 255, 38, 6, 18, 3, 0, 0, 0, 0, 0, "monospace", "start", "value", "", "", "", 0 },
    { "battery.right.percent", ZMK_NVP_SVG_RENDER_PERCENT, 3, 255, 78, 11, 0, 0, 0, 0, 0, 8, 0, "monospace", "start", "percent", "", "", "", 0 },
    { "battery.right.percent", ZMK_NVP_SVG_RENDER_BAR, 3, 255, 102, 6, 18, 3, 0, 0, 0, 0, 0, "monospace", "start", "value", "", "", "", 0 },
    { "display.half", ZMK_NVP_SVG_RENDER_VISIBLE, 3, 255, 122, 2, 24, 12, 0, 0, 0, 8, 0, "monospace", "start", "value", "L", "", "left", 0 },
    { "display.half", ZMK_NVP_SVG_RENDER_VISIBLE, 3, 255, 122, 2, 24, 12, 0, 0, 0, 8, 0, "monospace", "start", "value", "R", "", "right", 0 },
    { "output.selected", ZMK_NVP_SVG_RENDER_TEXT, 3, 255, 4, 26, 0, 0, 0, 0, 0, 8, 0, "monospace", "start", "output-label", "", "", "", 0 },
    { "layer.index", ZMK_NVP_SVG_RENDER_TEXT, 3, 255, 122, 26, 0, 0, 0, 0, 0, 12, 0, "monospace", "end", "value", "", "", "", 0 },
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
        lv_obj_set_style_text_font(label, &lv_font_montserrat_8, LV_PART_MAIN);
        lv_obj_set_pos(label, 4, 2);
        lv_obj_set_style_text_color(label, xml_foreground(), LV_PART_MAIN);
    }
    {
        lv_obj_t *label = lv_label_create(screen);
        lv_label_set_text(label, "R");
        lv_obj_set_style_text_font(label, &lv_font_montserrat_8, LV_PART_MAIN);
        lv_obj_set_pos(label, 68, 2);
        lv_obj_set_style_text_color(label, xml_foreground(), LV_PART_MAIN);
    }
    {
        lv_obj_t *label = lv_label_create(screen);
        lv_label_set_text(label, "LAYER");
        lv_obj_set_style_text_font(label, &lv_font_montserrat_8, LV_PART_MAIN);
        lv_obj_set_pos(label, 60, 17);
        lv_obj_set_style_text_color(label, xml_foreground(), LV_PART_MAIN);
    }
}
