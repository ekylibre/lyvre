import { defineConfig, devices } from "@playwright/test";

/** Tests du site construit (astro preview) : parcours et accessibilité, sur ordinateur et sur mobile. */
export default defineConfig({
  testDir: "tests",
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:4321" },
  webServer: { command: "npx astro preview --port 4321 --ignore-lock", port: 4321, reuseExistingServer: true },
  projects: [
    { name: "ordinateur", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
