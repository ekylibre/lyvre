// Configuration › Intégrations (admin) : services externes de l'instance et leur état.
import { Card, Group, SimpleGrid, Text } from "@mantine/core";
import { useList } from "../../api/resources";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { AppLink } from "../../app/navigation";
import { INTEGRATIONS_KEY, STATUS_TONES, checkSummary, type Integration } from "./types";

export default function IntegrationsPage() {
  const { data } = useList<Integration>(INTEGRATIONS_KEY, "/api/v1/integrations");
  return (
    <>
      <PageHeader title="Intégrations"
        description="Services externes utilisés par cette instance. Ouvrez une intégration pour la configurer, l'activer ou la désactiver et tester son fonctionnement." />
      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        {data?.items.map((v) => (
          <Card key={v.slug} component={AppLink} href={`/configuration/integrations/${v.slug}`} padding="md"
            style={{ textDecoration: "none", color: "inherit" }} aria-label={`${v.label} : ${v.status_label}`}>
            <Group justify="space-between" align="flex-start">
              <Text fw={700} size="lg">{v.label}</Text>
              <StatusBadge tone={STATUS_TONES[v.status]}>{v.status_label}</StatusBadge>
            </Group>
            <Text size="sm" c="dimmed" mt={4}>{v.description}</Text>
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
