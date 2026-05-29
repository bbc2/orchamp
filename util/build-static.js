// Assembles the generated (never-committed) src/orchamp_web/static/ dir: our
// browser JS bundled + minified, plus vendored libs and assets copied verbatim.
import { copyFileSync, mkdirSync, rmSync } from "node:fs";

const OUT = "src/orchamp_web/static";

const FONTS = [
  ["ibm-plex-sans", "ibm-plex-sans-latin-400-normal"],
  ["ibm-plex-sans", "ibm-plex-sans-latin-600-normal"],
  ["ibm-plex-sans", "ibm-plex-sans-latin-700-normal"],
  ["ibm-plex-mono", "ibm-plex-mono-latin-600-normal"],
];

// Start from a clean output directory.
rmSync(OUT, { recursive: true, force: true });
mkdirSync(`${OUT}/fonts`, { recursive: true });

// Bundle + minify our browser scripts. Stable output name (no content hash) so
// templates can hard-code /static/assumptions.js. The script has no imports, so
// the ESM output (the only format Bun.build emits) works as a classic <script>.
const result = await Bun.build({
  entrypoints: ["assets/assumptions.js"],
  outdir: OUT,
  minify: true,
  naming: "[name].[ext]",
});

if (!result.success) {
  for (const message of result.logs) console.error(message);
  process.exit(1);
}

// Copy vendored libraries and static passthrough assets verbatim.
const copies = [
  ["node_modules/htmx.org/dist/htmx.min.js", `${OUT}/htmx.min.js`],
  ["assets/favicon.svg", `${OUT}/favicon.svg`],
];

for (const [pkg, name] of FONTS) {
  copies.push([
    `node_modules/@fontsource/${pkg}/files/${name}.woff2`,
    `${OUT}/fonts/${name}.woff2`,
  ]);
}

for (const [src, dest] of copies) {
  try {
    copyFileSync(src, dest);
  } catch (err) {
    console.error(
      `build:static: failed to copy ${src} → ${dest}: ${err.message}`,
    );
    process.exit(1);
  }
}

console.log(
  `build:static: bundled assumptions.js, copied ${copies.length} assets`,
);
