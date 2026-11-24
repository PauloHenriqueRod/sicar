/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../index.css'), 'utf8');
const colors = (block: string) => Object.fromEntries(Array.from(block.matchAll(/--color-([\w-]+):\s*(#[\da-f]{6});/gi), ([, name, hex]) => [name, hex]));
const light = colors(css.match(/@theme\s*\{([^}]+)\}/)?.[1] ?? '');
const dark = { ...light, ...colors(css.match(/\.dark\s*\{([^}]+)\}/)?.[1] ?? '') };

function luminance(hex: string) {
  const rgb = [1, 3, 5].map(offset => {
    const channel = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}

function contrast(foreground: string, background: string) {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

describe('Shared color palette contrast', () => {
  for (const [theme, palette] of Object.entries({ light, dark })) {
    it(`keeps text, hover states, control boundaries and focus legible in the ${theme} theme`, () => {
      const textPairs = [
        ...['canvas', 'surface', 'panel'].flatMap(background => [['ink', background], ['muted', background], ['accent-ink', background]]),
        ['on-accent', 'accent'], ['on-accent', 'accent-hover'],
        ['accent-ink', 'accent-soft'], ['success', 'success-soft'], ['danger', 'danger-soft'], ['warning', 'warning-soft'],
        ['danger', 'surface'], ['danger', 'panel'], ['success', 'surface'], ['success', 'panel'], ['warning', 'surface'],
        ['navigation-ink', 'navigation'], ['navigation-muted', 'navigation'],
        ['navigation-active-ink', 'navigation-active'],
      ];
      for (const [foreground, background] of textPairs) {
        expect(palette[foreground], foreground).toMatch(/^#[\da-f]{6}$/i);
        expect(palette[background], background).toMatch(/^#[\da-f]{6}$/i);
        expect(contrast(palette[foreground], palette[background]), `${foreground} on ${background}`).toBeGreaterThanOrEqual(4.5);
      }
      for (const background of ['canvas', 'surface', 'panel']) {
        expect(contrast(palette['control-outline'], palette[background]), `control on ${background}`).toBeGreaterThanOrEqual(3);
        expect(contrast(palette.focus, palette[background]), `focus on ${background}`).toBeGreaterThanOrEqual(3);
      }
    });
  }
});
