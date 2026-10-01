import { defineConfig } from "vite";

export default defineConfig({
  // Относительные пути — сборка работает и из подпапки (GitHub Pages), и в Tauri.
  base: "./",
  worker: { format: "es" },
  build: { target: "es2022" },
});
