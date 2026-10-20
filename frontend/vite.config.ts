// Îlots React servis par Flask (voir app/frontend.py : vite_assets).
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
    rollupOptions: { input: "src/main.tsx" },
  },
  server: {
    port: 5173,
    strictPort: true,
    // Les pages viennent de Flask (:5000) : les assets doivent pointer vers Vite.
    origin: "http://localhost:5173",
    cors: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
  },
});
