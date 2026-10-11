import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { DEFAULT_THEME, THEMES } from "@/lib/theme";
import { contrast, inGamut, parseOklch, WHITE } from "./color";

const read = (name: string) => readFileSync(resolve(__dirname, "..", name), "utf-8");
// Comments are dropped: the header of themes.css quotes selectors as examples.
const stripComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");
const THEMES_CSS = stripComments(read("themes.css"));
const STYLES_CSS = stripComments(read("styles.css"));

/** The declarations of the first rule whose selector starts with `selector`. */
function block(css: string, selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  if (start < 0) throw new Error(`no rule for ${selector}`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  return Object.fromEntries(
    [...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1]!, m[2]!.trim()]),
  );
}

const rootLight = block(STYLES_CSS, "\n:root {");
const rootDark = block(STYLES_CSS, "\n.dark {");
const LIGHT_BG = parseOklch(rootLight["--background"]!).rgb;
const DARK_BG = parseOklch(rootDark["--background"]!).rgb;

const OTHER_THEMES = THEMES.filter((t) => t.id !== DEFAULT_THEME);

/** Every theme's brand colors, the default included. */
const brandOf = (id: string) =>
  id === DEFAULT_THEME
    ? { brand: rootLight["--brand"]!, brand2: rootLight["--brand-2"]! }
    : (() => {
        const light = block(THEMES_CSS, `:root[data-theme="${id}"]`);
        return { brand: light["--brand"]!, brand2: light["--brand-2"]! };
      })();

describe("themes.css and the theme list agree", () => {
  it("has a light and a dark block for every theme except the default", () => {
    for (const { id } of OTHER_THEMES) {
      expect(THEMES_CSS, id).toContain(`:root[data-theme="${id}"]`);
      expect(THEMES_CSS, id).toContain(`:root.dark[data-theme="${id}"]`);
      expect(THEMES_CSS, id).toContain(`[data-swatch="${id}"]`);
    }
  });

  it("has no block for a theme that is not in the list", () => {
    const ids = new Set<string>(THEMES.map((t) => t.id));
    for (const match of THEMES_CSS.matchAll(/data-theme="([^"]+)"/g)) {
      expect(ids.has(match[1]!), match[1]).toBe(true);
    }
    for (const match of THEMES_CSS.matchAll(/data-swatch="([^"]+)"/g)) {
      expect(ids.has(match[1]!), match[1]).toBe(true);
    }
  });

  it("gives the default swatch the same colors as the default theme", () => {
    const swatch = block(THEMES_CSS, `[data-swatch="${DEFAULT_THEME}"]`);
    expect(swatch["--brand"]).toBe(rootLight["--brand"]);
    expect(swatch["--brand-2"]).toBe(rootLight["--brand-2"]);
  });

  it("only changes the brand tokens", () => {
    const allowed = new Set([
      "--brand",
      "--brand-2",
      "--glow",
      "--ring",
      "--sidebar-ring",
      "--accent",
    ]);
    for (const { id } of OTHER_THEMES) {
      for (const selector of [`:root[data-theme="${id}"]`, `:root.dark[data-theme="${id}"]`]) {
        for (const name of Object.keys(block(THEMES_CSS, selector))) {
          expect(allowed.has(name), `${id} sets ${name}`).toBe(true);
        }
      }
    }
  });

  it("keeps the category colors out of the themes", () => {
    expect(THEMES_CSS).not.toMatch(/--cat-/);
  });

  it("has the same ring color as the brand, in light and in dark", () => {
    for (const { id } of OTHER_THEMES) {
      const light = block(THEMES_CSS, `:root[data-theme="${id}"]`);
      expect(light["--ring"], id).toBe(light["--brand"]);
      expect(light["--sidebar-ring"], id).toBe(light["--brand"]);
    }
  });
});

describe.each(THEMES.map((t) => t.id))("contrast of the %s theme", (id) => {
  const { brand, brand2 } = brandOf(id);
  const b1 = parseOklch(brand);
  const b2 = parseOklch(brand2);

  // The floor is what the default theme already meets (4.58 and 3.58).
  it("keeps white text readable on the brand color (4.5:1)", () => {
    expect(contrast(WHITE, b1.rgb)).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps white text readable on the second brand color (3:1, large or bold text)", () => {
    expect(contrast(WHITE, b2.rgb)).toBeGreaterThanOrEqual(3);
  });

  it.each([
    ["light", LIGHT_BG],
    ["dark", DARK_BG],
  ] as const)(
    "keeps both brand colors visible against the %s background (3:1)",
    (_mode, background) => {
      expect(contrast(b1.rgb, background)).toBeGreaterThanOrEqual(3);
      expect(contrast(b2.rgb, background)).toBeGreaterThanOrEqual(3);
    },
  );

  it("is inside the sRGB gamut, so every screen shows the colors we measured", () => {
    if (id === DEFAULT_THEME) return; // the original palette, from the template
    expect(inGamut(b1.L, b1.C, b1.hue)).toBe(true);
    expect(inGamut(b2.L, b2.C, b2.hue)).toBe(true);
  });
});

describe.each(OTHER_THEMES.map((t) => t.id))("accent backgrounds of the %s theme", (id) => {
  const foregroundLight = parseOklch(rootLight["--foreground"]!).rgb;
  const foregroundDark = parseOklch(rootDark["--foreground"]!).rgb;

  it("keeps the text readable on the accent background in light (7:1)", () => {
    const accent = parseOklch(block(THEMES_CSS, `:root[data-theme="${id}"]`)["--accent"]!).rgb;
    expect(contrast(foregroundLight, accent)).toBeGreaterThanOrEqual(7);
  });

  it("keeps the text readable on the accent background in dark (7:1)", () => {
    const accent = parseOklch(block(THEMES_CSS, `:root.dark[data-theme="${id}"]`)["--accent"]!).rgb;
    expect(contrast(foregroundDark, accent)).toBeGreaterThanOrEqual(7);
  });

  it("makes the accent background differ from the page background", () => {
    const light = parseOklch(block(THEMES_CSS, `:root[data-theme="${id}"]`)["--accent"]!).rgb;
    const dark = parseOklch(block(THEMES_CSS, `:root.dark[data-theme="${id}"]`)["--accent"]!).rgb;
    expect(light).not.toEqual(LIGHT_BG);
    expect(dark).not.toEqual(DARK_BG);
  });
});

describe("the contrast helper", () => {
  it("gives 21:1 for black on white and 1:1 for a color on itself", () => {
    expect(contrast([0, 0, 0], WHITE)).toBeCloseTo(21, 5);
    expect(contrast(WHITE, WHITE)).toBeCloseTo(1, 5);
  });

  it("matches the baseline measured outside the tests for the default brand", () => {
    expect(contrast(WHITE, parseOklch("oklch(0.585 0.233 277)").rgb)).toBeCloseTo(4.58, 1);
    expect(contrast(WHITE, parseOklch("oklch(0.656 0.241 354)").rgb)).toBeCloseTo(3.58, 1);
  });
});
