// Front React servi par Flask (voir app/frontend.py : vite_assets) :
// - src/main.tsx    : SPA React + Mantine (coquille app/templates/spa.html)
// - src/islands.tsx : îlots des pages Jinja pas encore migrées
// - build : app/static/dist/ + .vite/manifest.json, servi sous /static/dist/
// - dev   : serveur Vite sur :5173 (HMR), Flask charge les scripts depuis
//           VITE_DEV_SERVER=http://localhost:5173
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/static/dist/",
  build: {
    outDir: "../app/static/dist",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: { input: ["src/main.tsx", "src/islands.tsx"] },
  },
  server: {
    port: 5173,
    strictPort: true,
    // Les pages viennent de Flask (:5000) : les assets doivent pointer vers Vite.
    origin: "http://localhost:5173",
    cors: true,
    // app/spa_routes.json est partagé avec Flask (hors de frontend/).
    fs: { allow: [".."] },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
