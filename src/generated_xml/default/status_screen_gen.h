#pragma once
#include <lvgl.h>
#include <stdint.h>

#define ZMK_NVP_SVG_WIDTH 160
#define ZMK_NVP_SVG_HEIGHT 68
#define ZMK_NVP_SVG_BINDING_COUNT 19
#define ZMK_NVP_SVG_VISIBLE_ASSET_COUNT 0
#define ZMK_NVP_XML_HAS_BACKGROUND 1

enum zmk_nvp_svg_renderer {
    ZMK_NVP_SVG_RENDER_BAR = 0,
    ZMK_NVP_SVG_RENDER_PERCENT = 1,
    ZMK_NVP_SVG_RENDER_RING = 2,
    ZMK_NVP_SVG_RENDER_TEXT = 3,
    ZMK_NVP_SVG_RENDER_VISIBLE = 4,
};

struct zmk_nvp_svg_binding {
    const char *field_id;
    uint8_t renderer;
    uint8_t roles;
    uint8_t asset_index;
    int16_t x, y, width, height;
    int16_t ring_radius;
    uint8_t ring_width;
    uint8_t ring_rounded;
    uint8_t font_size;
    uint8_t color;
    const char *font_family;
    const char *anchor;
    const char *format;
    const char *prefix;
    const char *suffix;
    const char *when;
    uint8_t match_bit;
};

extern const struct zmk_nvp_svg_binding zmk_nvp_svg_bindings[19];
void zmk_nvp_xml_layout_create(lv_obj_t *screen);
