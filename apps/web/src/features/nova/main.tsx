import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { NovaApp } from "./NovaApp";
import "../../styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <NovaApp />
  </StrictMode>,
);
