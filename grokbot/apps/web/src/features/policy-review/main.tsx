import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { applyUiAppearance, watchSystemAppearance } from "../../lib/ui-appearance";
import { PolicyReviewApp } from "./PolicyReviewApp";
import "../../styles.css";

applyUiAppearance();
function App() {
  useEffect(() => watchSystemAppearance(), []);
  return <PolicyReviewApp />;
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
