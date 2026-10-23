/*
 * Copyright (c) 2026 The ZMK Contributors
 *
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <stdbool.h>
#include <stdint.h>

#include <lvgl.h>

#include <zmk/battery.h>

struct zmk_nvp_screen_state {
    uint8_t central_battery_level;
    enum zmk_battery_charge_state central_charge_state;
    uint8_t peripheral_battery_level;
    enum zmk_battery_charge_state peripheral_charge_state;
    uint8_t active_layer;
    uint8_t output;
    uint8_t active_ble_profile;
    uint8_t connected_ble_profiles;
    uint8_t bonded_ble_profiles;
    uint8_t ble_profile_count;
    uint8_t wpm_current;
    bool has_remote_status;
    bool split_connected;
};

lv_obj_t *zmk_nvp_xml_screen_create(void);
void zmk_nvp_xml_screen_update(const struct zmk_nvp_screen_state *state);
