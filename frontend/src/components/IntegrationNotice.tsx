// Intégration activée mais indisponible (non paramétrée) : la fonction qui en dépend est grisée et
// ce bandeau dit pourquoi ; un admin a le lien vers son paramétrage. Intégration désactivée : rien
// (ce qui n'existe que par elle est masqué par l'écran).
import { Alert, Anchor } from "@mantine/core";
import { Info } from "lucide-react";
import { useCan, useIntegration } from "../api/session";
import { integrationLabel } from "../features/integrations/catalog";

export interface IntegrationState { enabled?: boolean; available: boolean; message: string | null }

export function IntegrationNotice({ name, state, consequence }: {
  name: string; state: IntegrationState | undefined; consequence: string;
}) {
  const can = useCan();
  const enabled = useIntegration(name) && state?.enabled !== false;
  if (!enabled || !state || state.available) return null;
  return (
    <Alert color="ardoise" variant="light" icon={<Info />} role="status" mb="sm"
      title={`${integrationLabel(name)} indisponible : ${consequence}.`}>
      {state.message}{" "}
      {can.instanceAdmin
        ? <Anchor href={`/configuration/integrations/${name}`}>Paramétrer l'intégration</Anchor>
        : "Contactez un administrateur."}
    </Alert>
  );
}
