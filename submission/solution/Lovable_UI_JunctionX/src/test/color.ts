/** OKLCH colors and WCAG contrast, for the theme tests. */

export type Rgb = [number, number, number];

const encode = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
const decode = (c: number) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const clamp = (v: number) => Math.min(1, Math.max(0, v));

/** Linear sRGB of an OKLCH color, not clamped (to tell if it is inside the gamut). */
function linearRgb(L: number, C: number, hue: number): Rgb {
  const a = C * Math.cos((hue * Math.PI) / 180);
  const b = C * Math.sin((hue * Math.PI) / 180);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

export const inGamut = (L: number, C: number, hue: number) =>
  linearRgb(L, C, hue).every((v) => v >= -0.002 && v <= 1.002);

/** An `oklch(L C h)` string, as written in the CSS, to gamma-encoded sRGB. */
export function parseOklch(value: string): { rgb: Rgb; L: number; C: number; hue: number } {
  const match = /oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)/.exec(value);
  if (!match) throw new Error(`not an oklch color: ${value}`);
  const [L, C, hue] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const rgb = linearRgb(L, C, hue).map((v) => encode(clamp(v))) as Rgb;
  return { rgb, L, C, hue };
}

const luminance = ([r, g, b]: Rgb) => 0.2126 * decode(r) + 0.7152 * decode(g) + 0.0722 * decode(b);

export function contrast(x: Rgb, y: Rgb): number {
  const [hi, lo] = [luminance(x), luminance(y)].sort((p, q) => q - p);
  return (hi! + 0.05) / (lo! + 0.05);
}

export const WHITE: Rgb = [1, 1, 1];
