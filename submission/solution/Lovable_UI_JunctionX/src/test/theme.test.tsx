import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyMode,
  applyTheme,
  DEFAULT_THEME,
  isThemeId,
  MODE_KEY,
  readStoredMode,
  readStoredTheme,
  resolveDark,
  THEME_KEY,
  THEMES,
  themeBootScript,
  useTheme,
} from "@/lib/theme";

const root = document.documentElement;

/** An in-memory localStorage: the one Node provides on its own has no clear(). */
function memoryStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, String(value)),
    removeItem: (key: string) => void data.delete(key),
    clear: () => data.clear(),
  };
}

/** A storage the browser refuses to use (private mode, blocked cookies). */
function blockedStorage() {
  const fail = () => {
    throw new Error("blocked");
  };
  return { getItem: fail, setItem: fail, removeItem: fail, clear: fail };
}

/** A page with the given system setting; the default stub in setup.ts is "light". */
function systemPrefersDark(dark: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: dark && query.includes("dark"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

function reset() {
  localStorage.clear();
  root.removeAttribute("data-theme");
  root.classList.remove("dark");
  applyTheme(DEFAULT_THEME);
  applyMode("system");
  localStorage.clear();
}

beforeEach(() => {
  vi.stubGlobal("localStorage", memoryStorage());
  systemPrefersDark(false);
  reset();
});
afterEach(() => {
  vi.stubGlobal("localStorage", memoryStorage());
  reset();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the theme list", () => {
  it("has six themes, with the default first and unique ids", () => {
    expect(THEMES).toHaveLength(6);
    expect(THEMES[0]!.id).toBe(DEFAULT_THEME);
    expect(new Set(THEMES.map((t) => t.id)).size).toBe(6);
    expect(THEMES.map((t) => t.label)).toEqual([
      "Indigo & Pink",
      "Ocean",
      "Forest",
      "Sunset",
      "Grape",
      "Graphite",
    ]);
  });

  it.each(THEMES.map((t) => t.id))("accepts %s", (id) => {
    expect(isThemeId(id)).toBe(true);
  });

  it.each([undefined, null, 42, {}, "", "Ocean", "ocean ", "neon", "__proto__", 'ocean"><script>'])(
    "refuses %j",
    (value) => {
      expect(isThemeId(value)).toBe(false);
    },
  );
});

describe("reading what is saved", () => {
  it("falls back to the default theme and to the system mode when nothing is saved", () => {
    expect(readStoredTheme()).toBe(DEFAULT_THEME);
    expect(readStoredMode()).toBe("system");
  });

  it("reads a valid saved theme", () => {
    localStorage.setItem(THEME_KEY, "forest");
    expect(readStoredTheme()).toBe("forest");
  });

  it.each(["neon", "", "FOREST", "<script>", "constructor"])(
    "ignores the wrong saved theme %j",
    (value) => {
      localStorage.setItem(THEME_KEY, value);
      expect(readStoredTheme()).toBe(DEFAULT_THEME);
    },
  );

  it.each([
    ["dark", "dark"],
    ["light", "light"],
    ["system", "system"],
    ["", "system"],
    ["blue", "system"],
  ])("reads the saved mode %j as %s", (saved, expected) => {
    localStorage.setItem(MODE_KEY, saved);
    expect(readStoredMode()).toBe(expected);
  });

  it("does not crash when the storage is blocked", () => {
    vi.stubGlobal("localStorage", blockedStorage());
    expect(readStoredTheme()).toBe(DEFAULT_THEME);
    expect(readStoredMode()).toBe("system");
  });
});

describe("applying a theme", () => {
  it("sets the attribute, remembers it, and tells the default apart", () => {
    applyTheme("ocean");
    expect(root.getAttribute("data-theme")).toBe("ocean");
    expect(localStorage.getItem(THEME_KEY)).toBe("ocean");

    applyTheme(DEFAULT_THEME);
    expect(root.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("ignores a theme that is not in the list", () => {
    applyTheme("grape");
    applyTheme("neon" as never);
    expect(root.getAttribute("data-theme")).toBe("grape");
    expect(localStorage.getItem(THEME_KEY)).toBe("grape");
  });

  it("still applies the theme when the storage is blocked", () => {
    vi.stubGlobal("localStorage", blockedStorage());
    expect(() => applyTheme("sunset")).not.toThrow();
    expect(root.getAttribute("data-theme")).toBe("sunset");
  });

  it("never touches the light/dark mode", () => {
    applyMode("dark");
    applyTheme("forest");
    expect(root.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(MODE_KEY)).toBe("dark");
  });
});

describe("applying a mode", () => {
  it("sets and clears the dark class and remembers light and dark", () => {
    applyMode("dark");
    expect(root.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(MODE_KEY)).toBe("dark");

    applyMode("light");
    expect(root.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem(MODE_KEY)).toBe("light");
  });

  it("follows the system setting, and forgets the saved mode", () => {
    applyMode("dark");
    systemPrefersDark(true);
    applyMode("system");
    expect(root.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(MODE_KEY)).toBeNull();

    systemPrefersDark(false);
    applyMode("system");
    expect(root.classList.contains("dark")).toBe(false);
  });

  it("resolves the mode against the system setting", () => {
    systemPrefersDark(true);
    expect(resolveDark("system")).toBe(true);
    expect(resolveDark("light")).toBe(false);
    expect(resolveDark("dark")).toBe(true);
    systemPrefersDark(false);
    expect(resolveDark("system")).toBe(false);
    expect(resolveDark("dark")).toBe(true);
  });
});

function Probe({ name }: { name: string }) {
  const { theme, mode, dark, toggleDark } = useTheme();
  return (
    <button onClick={toggleDark} data-testid={name}>
      {theme}|{mode}|{dark ? "dark" : "light"}
    </button>
  );
}

describe("useTheme", () => {
  it("keeps every consumer in step when the theme or the mode changes", () => {
    render(
      <>
        <Probe name="a" />
        <Probe name="b" />
      </>,
    );
    expect(screen.getByTestId("a")).toHaveTextContent("indigo|system|light");

    act(() => applyTheme("grape"));
    act(() => applyMode("dark"));
    expect(screen.getByTestId("a")).toHaveTextContent("grape|dark|dark");
    expect(screen.getByTestId("b")).toHaveTextContent("grape|dark|dark");
  });

  it("toggles between light and dark, and saves an explicit choice", () => {
    render(<Probe name="a" />);
    act(() => screen.getByTestId("a").click());
    expect(screen.getByTestId("a")).toHaveTextContent("indigo|dark|dark");
    expect(localStorage.getItem(MODE_KEY)).toBe("dark");

    act(() => screen.getByTestId("a").click());
    expect(screen.getByTestId("a")).toHaveTextContent("indigo|light|light");
    expect(localStorage.getItem(MODE_KEY)).toBe("light");
  });

  it("follows a change made in another tab", () => {
    render(<Probe name="a" />);
    localStorage.setItem(THEME_KEY, "sunset");
    localStorage.setItem(MODE_KEY, "dark");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY }));
    });
    expect(screen.getByTestId("a")).toHaveTextContent("sunset|dark|dark");
    expect(root.getAttribute("data-theme")).toBe("sunset");
    expect(root.classList.contains("dark")).toBe(true);
  });

  it("returns to the default when the other tab clears the choice", () => {
    applyTheme("ocean");
    render(<Probe name="a" />);
    localStorage.clear();
    act(() => {
      window.dispatchEvent(new StorageEvent("storage"));
    });
    expect(screen.getByTestId("a")).toHaveTextContent("indigo|system|light");
    expect(root.hasAttribute("data-theme")).toBe(false);
  });

  it("stops listening when the component goes away", () => {
    const removed = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(<Probe name="a" />);
    unmount();
    expect(removed).toHaveBeenCalledWith("storage", expect.any(Function));
  });
});

/** Runs the head script against a fake page, as the browser would before the first paint. */
function runBootScript(options: {
  storage?: Record<string, string>;
  systemDark?: boolean;
  storageThrows?: boolean;
}) {
  const classes = new Set<string>();
  const attributes = new Map<string, string>();
  const documentStub = {
    documentElement: {
      classList: { add: (c: string) => classes.add(c) },
      setAttribute: (k: string, v: string) => attributes.set(k, v),
    },
  };
  const storageStub = {
    getItem: (key: string) => {
      if (options.storageThrows) throw new Error("blocked");
      return options.storage?.[key] ?? null;
    },
  };
  const matchMediaStub = () => ({ matches: Boolean(options.systemDark) });
  new Function("document", "localStorage", "matchMedia", themeBootScript())(
    documentStub,
    storageStub,
    matchMediaStub,
  );
  return { dark: classes.has("dark"), theme: attributes.get("data-theme") ?? null, attributes };
}

describe("the script that runs before the first paint", () => {
  it("applies a saved theme and mode", () => {
    expect(runBootScript({ storage: { [THEME_KEY]: "forest", [MODE_KEY]: "dark" } })).toMatchObject(
      {
        theme: "forest",
        dark: true,
      },
    );
  });

  it("uses the system setting when no mode is saved", () => {
    expect(runBootScript({ systemDark: true }).dark).toBe(true);
    expect(runBootScript({ systemDark: false }).dark).toBe(false);
  });

  it("lets a saved mode win over the system setting", () => {
    expect(runBootScript({ storage: { [MODE_KEY]: "light" }, systemDark: true }).dark).toBe(false);
    expect(runBootScript({ storage: { [MODE_KEY]: "dark" }, systemDark: false }).dark).toBe(true);
  });

  it("treats an unknown saved mode as the system setting, like readStoredMode", () => {
    expect(runBootScript({ storage: { [MODE_KEY]: "blue" }, systemDark: true }).dark).toBe(true);
    expect(readStoredMode()).toBe("system");
  });

  it("sets no attribute for the default theme or for nothing saved", () => {
    expect(runBootScript({ storage: { [THEME_KEY]: DEFAULT_THEME } }).theme).toBeNull();
    expect(runBootScript({}).theme).toBeNull();
  });

  it.each([
    "neon",
    "FOREST",
    "forest ",
    "",
    "__proto__",
    'forest"][onload=alert(1)',
    "<img src=x onerror=alert(1)>",
  ])("never lets the saved value %j reach the page", (value) => {
    const result = runBootScript({ storage: { [THEME_KEY]: value } });
    expect(result.theme).toBeNull();
    expect(result.attributes.size).toBe(0);
  });

  it("does not crash when the storage is blocked", () => {
    expect(runBootScript({ storageThrows: true })).toMatchObject({ theme: null, dark: false });
  });

  it("lists exactly the themes of the list, except the default", () => {
    const script = themeBootScript();
    for (const { id } of THEMES) {
      expect(script.includes(`"${id}"`)).toBe(id !== DEFAULT_THEME);
    }
  });
});
