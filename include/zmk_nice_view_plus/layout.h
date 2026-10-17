/*
 * Copyright (c) 2026 The ZMK Contributors
 *
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <stdbool.h>
#include <stdint.h>

#define ZMK_NICE_VIEW_PLUS_LAYOUT_VERSION 2
#define ZMK_NICE_VIEW_PLUS_WIDGET_COUNT 5

enum zmk_nice_view_plus_widget_id {
    ZMK_NICE_VIEW_PLUS_WIDGET_BATTERY,
    ZMK_NICE_VIEW_PLUS_WIDGET_OUTPUT,
    ZMK_NICE_VIEW_PLUS_WIDGET_PROFILES,
    ZMK_NICE_VIEW_PLUS_WIDGET_LAYER,
    ZMK_NICE_VIEW_PLUS_WIDGET_SPLIT,
};

struct zmk_nice_view_plus_widget_layout {
    uint8_t slot;
    uint8_t visible;
};

struct zmk_nice_view_plus_layout {
    uint8_t version;
    struct zmk_nice_view_plus_widget_layout widgets[ZMK_NICE_VIEW_PLUS_WIDGET_COUNT];
};

void zmk_nice_view_plus_layout_get(struct zmk_nice_view_plus_layout *layout);
int zmk_nice_view_plus_layout_set(const struct zmk_nice_view_plus_layout *layout, bool save);
int zmk_nice_view_plus_layout_reset(bool save);
bool zmk_nice_view_plus_layout_is_valid(const struct zmk_nice_view_plus_layout *layout);
