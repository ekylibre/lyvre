// Rendu de test sous les fournisseurs de la SPA (Mantine en mode test, Query, routeur).
import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { SESSION_KEY, type Session } from "../api/session";
import { theme } from "../app/theme";

export const TEST_SESSION: Session = {
  user: { id: 1, email: "tresorier@example.org", full_name: null, is_admin: false, must_change_password: false },
  // Intégrations toutes activées (comme l'instance de test du serveur) : un test les retire au besoin.
  instance: { id: 1, slug: "test", label: "Test", chart: "asso",
    integrations: { enabled: ["documenso", "facebook", "ga4", "helloasso", "odoo", "qonto", "smtp", "stancer"], proposed: [] } },
  instances: [{ id: 1, label: "Test" }],
  nav: [],
  admin_links: [],
  preferences: {},
  csrf_token: "token",
  role: "treasurer",
  permissions: { write: true, instance_admin: false },
};

export function renderWithProviders(ui: ReactElement, options: { session?: Session; route?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(SESSION_KEY, options.session ?? TEST_SESSION);
  const result = render(
    <QueryClientProvider client={client}>
      <MantineProvider theme={theme} env="test">
        <ModalsProvider>
          <MemoryRouter initialEntries={[options.route ?? "/"]}>{ui}</MemoryRouter>
        </ModalsProvider>
      </MantineProvider>
    </QueryClientProvider>,
  );
  return { ...result, client };
}
