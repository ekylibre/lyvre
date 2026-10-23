// Tableau de bord (administrateur de l'instance) : intégrations recommandées pour la structure, ni
// activées ni écartées. « Configurer » ouvre la fiche ; « Ne plus proposer » retire l'encart.
import { Alert, Button, Group, Stack, Text } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { SESSION_KEY, useCurrentSession } from "../../api/session";
import { AppLink } from "../../app/navigation";
import { INTEGRATION_PITCHES, integrationLabel } from "./catalog";

export function IntegrationProposals() {
  const proposed = useCurrentSession().instance?.integrations?.proposed ?? [];
  const client = useQueryClient();
  const dismiss = useAction((slug: string) => api.post<{ notices: Notice[] }>(`/api/v1/integrations/${slug}/dismiss`));
  if (!proposed.length) return null;
  return (
    <Stack gap="sm" mb="lg">
      {proposed.map((slug) => (
        <Alert key={slug} color="lichen" variant="light" title={`Activez ${integrationLabel(slug)}`}>
          <Group justify="space-between" gap="sm">
            <Text size="sm">{INTEGRATION_PITCHES[slug] ?? "Intégration recommandée pour votre structure."}</Text>
            <Group gap="xs">
              <Button size="compact-md" component={AppLink} href={`/configuration/integrations/${slug}`}>Configurer</Button>
              <Button size="compact-md" variant="subtle" loading={dismiss.isPending && dismiss.variables === slug}
                onClick={() => dismiss.mutate(slug, { onSuccess: () => void client.invalidateQueries({ queryKey: SESSION_KEY }) })}>
                Ne plus proposer</Button>
            </Group>
          </Group>
        </Alert>
      ))}
    </Stack>
  );
}
