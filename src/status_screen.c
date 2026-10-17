/*
 * Copyright (c) 2026 The ZMK Contributors
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdio.h>

#include <zephyr/kernel.h>
#include <zephyr/init.h>

#include <lvgl.h>

#include <zmk/battery.h>
#include <zmk/ble.h>
#include <zmk/display.h>
#include <zmk/endpoints.h>
#include <zmk/event_manager.h>
#include <zmk/events/battery_state_changed.h>
#include <zmk/events/ble_active_profile_changed.h>
#include <zmk/events/ble_profile_connection_changed.h>
#include <zmk/events/endpoint_changed.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/events/usb_conn_state_changed.h>
#if IS_ENABLED(CONFIG_ZMK_WPM)
#include <zmk/events/wpm_state_changed.h>
#endif
#include <zmk/keymap.h>
#include <zmk/stdlib.h>
#include <zmk/split/bluetooth/status.h>
#include <zmk_nice_view_plus/layout.h>
#include "svg_screen.h"

#if IS_ENABLED(CONFIG_ZMK_SPLIT) && !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
#include <zmk/events/split_peripheral_status_changed.h>
#endif

#define MAX_BLE_PROFILES 8

#if IS_ENABLED(CONFIG_ZMK_SPLIT) && !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
#include <zmk/split/bluetooth/peripheral.h>
#endif

static lv_obj_t *screen;
static struct zmk_nvp_screen_state state;

#if !IS_ENABLED(CONFIG_ZMK_NICE_VIEW_PLUS_SVG_SCREEN)
static lv_obj_t *widgets[ZMK_NICE_VIEW_PLUS_WIDGET_COUNT];
static lv_obj_t *battery_fills[2];
static lv_obj_t *battery_texts[2];
static lv_obj_t *battery_charge_icons[2];
static lv_obj_t *output_text;
static lv_obj_t *output_indicator;
static lv_obj_t *profile_widget;
static lv_obj_t *profile_boxes[MAX_BLE_PROFILES];
static lv_obj_t *profile_labels[MAX_BLE_PROFILES];
static uint8_t profile_box_count;
static lv_obj_t *layer_text;

static lv_color_t foreground_color(void) {
    return IS_ENABLED(CONFIG_NICE_VIEW_WIDGET_INVERTED) ? lv_color_white() : lv_color_black();
}

static lv_color_t background_color(void) {
    return IS_ENABLED(CONFIG_NICE_VIEW_WIDGET_INVERTED) ? lv_color_black() : lv_color_white();
}

static lv_obj_t *create_group(lv_obj_t *parent, lv_coord_t x, lv_coord_t y, lv_coord_t width,
                              lv_coord_t height) {
    lv_obj_t *group = lv_obj_create(parent);
    lv_obj_set_pos(group, x, y);
    lv_obj_set_size(group, width, height);
    lv_obj_set_style_bg_opa(group, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(group, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(group, 0, LV_PART_MAIN);
    lv_obj_clear_flag(group, LV_OBJ_FLAG_SCROLLABLE);
    return group;
}

static lv_obj_t *create_shape(lv_obj_t *parent, lv_coord_t x, lv_coord_t y, lv_coord_t width,
                              lv_coord_t height, bool filled, lv_coord_t border_width,
                              lv_coord_t radius) {
    lv_obj_t *shape = lv_obj_create(parent);
    lv_obj_set_pos(shape, x, y);
    lv_obj_set_size(shape, width, height);
    lv_obj_set_style_bg_color(shape, foreground_color(), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(shape, filled ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_color(shape, foreground_color(), LV_PART_MAIN);
    lv_obj_set_style_border_width(shape, border_width, LV_PART_MAIN);
    lv_obj_set_style_radius(shape, radius, LV_PART_MAIN);
    lv_obj_set_style_pad_all(shape, 0, LV_PART_MAIN);
    lv_obj_clear_flag(shape, LV_OBJ_FLAG_SCROLLABLE);
    return shape;
}

static lv_obj_t *create_label(lv_obj_t *parent, lv_coord_t x, lv_coord_t y, const lv_font_t *font,
                              lv_color_t color) {
    lv_obj_t *label = lv_label_create(parent);
    lv_obj_set_pos(label, x, y);
    lv_obj_set_style_text_color(label, color, LV_PART_MAIN);
    lv_obj_set_style_text_font(label, font, LV_PART_MAIN);
    return label;
}

static void update_profile_boxes(void) {
    uint8_t count = MIN(state.ble_profile_count, MAX_BLE_PROFILES);
    lv_coord_t button_width = count > 5 ? 13 : 18;
    lv_coord_t button_pitch = count > 5 ? 15 : 22;

    while (profile_box_count < count) {
        uint8_t profile = profile_box_count++;
        lv_coord_t x = 37 + profile * button_pitch;
        profile_boxes[profile] = create_shape(profile_widget, x, 1, button_width, 15, false, 1, 2);
        profile_labels[profile] =
            create_label(profile_widget, x, 1, &lv_font_unscii_8, foreground_color());
        lv_obj_set_size(profile_labels[profile], button_width, 15);
        lv_obj_set_style_text_align(profile_labels[profile], LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
        char number[2];
        snprintf(number, sizeof(number), "%u", profile + 1);
        lv_label_set_text(profile_labels[profile], number);
    }

    for (uint8_t profile = 0; profile < profile_box_count; profile++) {
        lv_obj_t *box = profile_boxes[profile];
        lv_obj_t *label = profile_labels[profile];
        bool visible = profile < count;
        lv_coord_t x = 37 + profile * button_pitch;

        lv_obj_set_pos(box, x, 1);
        lv_obj_set_size(box, button_width, 15);
        lv_obj_set_pos(label, x, 1);
        lv_obj_set_size(label, button_width, 15);
        if (!visible) {
            lv_obj_add_flag(box, LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(label, LV_OBJ_FLAG_HIDDEN);
            continue;
        }

        lv_obj_clear_flag(box, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(label, LV_OBJ_FLAG_HIDDEN);
        bool selected = state.active_ble_profile == profile;
        lv_obj_set_style_bg_opa(box, selected ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_MAIN);
        lv_obj_set_style_border_width(box, selected ? 0 : 1, LV_PART_MAIN);
        lv_obj_set_style_text_color(label, selected ? background_color() : foreground_color(),
                                    LV_PART_MAIN);
    }
}
#endif

static void render_status(struct k_work *work) {
    ARG_UNUSED(work);

#if IS_ENABLED(CONFIG_ZMK_NICE_VIEW_PLUS_SVG_SCREEN)
    zmk_nvp_svg_screen_update(&state);
#else

    char text[24];
    const uint8_t battery_levels[] = {state.central_battery_level, state.peripheral_battery_level};
    const enum zmk_battery_charge_state charge_states[] = {state.central_charge_state,
                                                           state.peripheral_charge_state};
    for (uint8_t battery = 0; battery < ARRAY_SIZE(battery_levels); battery++) {
        char name = battery == 0 ? 'C' : 'P';
        if (battery_levels[battery] <= 100) {
            snprintf(text, sizeof(text), "%c %u%%", name, battery_levels[battery]);
            lv_obj_set_width(battery_fills[battery], (18 * battery_levels[battery]) / 100);
            if (battery_levels[battery] == 0) {
                lv_obj_add_flag(battery_fills[battery], LV_OBJ_FLAG_HIDDEN);
            } else {
                lv_obj_clear_flag(battery_fills[battery], LV_OBJ_FLAG_HIDDEN);
            }
        } else {
            snprintf(text, sizeof(text), "%c --", name);
            lv_obj_add_flag(battery_fills[battery], LV_OBJ_FLAG_HIDDEN);
        }
        lv_label_set_text(battery_texts[battery], text);
        lv_label_set_text(
            battery_charge_icons[battery],
            charge_states[battery] == ZMK_BATTERY_CHARGE_STATE_CHARGING ? LV_SYMBOL_CHARGE : "");
    }

    bool output_connected = false;
#if IS_ENABLED(CONFIG_ZMK_SPLIT) && !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    if (!state.has_remote_status) {
        lv_label_set_text(output_text, "--");
    } else
#endif
    {
        switch (state.output) {
        case ZMK_SPLIT_BLE_STATUS_OUTPUT_USB:
            lv_label_set_text(output_text, "USB");
            output_connected = true;
            break;
        case ZMK_SPLIT_BLE_STATUS_OUTPUT_BLE:
            lv_label_set_text(output_text, "BLE");
            output_connected = state.active_ble_profile < 8 &&
                               (state.connected_ble_profiles & BIT(state.active_ble_profile));
            break;
        default:
            lv_label_set_text(output_text, "--");
            break;
        }
    }
    lv_obj_set_style_bg_opa(output_indicator, output_connected ? LV_OPA_COVER : LV_OPA_TRANSP,
                            LV_PART_MAIN);

    update_profile_boxes();

    snprintf(text, sizeof(text), "%u", state.active_layer);
    lv_label_set_text(layer_text, text);
#endif
}

K_WORK_DEFINE(render_status_work, render_status);

static void schedule_render(void) {
    if (screen) {
        k_work_submit_to_queue(zmk_display_work_q(), &render_status_work);
    }
}

static void set_remote_status(const struct zmk_split_ble_status *status) {
    if (!status || status->version != ZMK_SPLIT_BLE_STATUS_VERSION) {
        return;
    }

    state.active_layer = status->active_layer;
    state.output = status->output;
    state.active_ble_profile = status->active_ble_profile;
    state.wpm_current = status->words_per_minute;
    state.connected_ble_profiles = status->connected_ble_profiles;
    state.bonded_ble_profiles = status->bonded_ble_profiles;
    state.ble_profile_count = MIN(status->ble_profile_count, MAX_BLE_PROFILES);
    state.central_battery_level = status->central_battery_level;
    state.central_charge_state = status->central_charge_state;
    state.has_remote_status = true;
    schedule_render();
}

static int status_event_listener(const zmk_event_t *eh) {
    const struct zmk_battery_state_changed *battery = as_zmk_battery_state_changed(eh);
    if (battery) {
#if IS_ENABLED(CONFIG_ZMK_SPLIT) && !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
        state.peripheral_battery_level = battery->state_of_charge;
        state.peripheral_charge_state = battery->charge_state;
#else
        state.central_battery_level = battery->state_of_charge;
        state.central_charge_state = battery->charge_state;
#endif
    }
#if IS_ENABLED(CONFIG_ZMK_WPM)
    const struct zmk_wpm_state_changed *wpm = as_zmk_wpm_state_changed(eh);
    if (wpm) {
        state.wpm_current = MIN(wpm->state, UINT8_MAX);
    }
#endif

#if IS_ENABLED(CONFIG_ZMK_SPLIT) && !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    const struct zmk_split_peripheral_status_changed *split_status =
        as_zmk_split_peripheral_status_changed(eh);
    if (split_status) {
        state.split_connected = split_status->connected;
    }
#endif

#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL) &&                                                   \
    IS_ENABLED(CONFIG_ZMK_BATTERY_REPORTING_SPLIT_FETCHING)
    const struct zmk_peripheral_battery_state_changed *peripheral_battery =
        as_zmk_peripheral_battery_state_changed(eh);
    if (peripheral_battery && peripheral_battery->source == 0) {
        state.peripheral_battery_level = peripheral_battery->state_of_charge;
        state.peripheral_charge_state = peripheral_battery->charge_state;
    }
#endif

#if !IS_ENABLED(CONFIG_ZMK_SPLIT) || IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    if (as_zmk_layer_state_changed(eh)) {
        state.active_layer = zmk_keymap_highest_layer_active();
    } else if (as_zmk_endpoint_changed(eh) || as_zmk_ble_active_profile_changed(eh) ||
               as_zmk_ble_profile_connection_changed(eh)
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
               || as_zmk_usb_conn_state_changed(eh)
#endif
    ) {
        struct zmk_endpoint_instance endpoint = zmk_endpoint_get_selected();
        state.output = endpoint.transport == ZMK_TRANSPORT_USB   ? ZMK_SPLIT_BLE_STATUS_OUTPUT_USB
                       : endpoint.transport == ZMK_TRANSPORT_BLE ? ZMK_SPLIT_BLE_STATUS_OUTPUT_BLE
                                                                 : ZMK_SPLIT_BLE_STATUS_OUTPUT_NONE;
        int active_profile = zmk_ble_active_profile_index();
        state.active_ble_profile =
            active_profile >= 0 ? active_profile : ZMK_SPLIT_BLE_STATUS_NO_PROFILE;
        state.ble_profile_count = MIN(ZMK_BLE_PROFILE_COUNT, MAX_BLE_PROFILES);
        state.connected_ble_profiles = 0;
        state.bonded_ble_profiles = 0;
        for (uint8_t profile = 0; profile < MIN(ZMK_BLE_PROFILE_COUNT, MAX_BLE_PROFILES);
             profile++) {
            if (!zmk_ble_profile_is_open(profile)) {
                state.bonded_ble_profiles |= BIT(profile);
            }
            if (zmk_ble_profile_is_connected(profile)) {
                state.connected_ble_profiles |= BIT(profile);
            }
        }
    }
#endif

    schedule_render();
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(nice_view_plus_status, status_event_listener);
ZMK_SUBSCRIPTION(nice_view_plus_status, zmk_battery_state_changed);
#if IS_ENABLED(CONFIG_ZMK_SPLIT) && !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
ZMK_SUBSCRIPTION(nice_view_plus_status, zmk_split_peripheral_status_changed);
#endif
#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL) &&                                                   \
    IS_ENABLED(CONFIG_ZMK_BATTERY_REPORTING_SPLIT_FETCHING)
ZMK_SUBSCRIPTION(nice_view_plus_status, zmk_peripheral_battery_state_changed);
#endif
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
ZMK_SUBSCRIPTION(nice_view_plus_status, zmk_usb_conn_state_changed);
#endif
#if IS_ENABLED(CONFIG_ZMK_WPM)
ZMK_SUBSCRIPTION(nice_view_plus_status, zmk_wpm_state_changed);
#endif

#if !IS_ENABLED(CONFIG_ZMK_SPLIT) || IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
ZMK_SUBSCRIPTION(nice_view_plus_status, zmk_layer_state_changed);
ZMK_SUBSCRIPTION(nice_view_plus_status, zmk_endpoint_changed);
ZMK_SUBSCRIPTION(nice_view_plus_status, zmk_ble_active_profile_changed);
ZMK_SUBSCRIPTION(nice_view_plus_status, zmk_ble_profile_connection_changed);
#endif

lv_obj_t *zmk_display_status_screen(void) {
    state.central_battery_level = UINT8_MAX;
    state.peripheral_battery_level = UINT8_MAX;
    state.central_charge_state = ZMK_BATTERY_CHARGE_STATE_UNKNOWN;
    state.peripheral_charge_state = ZMK_BATTERY_CHARGE_STATE_UNKNOWN;
    state.active_ble_profile = ZMK_SPLIT_BLE_STATUS_NO_PROFILE;

#if !IS_ENABLED(CONFIG_ZMK_SPLIT) || IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    state.ble_profile_count = MIN(ZMK_BLE_PROFILE_COUNT, MAX_BLE_PROFILES);
#else
    state.ble_profile_count = 0;
#endif

#if IS_ENABLED(CONFIG_ZMK_NICE_VIEW_PLUS_SVG_SCREEN)
    screen = zmk_nvp_svg_screen_create();
#else
    screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(screen, background_color(), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(screen, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(screen, 0, LV_PART_MAIN);
    lv_obj_clear_flag(screen, LV_OBJ_FLAG_SCROLLABLE);

    create_shape(screen, 2, 33, 156, 1, true, 0, 0);
    create_shape(screen, 2, 55, 156, 1, true, 0, 0);

    static const lv_coord_t widget_positions[ZMK_NICE_VIEW_PLUS_WIDGET_COUNT][2] = {
        {0, 0}, {0, 56}, {0, 35}, {113, 2}, {88, 56},
    };
    static const lv_coord_t widget_sizes[ZMK_NICE_VIEW_PLUS_WIDGET_COUNT][2] = {
        {88, 30}, {80, 12}, {160, 18}, {45, 28}, {72, 12},
    };
    struct zmk_nice_view_plus_layout layout;
    zmk_nice_view_plus_layout_get(&layout);
    for (size_t i = 0; i < ARRAY_SIZE(widgets); i++) {
        uint8_t slot = layout.widgets[i].slot;
        widgets[i] = create_group(screen, widget_positions[slot][0], widget_positions[slot][1],
                                  widget_sizes[slot][0], widget_sizes[slot][1]);
        if (i == ZMK_NICE_VIEW_PLUS_WIDGET_BATTERY) {
            for (uint8_t battery = 0; battery < ARRAY_SIZE(battery_fills); battery++) {
                lv_coord_t outline_y = battery == 0 ? 3 : 18;
                lv_coord_t fill_y = battery == 0 ? 6 : 21;
                create_shape(widgets[i], 3, outline_y, 22, 10, false, 1, 1);
                create_shape(widgets[i], 26, outline_y + 3, 2, 5, true, 0, 0);
                battery_fills[battery] = create_shape(widgets[i], 6, fill_y, 18, 5, true, 0, 0);
                battery_texts[battery] = create_label(widgets[i], 32, outline_y - 2,
                                                      &lv_font_unscii_8, foreground_color());
                battery_charge_icons[battery] = create_label(
                    widgets[i], 9, outline_y - 2, &lv_font_montserrat_12, background_color());
            }
        } else if (i == ZMK_NICE_VIEW_PLUS_WIDGET_OUTPUT) {
            output_text = create_label(widgets[i], 4, 1, &lv_font_unscii_8, foreground_color());
            output_indicator = create_shape(widgets[i], 28, 3, 6, 6, false, 1, 3);
        } else if (i == ZMK_NICE_VIEW_PLUS_WIDGET_PROFILES) {
            lv_obj_t *ble_label =
                create_label(widgets[i], 4, 2, &lv_font_montserrat_8, foreground_color());
            lv_label_set_text(ble_label, "BLE");
            profile_widget = widgets[i];
        } else if (i == ZMK_NICE_VIEW_PLUS_WIDGET_LAYER) {
            create_shape(widgets[i], 0, 0, 43, 27, false, 1, 2);
            lv_obj_t *layer_label =
                create_label(widgets[i], 4, 1, &lv_font_montserrat_8, foreground_color());
            lv_label_set_text(layer_label, "LAYER");
            layer_text = create_label(widgets[i], 1, 6, &lv_font_montserrat_20, foreground_color());
            lv_obj_set_size(layer_text, 41, 21);
            lv_obj_set_style_text_align(layer_text, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
        } else {
            lv_obj_t *split_label =
                create_label(widgets[i], 0, 1, &lv_font_montserrat_8, foreground_color());
            lv_label_set_text(split_label, "SPLIT");
            bool right_half = IS_ENABLED(CONFIG_ZMK_NICE_VIEW_PLUS_RIGHT_HALF);
            create_shape(widgets[i], 37, 2, 14, 9, !right_half, 1, 1);
            create_shape(widgets[i], 55, 2, 14, 9, right_half, 1, 1);
            lv_obj_t *left = create_label(widgets[i], 37, 2, &lv_font_montserrat_8,
                                          right_half ? foreground_color() : background_color());
            lv_obj_set_size(left, 14, 9);
            lv_obj_set_style_text_align(left, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
            lv_obj_t *right = create_label(widgets[i], 55, 2, &lv_font_montserrat_8,
                                           right_half ? background_color() : foreground_color());
            lv_obj_set_size(right, 14, 9);
            lv_obj_set_style_text_align(right, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
            lv_label_set_text(left, "L");
            lv_label_set_text(right, "R");
        }

        if (!layout.widgets[i].visible) {
            lv_obj_add_flag(widgets[i], LV_OBJ_FLAG_HIDDEN);
        }
    }

#endif

#if IS_ENABLED(CONFIG_ZMK_SPLIT) && !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    state.split_connected = zmk_split_bt_peripheral_is_connected();
    state.peripheral_battery_level = zmk_battery_state_of_charge();
    state.peripheral_charge_state = zmk_battery_charge_state();
#else
    state.central_battery_level = zmk_battery_state_of_charge();
    state.central_charge_state = zmk_battery_charge_state();
#endif

#if !IS_ENABLED(CONFIG_ZMK_SPLIT) || IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    state.active_layer = zmk_keymap_highest_layer_active();
#else
#if IS_ENABLED(CONFIG_ZMK_SPLIT_BLE_STATUS_SYNC)
    zmk_split_ble_register_central_status_callback(set_remote_status);
#endif
#endif

#if !IS_ENABLED(CONFIG_ZMK_SPLIT) || IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    struct zmk_endpoint_instance endpoint = zmk_endpoint_get_selected();
    state.output = endpoint.transport == ZMK_TRANSPORT_USB   ? ZMK_SPLIT_BLE_STATUS_OUTPUT_USB
                   : endpoint.transport == ZMK_TRANSPORT_BLE ? ZMK_SPLIT_BLE_STATUS_OUTPUT_BLE
                                                             : ZMK_SPLIT_BLE_STATUS_OUTPUT_NONE;
    int active_profile = zmk_ble_active_profile_index();
    state.active_ble_profile =
        active_profile >= 0 ? active_profile : ZMK_SPLIT_BLE_STATUS_NO_PROFILE;
#endif
    schedule_render();
    return screen;
}
