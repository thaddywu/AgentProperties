import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { applyUiAppearance, watchSystemAppearance } from "../../lib/ui-appearance";
import { NovaApp } from "./NovaApp";
import "../../styles.css";

applyUiAppearance();

function AppearanceSync() {
  useEffect(() => watchSystemAppearance(), []);
  return null;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppearanceSync />
    <NovaApp />
  </StrictMode>,
);
