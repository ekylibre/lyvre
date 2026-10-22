// Routeur de la SPA : une route paresseuse par page de spa_routes.json ; toute autre URL
// est une ancienne page Jinja (chargement complet).
import { useEffect } from "react";
import { createBrowserRouter, useLocation, useRouteError } from "react-router";
import { Alert, Button, Center, Loader, Stack } from "@mantine/core";
import { BARE_PAGES, PAGES, SPA_ROUTES, toRouterPath } from "./routes";
import { RootLayout } from "./RootLayout";

export interface RouteHandle {
  bare: boolean;
}

/** URL hors SPA atteinte par le routeur : la page est servie par Flask. */
function LegacyPage() {
  const location = useLocation();
  useEffect(() => {
    window.location.replace(location.pathname + location.search + location.hash);
  }, [location]);
  return <Center h="60vh"><Loader /></Center>;
}

function RouteError() {
  const error = useRouteError();
  const message = error instanceof Error ? error.message : "Erreur inattendue.";
  return (
    <Center h="60vh">
      <Stack maw={480}>
        <Alert color="red" title="La page n'a pas pu s'afficher">{message}</Alert>
        <Button onClick={() => window.location.reload()}>Recharger la page</Button>
      </Stack>
    </Center>
  );
}

export function createRouter() {
  const pages = SPA_ROUTES.map((route) => ({
    path: toRouterPath(route.rule),
    handle: { bare: BARE_PAGES.has(route.endpoint) } satisfies RouteHandle,
    lazy: async () => ({ Component: (await PAGES[route.endpoint]()).default }),
  }));
  return createBrowserRouter([
    {
      element: <RootLayout />,
      errorElement: <RouteError />,
      hydrateFallbackElement: <Center h="60vh"><Loader /></Center>,
      children: [...pages, { path: "*", element: <LegacyPage /> }],
    },
  ]);
}
