/**
 * Generate the Tauri window-icon suite from the brand SVG.
 *
 * Steps:
 *   1. Rasterise apps/metis-web/public/brand/metis-mark.svg to a
 *      1024x1024 PNG with a #06080e rounded-square background. The
 *      mark is centred at 60 % of the canvas so it has breathing
 *      room; the rounded-square chrome matches Apple-style app
 *      icon conventions.
 *   2. Run `pnpm tauri icon` from apps/metis-desktop, which emits
 *      the standard 5-file icon suite (32x32.png, 128x128.png,
 *      128x128@2x.png, icon.icns, icon.ico) into
 *      apps/metis-desktop/src-tauri/icons/.
 *
 * Run via (from the repo root):
 *   node apps/metis-web/scripts/build-tauri-icons.mjs
 *
 * The script lives under apps/metis-web/ specifically so that Node's
 * bare-import resolution for `sharp` finds the module via
 * apps/metis-web/node_modules — the only place sharp is declared.
 * (The repo has no root package.json / hoisted node_modules; running
 * the script from anywhere else would fail with ERR_MODULE_NOT_FOUND
 * on a clean checkout.)
 *
 * Re-run this script whenever public/brand/metis-mark.svg changes.
 * The output icons are committed; consumers don't need to re-run
 * unless they're regenerating from a new source.
 */

import { execSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import sharp from "sharp";

const __dirname = dirname(fileURLToPath(import.meta.url));
// __dirname = <repo>/apps/metis-web/scripts
const metisWebDir = resolve(__dirname, "..");
// repoRoot = <repo>
const repoRoot = resolve(metisWebDir, "..", "..");

const sourceSvg = resolve(metisWebDir, "public/brand/metis-mark.svg");
const tauriDir = resolve(repoRoot, "apps/metis-desktop");
const iconsDir = resolve(tauriDir, "src-tauri/icons");
const tempPng = resolve(iconsDir, "_source-1024.png");

mkdirSync(iconsDir, { recursive: true });

console.log("Rasterising SVG to 1024x1024 with rounded-square chrome...");

// Composite: 1024 dark navy rounded square + centred mark @ 60 % size.
const bgSvg = `
  <svg width="1024" height="1024" xmlns="http://www.w3.org/2000/svg">
    <rect width="1024" height="1024" rx="180" ry="180" fill="#06080e"/>
  </svg>
`;

// Render the mark white at 614x614 (60 % of 1024) and centre it.
const markPng = await sharp(sourceSvg, { density: 600 })
  .resize(614, 614)
  .tint({ r: 244, g: 246, b: 250 })
  .png()
  .toBuffer();

await sharp(Buffer.from(bgSvg))
  .composite([
    {
      input: markPng,
      top: Math.round((1024 - 614) / 2),
      left: Math.round((1024 - 614) / 2),
    },
  ])
  .png()
  .toFile(tempPng);

console.log(`Wrote ${tempPng}`);
console.log("Running `pnpm tauri icon`...");

execSync(`pnpm tauri icon "${tempPng}"`, {
  cwd: tauriDir,
  stdio: "inherit",
});

console.log("Cleaning up source PNG...");
rmSync(tempPng, { force: true });

console.log("\nDone. Generated icon suite under apps/metis-desktop/src-tauri/icons/");
console.log("Verify with: ls apps/metis-desktop/src-tauri/icons/");
