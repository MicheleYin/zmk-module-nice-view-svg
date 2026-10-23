cmake_minimum_required(VERSION 3.20)
project(zmk_xml_preview_host C)

if(NOT DEFINED LVGL_DIR)
  message(
    STATUS
      "LVGL_DIR not set; skipping native SDL preview target. "
      "Use tools/xml_preview_host/render_png.py instead.")
  return()
endif()

message(FATAL_ERROR
  "Native SDL preview is not wired in this repository yet. "
  "Set up LVGL with LV_USE_XML and LV_USE_SDL locally, or use render_png.py.")
