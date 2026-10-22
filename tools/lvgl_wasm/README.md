# LVGL XML WebAssembly preview

This minimal preview renders LVGL component XML using the exact LVGL commit
pinned by the module's ZMK West manifest. It is a runtime harness, not yet a
preview for the module's typed `zmk_status_*` widgets.

Install CMake and the Emscripten SDK, then activate the SDK environment and run:

```sh
emcmake cmake -S tools/lvgl_wasm -B build/lvgl_wasm
cmake --build build/lvgl_wasm
```

Serve `build/lvgl_wasm/web` over HTTP and open `index.html`. The browser page
keeps the previous render when LVGL rejects an update. LVGL source is fetched
at configure time and pinned to commit `f1db87ee98f1810328a8419572fa42a3b5f352ae`.