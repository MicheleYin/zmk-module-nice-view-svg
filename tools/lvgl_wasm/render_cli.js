#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

async function main() {
  const [xmlPath, outputPath, widthText, heightText] = process.argv.slice(2);
  if (!xmlPath || !outputPath) {
    process.stderr.write("usage: render_cli.js <xml> <png> [width] [height]\n");
    process.exit(2);
  }
  const xml = fs.readFileSync(xmlPath, "utf8");
  const previewDir = path.join(__dirname, "..", "..", "build", "lvgl_wasm", "web");
  const modulePath = path.join(previewDir, "preview.js");
  if (!fs.existsSync(modulePath)) {
    process.stderr.write("build the wasm preview first: emcmake cmake ...\n");
    process.exit(1);
  }
  const CreateLVGLModule = require(modulePath);
  const module = await CreateLVGLModule();
  const width = Number(widthText || module._get_width());
  const height = Number(heightText || module._get_height());
  if (!module._set_preview_size(width, height)) {
    throw new Error(`invalid preview dimensions: ${width}x${height}`);
  }
  const encoded = Buffer.from(`${xml}\0`, "utf8");
  const pointer = module._malloc(encoded.length);
  module.HEAPU8.set(encoded, pointer);
  const ok = module._render_xml(pointer);
  module._free(pointer);
  if (!ok) {
    process.stderr.write("LVGL rejected the component XML\n");
    process.exit(1);
  }
  const offset = module._get_framebuffer();
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(
    outputPath,
    Buffer.from(module.HEAPU8.slice(offset, offset + width * height * 4)),
  );
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
