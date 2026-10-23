// Fournisseurs communs : thème Mantine, dates en français, notifications, modales, données.
import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/notifications/styles.css";
import "@mantine/spotlight/styles.css";
import "@mantine/dropzone/styles.css";
import "@mantine/charts/styles.css";
import "mantine-datatable/styles.css";
import "./lyvre.css";
import "dayjs/locale/fr";
import dayjs from "dayjs";
import customParseFormat from "dayjs/plugin/customParseFormat";

import type { ReactNode } from "react";
import { MantineProvider } from "@mantine/core";
import { LucideProvider } from "lucide-react";
import { DatesProvider } from "@mantine/dates";
import { ModalsProvider } from "@mantine/modals";
import { Notifications, notifications } from "@mantine/notifications";
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { openIntegrationRequired } from "../components/IntegrationRequired";
import { theme } from "./theme";

// Saisie clavier des DateInput (« 15/06/2026 ») : analyse selon valueFormat.
dayjs.extend(customParseFormat);

function notifyError(error: unknown) {
  // 401 / 409 « pas d'instance » : redirection en cours (api/client.ts).
  if (error instanceof ApiError && (error.status === 401 || error.code === "no_instance")) return;
  // Intégration désactivée : fenêtre qui propose de l'activer plutôt qu'une erreur.
  if (error instanceof ApiError && error.code === "integration_required" && typeof error.details.service === "string") {
    openIntegrationRequired(error.details.service, error.message);
    return;
  }
  const message = error instanceof Error ? error.message : "Erreur inattendue.";
  notifications.show({ color: "red", title: "Erreur", message, autoClose: false });
}

export function createQueryClient() {
  return new QueryClient({
    queryCache: new QueryCache({ onError: notifyError }),
    mutationCache: new MutationCache({
      // Une mutation qui gère ses erreurs (formulaire) déclare meta.silent.
      onError: (error, _vars, _ctx, mutation) => {
        if (!mutation.meta?.silent) notifyError(error);
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (count, error) =>
          !(error instanceof ApiError && error.status > 0 && error.status < 500) && count < 2,
      },
    },
  });
}

export function Providers({ children, client }: { children: ReactNode; client: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <MantineProvider theme={theme} defaultColorScheme="auto">
        {/* Icônes Lucide au trait de 1,5 px, 20 px dans l'interface (charte). */}
        <LucideProvider strokeWidth={1.5} size={20}>
        <DatesProvider settings={{ locale: "fr", firstDayOfWeek: 1 }}>
          <ModalsProvider labels={{ confirm: "Confirmer", cancel: "Annuler" }}>
            <Notifications position="top-right" />
            {children}
          </ModalsProvider>
        </DatesProvider>
        </LucideProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}
