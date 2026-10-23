// Configuration › Intégrations (admin) : services externes de l'instance et leur état.
import { Card, Group, SimpleGrid, Text } from "@mantine/core";
import { useList } from "../../api/resources";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { AppLink } from "../../app/navigation";
import { IntegrationLogo } from "./IntegrationLogo";
import { INTEGRATIONS_KEY, STATUS_TONES, checkSummary, sortIntegrations, type Integration } from "./types";

export default function IntegrationsPage() {
  const { data } = useList<Integration>(INTEGRATIONS_KEY, "/api/v1/integrations");
  return (
    <>
      <PageHeader title="Intégrations"
        description="Services externes proposés pour cette structure, désactivés tant que vous ne les activez pas. Ouvrez une intégration pour l'activer, la configurer et tester son fonctionnement." />
      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        {data && sortIntegrations(data.items).map((v) => (
          <Card key={v.slug} component={AppLink} href={`/configuration/integrations/${v.slug}`} padding="md"
            style={{ textDecoration: "none", color: "inherit" }} aria-label={`${v.label} : ${v.status_label}`}>
            <Group justify="space-between" align="flex-start">
              <Group gap="sm" wrap="nowrap"><IntegrationLogo slug={v.slug} /><Text fw={700} size="lg">{v.label}</Text></Group>
              <Group gap={6}>
                {v.recommended && !v.enabled && <StatusBadge tone="info">Recommandée</StatusBadge>}
                <StatusBadge tone={STATUS_TONES[v.status]}>{v.status_label}</StatusBadge>
              </Group>
            </Group>
            <Text size="sm" c="dimmed" mt={4}>{v.description}</Text>
            {v.recommended && !v.enabled && <Text size="sm" fw={600} c="var(--lv-lichen)" mt="xs">Activer et configurer →</Text>}
            {v.last_check ? (
              <>
                <Text size="sm" mt="xs">Dernier test : {checkSummary(v.last_check)}
                  {v.check_outdated && <Text span size="sm" c="dimmed"> (configuration modifiée depuis)</Text>}</Text>
                {v.status === "error" && <Text size="sm" c="var(--lv-brique)" truncate>{v.last_check.message}</Text>}
              </>
            ) : <Text size="sm" c="dimmed" mt="xs">Jamais testée</Text>}
          </Card>
        ))}
      </SimpleGrid>
    </>
  );
}
