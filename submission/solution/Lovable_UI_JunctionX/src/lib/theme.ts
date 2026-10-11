import { useCallback, useSyncExternalStore } from "react";

/**
 * Color themes and the light/dark mode.
 *
 * A theme is a named palette (src/themes.css): the `data-theme` attribute on
 * <html>. The mode is the `dark` class on <html>. Both are saved in
 * localStorage and applied by a small script in <head> before the first paint
 * (`themeBootScript`), so a saved choice never flashes.
 */

export const THEMES = [
  { id: "indigo", label: "Indigo & Pink" },
  { id: "ocean", label: "Ocean" },
  { id: "forest", label: "Forest" },
  { id: "sunset", label: "Sunset" },
  { id: "grape", label: "Grape" },
  { id: "graphite", label: "Graphite" },
] as const;

export type ThemeId = (typeof THEMES)[number]["id"];
export type ThemeMode = "light" | "dark" | "system";

/** The default theme is the one in styles.css: it has no `data-theme`. */
export const DEFAULT_THEME: ThemeId = "indigo";

/** Storage keys. `theme` already held "light" or "dark" before themes existed. */
export const THEME_KEY = "palette";
export const MODE_KEY = "theme";

export const isThemeId = (value: unknown): value is ThemeId =>
  typeof value === "string" && THEMES.some((t) => t.id === value);

const read = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

const write = (key: string, value: string | null) => {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* private mode: the choice just is not remembered */
  }
};

/** The saved theme, or the default when nothing valid is saved. */
export function readStoredTheme(): ThemeId {
  const value = read(THEME_KEY);
  return isThemeId(value) ? value : DEFAULT_THEME;
}

/** The saved mode; anything other than "light" or "dark" means "system". */
export function readStoredMode(): ThemeMode {
  const value = read(MODE_KEY);
  return value === "light" || value === "dark" ? value : "system";
}

const systemPrefersDark = () =>
  typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;

export const resolveDark = (mode: ThemeMode) =>
  mode === "system" ? systemPrefersDark() : mode === "dark";

type ThemeState = { theme: ThemeId; mode: ThemeMode; dark: boolean };

const SERVER_STATE: ThemeState = { theme: DEFAULT_THEME, mode: "system", dark: false };

function readState(): ThemeState {
  if (typeof document === "undefined") return SERVER_STATE;
  const root = document.documentElement;
  const attribute = root.getAttribute("data-theme");
  return {
    theme: isThemeId(attribute) ? attribute : DEFAULT_THEME,
    mode: readStoredMode(),
    dark: root.classList.contains("dark"),
  };
}

let state: ThemeState = readState();
const listeners = new Set<() => void>();

/** Refreshes the state from the page and tells the listeners if it changed. */
function sync() {
  const next = readState();
  if (next.theme === state.theme && next.mode === state.mode && next.dark === state.dark) return;
  state = next;
  listeners.forEach((listener) => listener());
}

/** Applies a theme and remembers it. The default theme removes the attribute. */
export function applyTheme(id: ThemeId) {
  if (!isThemeId(id)) return;
  const root = document.documentElement;
  if (id === DEFAULT_THEME) root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", id);
  write(THEME_KEY, id === DEFAULT_THEME ? null : id);
  sync();
}

/** Applies light, dark or the system setting, and remembers it. */
export function applyMode(mode: ThemeMode) {
  document.documentElement.classList.toggle("dark", resolveDark(mode));
  write(MODE_KEY, mode === "system" ? null : mode);
  sync();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const media =
    typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null;
  const onSystemChange = () => {
    if (readStoredMode() === "system") applyMode("system");
  };
  // Another tab changed the choice, or the system setting changed.
  const onStorage = () => {
    const root = document.documentElement;
    const theme = readStoredTheme();
    if (theme === DEFAULT_THEME) root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    root.classList.toggle("dark", resolveDark(readStoredMode()));
    sync();
  };
  media?.addEventListener?.("change", onSystemChange);
  window.addEventListener("storage", onStorage);
  sync();
  return () => {
    listeners.delete(listener);
    media?.removeEventListener?.("change", onSystemChange);
    window.removeEventListener("storage", onStorage);
  };
}

/** The current theme and mode, kept in step wherever they are changed. */
export function useTheme() {
  const current = useSyncExternalStore(
    subscribe,
    () => state,
    () => SERVER_STATE,
  );
  const setTheme = useCallback((id: ThemeId) => applyTheme(id), []);
  const setMode = useCallback((mode: ThemeMode) => applyMode(mode), []);
  const toggleDark = useCallback(() => applyMode(state.dark ? "light" : "dark"), []);
  return { ...current, setTheme, setMode, toggleDark };
}

/**
 * The script for <head>: applies the saved theme and mode before the first
 * paint. The saved theme is checked against the list, so a wrong or tampered
 * value never reaches the page.
 */
export function themeBootScript(): string {
  const ids = JSON.stringify(THEMES.map((t) => t.id).filter((id) => id !== DEFAULT_THEME));
  return (
    "try{var d=document.documentElement,s=localStorage,t=s.getItem(" +
    JSON.stringify(THEME_KEY) +
    ")," +
    "m=s.getItem(" +
    JSON.stringify(MODE_KEY) +
    ");" +
    `if(t&&${ids}.indexOf(t)>-1)d.setAttribute('data-theme',t);` +
    "if(m==='dark'||m==='light'?m==='dark':matchMedia('(prefers-color-scheme:dark)').matches)d.classList.add('dark')" +
    "}catch(e){}"
  );
}
