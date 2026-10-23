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
  const previewDir = path.join(__dirname, "build", "web");
  const modulePath = path.join(previewDir, "preview.js");
  if (!fs.existsSync(modulePath)) {
    process.stderr.write("build the wasm preview first: emcmake cmake ...\n");
    process.exit(1);
  }
  const CreateLVGLModule = require(modulePath);
  const module = await CreateLVGLModule();
  const width = Number(widthText || module._get_width());
  const height = Number(heightText || module._get_height());
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
  const rgba = Buffer.from(module.HEAPU8.subarray(offset, offset + width * height * 4));
  const { PNG } = require("pngjs");
  const png = new PNG({ width, height });
  for (let index = 0; index < width * height; index++) {
    const source = index * 4;
    const value =
      rgba[source] < 128 && rgba[source + 1] < 128 && rgba[source + 2] < 128 ? 0 : 255;
    const target = index * 4;
    png.data[target] = value;
    png.data[target + 1] = value;
    png.data[target + 2] = value;
    png.data[target + 3] = 255;
  }
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, PNG.sync.write(png));
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
