#!/usr/bin/env node
/**
 * One-shot PWA icon generator.
 *
 * Renders the lucide `Brain` SVG centred on a #0a0a0a background and
 * outputs the full PWA icon set into apps/web/public/icons/.
 *
 * Requires: `sharp` (devDependency). Run from apps/web:
 *
 *   node scripts/generate-icons.mjs
 *
 * Re-run whenever branding changes.
 */

import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

let sharp;
try {
  sharp = (await import('sharp')).default;
} catch {
  console.error(
    'sharp is not installed. Install with: npm install --save-dev sharp',
  );
  process.exit(1);
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT_DIR = path.join(ROOT, 'public', 'icons');
const FAVICON = path.join(ROOT, 'public', 'favicon.ico');

const BG = '#0a0a0a';
const FG = '#fafafa';

// Lucide Brain icon (https://lucide.dev/icons/brain), centred 24x24.
const BRAIN_PATH =
  'M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4 M17.599 6.5a3 3 0 0 0 .399-1.375 M6.003 5.125A3 3 0 0 0 6.401 6.5 M3.477 10.896a4 4 0 0 1 .585-.396 M19.938 10.5a4 4 0 0 1 .585.396 M6 18a4 4 0 0 1-1.967-.516 M19.967 17.484A4 4 0 0 1 18 18';

function svg(size) {
  // Center the 24x24 icon and scale to ~60% of canvas.
  const iconSize = Math.round(size * 0.6);
  const offset = Math.round((size - iconSize) / 2);
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <rect width="${size}" height="${size}" fill="${BG}"/>
  <g transform="translate(${offset}, ${offset}) scale(${iconSize / 24})">
    <g fill="none" stroke="${FG}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="${BRAIN_PATH}"/>
    </g>
  </g>
</svg>`;
}

// Maskable variant: leaves a 20% safe-zone around the icon (per W3C maskable spec).
function maskableSvg(size) {
  const iconSize = Math.round(size * 0.4); // smaller so safe-zone isn't cropped
  const offset = Math.round((size - iconSize) / 2);
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <rect width="${size}" height="${size}" fill="${BG}"/>
  <g transform="translate(${offset}, ${offset}) scale(${iconSize / 24})">
    <g fill="none" stroke="${FG}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="${BRAIN_PATH}"/>
    </g>
  </g>
</svg>`;
}

async function renderPng(svgString, outPath) {
  const buffer = await sharp(Buffer.from(svgString)).png().toBuffer();
  await writeFile(outPath, buffer);
  console.log('  wrote', path.relative(ROOT, outPath));
}

async function renderIco(svgString, outPath) {
  // Sharp doesn't natively support .ico — write a 32x32 PNG and rely on browsers
  // tolerating PNG-in-ICO. For a true multi-res ICO, run `magick convert` after.
  const buffer = await sharp(Buffer.from(svgString)).resize(32, 32).png().toBuffer();
  await writeFile(outPath, buffer);
  console.log('  wrote', path.relative(ROOT, outPath));
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });

  const sizes = [72, 96, 128, 144, 152, 192, 384, 512];
  console.log('Generating standard icons...');
  for (const size of sizes) {
    await renderPng(svg(size), path.join(OUT_DIR, `icon-${size}.png`));
  }

  console.log('Generating maskable icons...');
  for (const size of [192, 512]) {
    await renderPng(maskableSvg(size), path.join(OUT_DIR, `maskable-${size}.png`));
  }

  console.log('Generating notification badge...');
  await renderPng(svg(72), path.join(OUT_DIR, 'badge-72.png'));

  console.log('Generating favicon...');
  await renderIco(svg(64), FAVICON);

  console.log('\nDone. Generated icon set in', path.relative(process.cwd(), OUT_DIR));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
