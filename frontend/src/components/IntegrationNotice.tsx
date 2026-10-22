// Intégration indisponible (désactivée ou non paramétrée) : la fonction qui en dépend est
// grisée et ce bandeau dit pourquoi ; un admin a le lien vers son paramétrage.
import { Alert, Anchor } from "@mantine/core";
import { Info } from "lucide-react";
import { useCurrentSession } from "../api/session";

export interface IntegrationState { available: boolean; message: string | null }

const LABELS: Record<string, string> = {
  helloasso: "HelloAsso", odoo: "Odoo", smtp: "SMTP (relance email)", qonto: "Qonto", stancer: "Stancer",
};

export function IntegrationNotice({ name, state, consequence }: {
  name: string; state: IntegrationState | undefined; consequence: string;
}) {
  const session = useCurrentSession();
  if (!state || state.available) return null;
  return (
    <Alert color="ardoise" variant="light" icon={<Info />} role="status" mb="sm"
      title={`${LABELS[name] ?? name} indisponible : ${consequence}.`}>
      {state.message}{" "}
      {session.user?.is_admin
        ? <Anchor href={`/configuration/integrations/${name}`}>Paramétrer l'intégration</Anchor>
        : "Contactez un administrateur."}
    </Alert>
  );
}
