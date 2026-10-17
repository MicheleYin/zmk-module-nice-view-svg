/*
 * Copyright (c) 2026 The ZMK Contributors
 *
 * SPDX-License-Identifier: MIT
 */

#include <errno.h>
#include <string.h>

#include <zephyr/settings/settings.h>
#include <zephyr/sys/util.h>

#include <zmk_nice_view_plus/layout.h>

static const struct zmk_nice_view_plus_layout default_layout = {
    .version = ZMK_NICE_VIEW_PLUS_LAYOUT_VERSION,
    .widgets = {{0, 1}, {1, 1}, {2, 1}, {3, 1}, {4, 1}},
};

static struct zmk_nice_view_plus_layout current_layout = {
    .version = ZMK_NICE_VIEW_PLUS_LAYOUT_VERSION,
    .widgets = {{0, 1}, {1, 1}, {2, 1}, {3, 1}, {4, 1}},
};

bool zmk_nice_view_plus_layout_is_valid(const struct zmk_nice_view_plus_layout *layout) {
    if (!layout || layout->version != ZMK_NICE_VIEW_PLUS_LAYOUT_VERSION) {
        return false;
    }

    uint8_t used_slots = 0;
    for (size_t i = 0; i < ARRAY_SIZE(layout->widgets); i++) {
        const struct zmk_nice_view_plus_widget_layout *widget = &layout->widgets[i];
        if (widget->slot >= ZMK_NICE_VIEW_PLUS_WIDGET_COUNT || widget->visible > 1) {
            return false;
        }
        if (widget->visible && (used_slots & BIT(widget->slot))) {
            return false;
        }
        if (widget->visible) {
            used_slots |= BIT(widget->slot);
        }
    }

    return true;
}

void zmk_nice_view_plus_layout_get(struct zmk_nice_view_plus_layout *layout) {
    if (layout) {
        *layout = current_layout;
    }
}

int zmk_nice_view_plus_layout_set(const struct zmk_nice_view_plus_layout *layout, bool save) {
    if (!zmk_nice_view_plus_layout_is_valid(layout)) {
        return -EINVAL;
    }

    current_layout = *layout;
    if (save) {
        return settings_save_one("nice_view_plus/layout", &current_layout, sizeof(current_layout));
    }

    return 0;
}

int zmk_nice_view_plus_layout_reset(bool save) {
    return zmk_nice_view_plus_layout_set(&default_layout, save);
}

static int nice_view_plus_settings_set(const char *name, size_t len, settings_read_cb read_cb,
                                       void *cb_arg) {
    const char *next;
    if (!settings_name_steq(name, "layout", &next) || next) {
        return -ENOENT;
    }
    if (len != sizeof(current_layout)) {
        return -EINVAL;
    }

    struct zmk_nice_view_plus_layout loaded;
    int rc = read_cb(cb_arg, &loaded, sizeof(loaded));
    if (rc < 0) {
        return rc;
    }
    if (rc != sizeof(loaded) || !zmk_nice_view_plus_layout_is_valid(&loaded)) {
        return -EINVAL;
    }

    current_layout = loaded;
    return 0;
}

SETTINGS_STATIC_HANDLER_DEFINE(nice_view_plus, "nice_view_plus", NULL,
                               nice_view_plus_settings_set, NULL, NULL);
