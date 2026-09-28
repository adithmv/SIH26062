import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
const proxy = {
  "/api": process.env.API_PROXY_TARGET || "http://127.0.0.1:8000",
};
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "prompt",
      injectRegister: "auto",
      includeAssets: ["maps/maitri-demo.svg", "icon.svg"],
      manifest: {
        name: "Polaris Mission Operations",
        short_name: "Polaris",
        start_url: "/",
        display: "standalone",
        theme_color: "#102b3b",
        background_color: "#f4f7f9",
        icons: [
          {
            src: "/icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,webmanifest}"],
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
        navigateFallbackDenylist: [/^\/api\//],
        clientsClaim: true,
        // Do not activate new application code underneath an open field report.
        skipWaiting: false,
        cleanupOutdatedCaches: true,
      },
    }),
  ],
  server: { host: "127.0.0.1", proxy },
  preview: { host: "127.0.0.1", proxy },
});
