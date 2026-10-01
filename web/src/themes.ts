// Мягкие двухцветные темы в духе Minesweeper «The Clean One».
//
// Каждая тема — всего два цвета: bg (фон) и fg (контуры, цифры, текст).
// Все остальные оттенки получаются наложением fg на bg с разной
// прозрачностью, поэтому интерфейс согласован в любой теме.

export interface Theme {
  bg: string;
  fg: string;
}

export const THEMES = {
  Cream: { bg: "#F1EADF", fg: "#5B554C" },
  Sage: { bg: "#E6ECE6", fg: "#5E7A63" },
  Sky: { bg: "#E7EDF3", fg: "#566F88" },
  Blush: { bg: "#F4E9E6", fg: "#9E6B66" },
  Lavender: { bg: "#ECE9F3", fg: "#6E6396" },
  Slate: { bg: "#2B2F36", fg: "#C7CCD4" },
  Mocha: { bg: "#2E2926", fg: "#D6C4B2" },
  Forest: { bg: "#222B27", fg: "#A9C4B0" },
} satisfies Record<string, Theme>;

export type ThemeName = keyof typeof THEMES;
export const THEME_ORDER = Object.keys(THEMES) as ThemeName[];
export const DEFAULT_THEME: ThemeName = "Cream";

// Прозрачности наложения fg на bg для состояний закрытой ячейки.
export const TILE_FILL = 0.12; // обычная закрытая ячейка
export const TILE_HOVER = 0.22; // ячейка под курсором
export const TILE_PRESS = 0.3; // нажатая ячейка / зона аккорда
export const SURFACE = 0.06; // лёгкая «поверхность» панелей
export const HAIRLINE = 0.18; // тонкие разделители

function hexToRgb(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex(rgb: number[]): string {
  return "#" + rgb.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
}

/** Линейно смешивает два цвета: t=0 → c1, t=1 → c2. */
export function mix(c1: string, c2: string, t: number): string {
  const a = hexToRgb(c1);
  const b = hexToRgb(c2);
  return rgbToHex(a.map((v, i) => v + (b[i] - v) * t));
}

/** Непрозрачный результат наложения fg поверх bg с прозрачностью alpha. */
export function overlay(fg: string, bg: string, alpha: number): string {
  return mix(bg, fg, Math.min(1, Math.max(0, alpha)));
}

export function isDark(theme: Theme): boolean {
  const [r, g, b] = hexToRgb(theme.bg);
  return 0.299 * r + 0.587 * g + 0.114 * b < 128;
}

/** Выставляет CSS-переменные темы на :root (меню, HUD, оверлеи). */
export function applyTheme(theme: Theme): void {
  const { bg, fg } = theme;
  const s = document.documentElement.style;
  s.setProperty("--bg", bg);
  s.setProperty("--fg", fg);
  s.setProperty("--surface", overlay(fg, bg, SURFACE));
  s.setProperty("--surface-hi", overlay(fg, bg, TILE_FILL));
  s.setProperty("--press", overlay(fg, bg, TILE_PRESS));
  s.setProperty("--hairline", overlay(fg, bg, HAIRLINE));
  s.setProperty("--muted", overlay(fg, bg, 0.55));
  s.colorScheme = isDark(theme) ? "dark" : "light";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", bg);
}
