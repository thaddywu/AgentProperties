import type { AppearancePreference } from "@rakazo/ui-tokens";
import { resolveAppearance } from "@rakazo/ui-tokens";
import { Button } from "@rakazo/ui-web";
import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import {
  getUiAppearancePreference,
  readSystemAppearance,
  setUiAppearance,
  watchSystemAppearance,
} from "../lib/ui-appearance";

export function AppearanceToggle() {
  const [preference, setPreference] = useState<AppearancePreference>(getUiAppearancePreference);
  const [system, setSystem] = useState(readSystemAppearance);
  useEffect(() => watchSystemAppearance(setSystem), []);
  const light = resolveAppearance(preference, system) === "light";
  const label = light ? "Switch to dark mode" : "Switch to light mode";

  return (
    <Button
      size="sm"
      variant="ghost"
      aria-label={label}
      title={label}
      onClick={() => {
        const next = light ? "dark" : "light";
        setUiAppearance(next);
        setPreference(next);
      }}
    >
      {light ? <Moon className="size-4" /> : <Sun className="size-4" />}
    </Button>
  );
}
