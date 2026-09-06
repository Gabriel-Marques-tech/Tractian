import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `base` relativo: a mesma build serve em `npm run dev`, no FastAPI em :8001 e
// num deploy estatico, sem saber em que caminho foi montada.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist" },
});
