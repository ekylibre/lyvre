// Fournisseurs communs : thème Mantine, dates en français, notifications, modales, données.
import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/notifications/styles.css";
import "@mantine/spotlight/styles.css";
import "@mantine/dropzone/styles.css";
import "@mantine/charts/styles.css";
import "mantine-datatable/styles.css";
import "dayjs/locale/fr";

import type { ReactNode } from "react";
import { MantineProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { ModalsProvider } from "@mantine/modals";
import { Notifications, notifications } from "@mantine/notifications";
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { theme } from "./theme";

function notifyError(error: unknown) {
  // 401 / 409 « pas d'instance » : redirection en cours (api/client.ts).
  if (error instanceof ApiError && (error.status === 401 || error.code === "no_instance")) return;
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
        <DatesProvider settings={{ locale: "fr", firstDayOfWeek: 1 }}>
          <ModalsProvider labels={{ confirm: "Confirmer", cancel: "Annuler" }}>
            <Notifications position="top-right" />
            {children}
          </ModalsProvider>
        </DatesProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}
