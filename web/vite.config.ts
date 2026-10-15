import { defineConfig, type Plugin } from "vite";

/**
 * Счётчик посещений GoatCounter — только если задан GOATCOUNTER_CODE
 * (код сайта, например `noguess` для noguess.goatcounter.com). Его передаёт
 * workflow GitHub Pages; в десктоп-сборке и при разработке счётчика нет.
 */
function goatCounter(): Plugin {
  const code = process.env.GOATCOUNTER_CODE?.trim() ?? "";
  if (code && !/^[a-z0-9-]+$/.test(code)) {
    throw new Error(`GOATCOUNTER_CODE must be a GoatCounter site code, got "${code}"`);
  }
  return {
    name: "goatcounter",
    apply: "build",
    transformIndexHtml() {
      if (!code) return [];
      return [
        {
          tag: "script",
          attrs: {
            "data-goatcounter": `https://${code}.goatcounter.com/count`,
            async: true,
            src: "https://gc.zgo.at/count.js",
          },
          injectTo: "head",
        },
      ];
    },
  };
}

export default defineConfig({
  // Относительные пути — сборка работает и из подпапки (GitHub Pages), и в Tauri.
  base: "./",
  worker: { format: "es" },
  build: { target: "es2022" },
  plugins: [goatCounter()],
});
