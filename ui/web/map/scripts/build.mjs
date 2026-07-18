import {copyFile, mkdir} from "node:fs/promises";
import {fileURLToPath} from "node:url";

import {build} from "esbuild";

const mapRoot = new URL("../", import.meta.url);
const bundleDirectory = new URL("bundle/", mapRoot);

await mkdir(bundleDirectory, {recursive: true});
await build({
  entryPoints: [fileURLToPath(new URL("src/app.js", mapRoot))],
  outfile: fileURLToPath(new URL("map.js", bundleDirectory)),
  bundle: true,
  format: "iife",
  target: ["chrome120"],
  minify: true,
  sourcemap: false,
  legalComments: "external"
});
await copyFile(
  fileURLToPath(new URL("node_modules/maplibre-gl/dist/maplibre-gl.css", mapRoot)),
  fileURLToPath(new URL("maplibre-gl.css", bundleDirectory))
);
