import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemePicker } from "@/components/theme-picker";
import {
  applyMode,
  applyTheme,
  DEFAULT_THEME,
  MODE_KEY,
  THEME_KEY,
  THEMES,
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

function reset() {
  root.removeAttribute("data-theme");
  root.classList.remove("dark");
  applyTheme(DEFAULT_THEME);
  applyMode("system");
  localStorage.clear();
}

beforeEach(() => {
  // Radix sizes the popover with a ResizeObserver, which jsdom does not have.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal("localStorage", memoryStorage());
  reset();
});
afterEach(() => {
  reset();
  vi.unstubAllGlobals();
});

const open = () => fireEvent.click(screen.getByRole("button", { name: "Choose a theme" }));
const themeGroup = () => screen.getByRole("radiogroup", { name: "Theme" });
const modeGroup = () => screen.getByRole("radiogroup", { name: "Mode" });
const themeOption = (label: string) => within(themeGroup()).getByRole("radio", { name: label });

describe("ThemePicker", () => {
  it("is closed until the button is pressed", () => {
    render(<ThemePicker />);
    expect(screen.getByRole("button", { name: "Choose a theme" })).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
    open();
    expect(screen.getByRole("dialog", { name: "Appearance" })).toBeInTheDocument();
  });

  it("lists the six themes, with the default selected", () => {
    render(<ThemePicker />);
    open();

    const options = within(themeGroup()).getAllByRole("radio");
    expect(options.map((o) => o.getAttribute("aria-label"))).toEqual(THEMES.map((t) => t.label));
    expect(themeOption("Indigo & Pink")).toHaveAttribute("aria-checked", "true");
    expect(options.filter((o) => o.getAttribute("aria-checked") === "true")).toHaveLength(1);
  });

  it("applies the chosen theme at once, marks it and remembers it", () => {
    render(<ThemePicker />);
    open();
    fireEvent.click(themeOption("Ocean"));

    expect(root.getAttribute("data-theme")).toBe("ocean");
    expect(localStorage.getItem(THEME_KEY)).toBe("ocean");
    expect(themeOption("Ocean")).toHaveAttribute("aria-checked", "true");
    expect(themeOption("Indigo & Pink")).toHaveAttribute("aria-checked", "false");
  });

  it.each(THEMES.map((t) => [t.id, t.label] as const))(
    "switches to %s and back to the default",
    (id, label) => {
      render(<ThemePicker />);
      open();
      fireEvent.click(themeOption(label));
      expect(root.getAttribute("data-theme")).toBe(id === DEFAULT_THEME ? null : id);

      fireEvent.click(themeOption("Graphite"));
      fireEvent.click(themeOption("Indigo & Pink"));
      expect(root.hasAttribute("data-theme")).toBe(false);
      expect(localStorage.getItem(THEME_KEY)).toBeNull();
    },
  );

  it("opens with the theme that is already applied", () => {
    applyTheme("grape");
    render(<ThemePicker />);
    open();
    expect(themeOption("Grape")).toHaveAttribute("aria-checked", "true");
  });

  it("shows a swatch with the palette of each theme", () => {
    render(<ThemePicker />);
    open();
    for (const { id } of THEMES) {
      expect(themeGroup().querySelector(`[data-swatch="${id}"]`), id).not.toBeNull();
    }
  });

  it("has the three modes, with the current one selected", () => {
    applyMode("dark");
    render(<ThemePicker />);
    open();

    const group = within(modeGroup());
    expect(group.getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
    expect(group.getByRole("radio", { name: "Light" })).toHaveAttribute("aria-checked", "false");
    expect(group.getByRole("radio", { name: "System" })).toHaveAttribute("aria-checked", "false");
  });

  it("changes the mode, remembers light and dark, and forgets it for system", () => {
    render(<ThemePicker />);
    open();
    const group = within(modeGroup());

    fireEvent.click(group.getByRole("radio", { name: "Dark" }));
    expect(root.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(MODE_KEY)).toBe("dark");

    fireEvent.click(group.getByRole("radio", { name: "Light" }));
    expect(root.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem(MODE_KEY)).toBe("light");

    fireEvent.click(group.getByRole("radio", { name: "System" }));
    expect(localStorage.getItem(MODE_KEY)).toBeNull();
  });

  it("keeps the mode when the selected one is pressed again", () => {
    applyMode("dark");
    render(<ThemePicker />);
    open();
    fireEvent.click(within(modeGroup()).getByRole("radio", { name: "Dark" }));

    expect(within(modeGroup()).getByRole("radio", { name: "Dark" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(root.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(MODE_KEY)).toBe("dark");
  });

  it("does not change the mode when a theme is chosen, nor the theme when the mode changes", () => {
    render(<ThemePicker />);
    open();
    fireEvent.click(within(modeGroup()).getByRole("radio", { name: "Dark" }));
    fireEvent.click(themeOption("Forest"));
    fireEvent.click(within(modeGroup()).getByRole("radio", { name: "Light" }));

    expect(root.getAttribute("data-theme")).toBe("forest");
    expect(root.classList.contains("dark")).toBe(false);
  });

  it("closes with Escape and gives the focus back to the button", async () => {
    render(<ThemePicker />);
    const button = screen.getByRole("button", { name: "Choose a theme" });
    open();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(button));
  });

  it("keeps a preview of the current colors", () => {
    render(<ThemePicker />);
    open();
    expect(screen.getByText("Preview")).toBeInTheDocument();
    expect(screen.getByText("Accent")).toBeInTheDocument();
    expect(screen.getByText("Button")).toBeInTheDocument();
  });
});

function SunMoon() {
  const { dark, toggleDark } = useTheme();
  return (
    <button
      onClick={toggleDark}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
    >
      {dark ? "sun" : "moon"}
    </button>
  );
}

describe("ThemePicker next to the sun/moon button", () => {
  it("keeps the two in step, in both directions", () => {
    render(
      <>
        <SunMoon />
        <ThemePicker />
      </>,
    );
    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();

    open();
    fireEvent.click(within(modeGroup()).getByRole("radio", { name: "Dark" }));
    expect(screen.getByRole("button", { name: "Switch to light theme" })).toBeInTheDocument();

    act(() => screen.getByRole("button", { name: "Switch to light theme" }).click());
    expect(within(modeGroup()).getByRole("radio", { name: "Light" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(root.classList.contains("dark")).toBe(false);
  });

  it("keeps the chosen theme when the sun/moon button is used", () => {
    render(
      <>
        <SunMoon />
        <ThemePicker />
      </>,
    );
    open();
    fireEvent.click(themeOption("Sunset"));
    act(() => screen.getByRole("button", { name: "Switch to dark theme" }).click());

    expect(root.getAttribute("data-theme")).toBe("sunset");
    expect(root.classList.contains("dark")).toBe(true);
    expect(themeOption("Sunset")).toHaveAttribute("aria-checked", "true");
  });
});
