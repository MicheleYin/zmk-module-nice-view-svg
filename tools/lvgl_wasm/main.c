#include <stdint.h>
#include <stdlib.h>

#include "lvgl.h"
#include "src/others/xml/lv_xml.h"
#include "src/others/xml/lv_xml_component.h"

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#define PREVIEW_EXPORT EMSCRIPTEN_KEEPALIVE
#else
#define PREVIEW_EXPORT
#endif

enum {
    PREVIEW_WIDTH = 160,
    PREVIEW_HEIGHT = 68,
};

static uint8_t framebuffer[PREVIEW_WIDTH * PREVIEW_HEIGHT * 4];
static lv_display_t *preview_display;
static lv_obj_t *preview_view;
static const char initial_xml[] =
    "<component><view extends=\"lv_obj\" width=\"160\" height=\"68\">"
    "<lv_label text=\"LVGL XML preview\" x=\"5\" y=\"5\"/>"
    "</view></component>";

PREVIEW_EXPORT int render_xml(const char *xml);

static void flush_display(lv_display_t *display, const lv_area_t *area, uint8_t *pixels)
{
    int32_t width = lv_area_get_width(area);
    int32_t height = lv_area_get_height(area);
    const lv_color_t *source = (const lv_color_t *)pixels;

    for (int32_t y = 0; y < height; y++) {
        for (int32_t x = 0; x < width; x++) {
            uint32_t color = lv_color_to_u32(source[y * width + x]);
            uint32_t offset = ((area->y1 + y) * PREVIEW_WIDTH + area->x1 + x) * 4;
            framebuffer[offset] = (uint8_t)(color >> 16);
            framebuffer[offset + 1] = (uint8_t)(color >> 8);
            framebuffer[offset + 2] = (uint8_t)color;
            framebuffer[offset + 3] = 255;
        }
    }

    lv_display_flush_ready(display);
}

int main(void)
{
    lv_init();
    lv_xml_init();

    preview_display = lv_display_create(PREVIEW_WIDTH, PREVIEW_HEIGHT);
    if (preview_display == NULL) {
        return 1;
    }

    lv_display_set_color_format(preview_display, LV_COLOR_FORMAT_XRGB8888);
    lv_display_set_flush_cb(preview_display, flush_display);
    lv_display_set_buffers(preview_display, framebuffer, NULL, sizeof(framebuffer),
                           LV_DISPLAY_RENDER_MODE_FULL);
    lv_obj_set_style_bg_color(lv_screen_active(), lv_color_black(), 0);
    lv_obj_set_style_bg_opa(lv_screen_active(), LV_OPA_COVER, 0);
    if (!render_xml(initial_xml)) {
        return 1;
    }
    lv_refr_now(preview_display);

    return 0;
}

PREVIEW_EXPORT uint8_t *get_framebuffer(void)
{
    return framebuffer;
}

PREVIEW_EXPORT int get_width(void)
{
    return PREVIEW_WIDTH;
}

PREVIEW_EXPORT int get_height(void)
{
    return PREVIEW_HEIGHT;
}

PREVIEW_EXPORT int render_xml(const char *xml)
{
    if (xml == NULL || preview_display == NULL) {
        return 0;
    }

    lv_xml_component_unregister("Preview");
    if (lv_xml_component_register_from_data("Preview", xml) != LV_RESULT_OK) {
        return 0;
    }

    lv_obj_t *next_view = lv_xml_create(lv_screen_active(), "Preview", NULL);
    if (next_view == NULL) {
        lv_xml_component_unregister("Preview");
        return 0;
    }

    if (preview_view != NULL) {
        lv_obj_delete(preview_view);
    }
    preview_view = next_view;
    lv_refr_now(preview_display);
    return 1;
}