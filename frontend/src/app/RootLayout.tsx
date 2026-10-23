// Mise en page selon la route : pages nues (connexion, choix d'instance) ou application
// (session obligatoire, en-tête et menus).
import { useEffect, type ReactNode } from "react";
import { Outlet, useLocation, useMatches } from "react-router";
import { Center, Loader, useMantineColorScheme } from "@mantine/core";
import { useSession } from "../api/session";
import { AppLayout } from "./AppShell/AppLayout";
import { AppSpotlight } from "./Spotlight";
import type { RouteHandle } from "./router";

/** Applique le thème mémorisé dans le compte (FM14) dès que la session est connue. */
function ColorSchemeSync() {
  const { data } = useSession();
  const { setColorScheme } = useMantineColorScheme();
  const wanted = data?.preferences.color_scheme;
  useEffect(() => {
    if (wanted) setColorScheme(wanted);
  }, [wanted, setColorScheme]);
  return null;
}

function Loading() {
  return <Center h="100vh"><Loader /></Center>;
}

/** Pages de l'application : connexion et instance exigées. */
function SessionGate({ children }: { children: ReactNode }) {
  const { data: session, isPending } = useSession();
  const location = useLocation();
  const next = encodeURIComponent(location.pathname + location.search);
  const missing = !session?.user ? "/login" : session.user.must_change_password ? "/password"
    : !session.instance ? "/select-instance" : null;
  useEffect(() => {
    if (!isPending && missing) window.location.replace(`${missing}?next=${next}`);
  }, [isPending, missing, next]);
  if (isPending || missing) return <Loading />;
  return <>{children}</>;
}

export function RootLayout() {
  const matches = useMatches();
  const bare = matches.some((m) => (m.handle as RouteHandle | undefined)?.bare);
  return (
    <>
      <ColorSchemeSync />
      {bare ? (
        <Outlet />
      ) : (
        <SessionGate>
          <AppSpotlight />
          <AppLayout><Outlet /></AppLayout>
        </SessionGate>
      )}
    </>
  );
}
