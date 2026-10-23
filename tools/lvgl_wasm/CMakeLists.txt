cmake_minimum_required(VERSION 3.20)
project(zmk_lvgl_wasm_preview C)

include(FetchContent)

set(LV_CONF_INCLUDE_SIMPLE ON CACHE BOOL "Use the local LVGL configuration" FORCE)
set(LV_CONF_BUILD_DISABLE_EXAMPLES ON CACHE BOOL "" FORCE)
set(LV_CONF_BUILD_DISABLE_DEMOS ON CACHE BOOL "" FORCE)

FetchContent_Declare(
    lvgl
    GIT_REPOSITORY https://github.com/zmkfirmware/lvgl.git
    GIT_TAG f1db87ee98f1810328a8419572fa42a3b5f352ae
    GIT_SHALLOW FALSE
)
FetchContent_MakeAvailable(lvgl)

target_include_directories(lvgl PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")

add_executable(lvgl_preview main.c)
target_link_libraries(lvgl_preview PRIVATE lvgl)
target_compile_features(lvgl_preview PRIVATE c_std_11)

set(WEB_OUTPUT_DIR "${CMAKE_BINARY_DIR}/web")
set_target_properties(lvgl_preview PROPERTIES
    OUTPUT_NAME preview
    RUNTIME_OUTPUT_DIRECTORY "${WEB_OUTPUT_DIR}"
)
file(MAKE_DIRECTORY "${WEB_OUTPUT_DIR}")
configure_file(index.html "${WEB_OUTPUT_DIR}/index.html" COPYONLY)

if(EMSCRIPTEN)
    target_link_options(lvgl_preview PRIVATE
        "-sALLOW_MEMORY_GROWTH=1"
        "-sENVIRONMENT=web,node"
        "-sEXPORTED_FUNCTIONS=['_main','_malloc','_free','_render_xml','_set_preview_size','_get_framebuffer','_get_width','_get_height']"
        "-sEXPORTED_RUNTIME_METHODS=['HEAPU8']"
        "-sMODULARIZE=1"
        "-sEXPORT_NAME=CreateLVGLModule"
    )
    set_target_properties(lvgl_preview PROPERTIES SUFFIX ".js")
endif()