#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "lvgl.h"
#include "src/others/xml/lv_xml.h"
#include "src/others/xml/lv_xml_component.h"

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#define PREVIEW_EXPORT EMSCRIPTEN_KEEPALIVE
#else
#define PREVIEW_EXPORT
#endif

static uint8_t *framebuffer;
static int preview_width;
static int preview_height;
static lv_display_t *preview_display;
static lv_obj_t *preview_view;

PREVIEW_EXPORT int render_xml(const char *xml);
PREVIEW_EXPORT int set_preview_size(int width, int height);

static void flush_display(lv_display_t *display, const lv_area_t *area, uint8_t *pixels) {
    (void)area;
    (void)pixels;
    lv_display_flush_ready(display);
}

int main(void) {
    lv_init();
    lv_xml_init();
    return 0;
}

PREVIEW_EXPORT uint8_t *get_framebuffer(void) { return framebuffer; }

PREVIEW_EXPORT int get_width(void) { return preview_width; }

PREVIEW_EXPORT int get_height(void) { return preview_height; }

PREVIEW_EXPORT int set_preview_size(int width, int height) {
    if (width <= 0 || height <= 0 || width > 1024 || height > 1024) {
        return 0;
    }
    if (width == preview_width && height == preview_height && preview_display != NULL) {
        return 1;
    }

    if (preview_view != NULL) {
        lv_obj_delete(preview_view);
        preview_view = NULL;
    }
    if (preview_display != NULL) {
        lv_display_delete(preview_display);
        preview_display = NULL;
    }
    free(framebuffer);
    framebuffer = calloc((size_t)width * height, 4);
    if (framebuffer == NULL) {
        preview_width = 0;
        preview_height = 0;
        return 0;
    }

    preview_width = width;
    preview_height = height;
    preview_display = lv_display_create(width, height);
    if (preview_display == NULL) {
        free(framebuffer);
        framebuffer = NULL;
        preview_width = 0;
        preview_height = 0;
        return 0;
    }
    lv_display_set_color_format(preview_display, LV_COLOR_FORMAT_ARGB8888);
    lv_display_set_flush_cb(preview_display, flush_display);
    lv_display_set_buffers(preview_display, framebuffer, NULL, (uint32_t)width * height * 4,
                           LV_DISPLAY_RENDER_MODE_FULL);
    lv_obj_set_style_bg_color(lv_screen_active(), lv_color_white(), 0);
    lv_obj_set_style_bg_opa(lv_screen_active(), LV_OPA_COVER, 0);
    memset(framebuffer, 255, (size_t)width * height * 4);
    return 1;
}

PREVIEW_EXPORT int render_xml(const char *xml) {
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
