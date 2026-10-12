import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import BaseAccess from "./BaseAccess.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BaseAccess />
  </StrictMode>,
);
