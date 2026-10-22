// Tests de bout en bout (make e2e) : serveur Flask sur base jetable (scripts/e2e_server.py),
// fichiers du front construits au préalable.
import { defineConfig, devices } from "@playwright/test";
import fixtures from "./e2e/fixtures.json" with { type: "json" };

const baseURL = `http://127.0.0.1:${fixtures.port}`;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL, locale: "fr-FR", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "../.venv/bin/python ../scripts/e2e_server.py",
    url: `${baseURL}/login`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "ignore",
  },
});
