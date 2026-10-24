#pragma once
#include <lvgl.h>
#include <stdint.h>

#ifndef LV_ATTRIBUTE_MEM_ALIGN
#define LV_ATTRIBUTE_MEM_ALIGN
#endif
#ifndef LV_ATTRIBUTE_LARGE_CONST
#define LV_ATTRIBUTE_LARGE_CONST
#endif

#define ZMK_NVP_SVG_WIDTH 128
#define ZMK_NVP_SVG_HEIGHT 32
#define ZMK_NVP_SVG_BINDING_COUNT 8
#define ZMK_NVP_SVG_VISIBLE_ASSET_COUNT 0
#define ZMK_NVP_SVG_ANIMATION_COUNT 0
#define ZMK_NVP_XML_HAS_BACKGROUND 0

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

struct zmk_nvp_svg_animation {
    const lv_image_dsc_t *const *frames;
    const uint32_t *durations_ms;
    uint16_t frame_count;
    uint32_t repeat_count;
};

extern const struct zmk_nvp_svg_binding zmk_nvp_svg_bindings[8];
extern const lv_image_dsc_t *const zmk_nvp_svg_visible_assets[];
extern const uint8_t zmk_nvp_svg_visible_animation_indices[];
extern const struct zmk_nvp_svg_animation zmk_nvp_svg_animations[1];
lv_obj_t *zmk_nvp_xml_animation_create(
    lv_obj_t *parent, const struct zmk_nvp_svg_animation *animation,
    int16_t x, int16_t y, bool initially_paused);
void zmk_nvp_xml_animation_attach(
    lv_obj_t *image, const struct zmk_nvp_svg_animation *animation,
    bool initially_paused);
void zmk_nvp_xml_animation_set_paused(lv_obj_t *image, bool paused);
void zmk_nvp_xml_layout_create(lv_obj_t *screen);
