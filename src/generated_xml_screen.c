#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/sys/util.h>

#if IS_ENABLED(CONFIG_ZMK_SVG_THEME_LEFT)
#include "generated_xml/nice_view_left/status_screen_gen.c"
#elif IS_ENABLED(CONFIG_ZMK_SVG_THEME_RIGHT)
#include "generated_xml/nice_view_right/status_screen_gen.c"
#elif DT_PROP(DT_CHOSEN(zephyr_display), width) == 128 &&                              \
    DT_PROP(DT_CHOSEN(zephyr_display), height) == 32
#if IS_ENABLED(CONFIG_ZMK_SVG_RIGHT_HALF)
#include "generated_xml/oled_right/status_screen_gen.c"
#else
#include "generated_xml/oled_left/status_screen_gen.c"
#endif
#elif DT_PROP(DT_CHOSEN(zephyr_display), width) == 160 &&                              \
    DT_PROP(DT_CHOSEN(zephyr_display), height) == 68
#if IS_ENABLED(CONFIG_ZMK_SVG_RIGHT_HALF)
#include "generated_xml/nice_view_right/status_screen_gen.c"
#else
#include "generated_xml/nice_view_left/status_screen_gen.c"
#endif
#else
#error "Automatic LVGL XML theme supports 160x68 and 128x32 displays"
#endif