import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";
import { Check, Monitor, Moon, Palette, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { isThemeId, THEMES, useTheme, type ThemeMode } from "@/lib/theme";

const MODES: { id: ThemeMode; label: string; icon: typeof Sun }[] = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
  { id: "system", label: "System", icon: Monitor },
];

/**
 * A small "Appearance" panel: the light/dark/system mode and a list of color
 * themes. A choice applies at once and is remembered. The swatch of each theme
 * uses `data-swatch`, so it shows that theme's colors whatever the page uses.
 */
export function ThemePicker() {
  const { theme, mode, setTheme, setMode } = useTheme();

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          className="rounded-full bg-card"
          aria-label="Choose a theme"
        >
          <Palette aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[19rem] p-4" aria-label="Appearance">
        <h2 className="text-sm font-semibold text-foreground">Appearance</h2>

        <p id="theme-mode-label" className="mt-3 text-xs font-medium text-muted-foreground">
          Mode
        </p>
        <ToggleGroup
          type="single"
          value={mode}
          onValueChange={(value) => {
            // Clicking the selected mode again would clear the value: ignore it.
            if (value === "light" || value === "dark" || value === "system") setMode(value);
          }}
          aria-labelledby="theme-mode-label"
          variant="outline"
          className="mt-1.5 grid grid-cols-3 gap-1.5"
        >
          {MODES.map(({ id, label, icon: Icon }) => (
            <ToggleGroupItem key={id} value={id} aria-label={label} className="h-9 gap-1.5 text-xs">
              <Icon className="h-3.5 w-3.5" aria-hidden /> {label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        <p id="theme-list-label" className="mt-4 text-xs font-medium text-muted-foreground">
          Theme
        </p>
        <RadioGroupPrimitive.Root
          value={theme}
          onValueChange={(value) => {
            if (isThemeId(value)) setTheme(value);
          }}
          aria-labelledby="theme-list-label"
          className="mt-1.5 grid gap-1.5"
        >
          {THEMES.map(({ id, label }) => (
            <RadioGroupPrimitive.Item
              key={id}
              value={id}
              aria-label={label}
              className="flex w-full items-center gap-3 rounded-lg border border-border bg-card px-3 py-2 text-left text-sm text-foreground outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring data-[state=checked]:border-brand data-[state=checked]:bg-accent"
            >
              <span
                data-swatch={id}
                className="brand-gradient h-6 w-6 shrink-0 rounded-full border border-border"
                aria-hidden
              />
              <span className="flex-1 font-medium">{label}</span>
              <RadioGroupPrimitive.Indicator>
                <Check className="h-4 w-4 text-brand" aria-hidden />
              </RadioGroupPrimitive.Indicator>
            </RadioGroupPrimitive.Item>
          ))}
        </RadioGroupPrimitive.Root>

        <p className="mt-4 text-xs font-medium text-muted-foreground">Preview</p>
        <div
          className="mt-1.5 flex items-center gap-2 rounded-lg border border-border bg-background p-3"
          aria-hidden
        >
          <span className="brand-gradient h-2 flex-1 rounded-full" />
          <span className="rounded-md bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground">
            Accent
          </span>
          <span className="rounded-md bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
            Button
          </span>
        </div>
      </PopoverContent>
    </Popover>
  );
}
