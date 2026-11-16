// Aide « API et MCP » (lot AK4, claudedocs/design_api_mcp_aiffel.md § 9.3) : générée à partir des domaines et du
// registre des outils de cette installation (GET /api/v1/api-keys/help), jamais recopiée à la main.
import { Alert, Badge, Center, Code, Loader, Paper, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { mcpConfig, type DomainOption } from "./apiKeys";

interface HelpTool { name: string; title: string; domain: string; domain_label: string; access: "read" | "write"; description: string }
interface Help {
  mcp_url: string | null; api_url: string | null; domains: DomainOption[]; tools: HelpTool[];
  limits: { rate_per_minute: number; creations_per_day: number; file_max_mb: number };
}

/** Outils regroupés par domaine, dans l'ordre des domaines (« Toujours » en tête). */
export function toolsByDomain(help: Pick<Help, "domains" | "tools">): { label: string; tools: HelpTool[] }[] {
  const order = ["*", ...help.domains.map((d) => d.key)];
  return order.map((key) => ({
    label: key === "*" ? "Toujours disponibles" : help.domains.find((d) => d.key === key)?.label ?? key,
    tools: help.tools.filter((t) => t.domain === key),
  })).filter((g) => g.tools.length > 0);
}

export default function ApiHelpPage() {
  const { data, error } = useQuery({ queryKey: ["api-keys", "help"], queryFn: () => api.get<Help>("/api/v1/api-keys/help") });
  if (error) return <Alert color="brique">{(error as Error).message}</Alert>;
  if (!data) return <Center h={300}><Loader /></Center>;
  return (
    <>
      <PageHeader title="Aide API et MCP" description="Brancher un agent (Aiffel) ou un script sur cette structure avec une clé d'API." />
      <Stack gap="md">
        <Paper p="md">
          <Title order={2} size="h4" mb="xs">Se connecter</Title>
          <Text size="sm" mb="xs">Chaque appel porte la clé dans l'en-tête <Code>Authorization: Bearer lyv_…</Code>. La clé donne accès à une
            seule structure, avec les droits de la personne à qui elle est rattachée, et seulement dans ses domaines.</Text>
          <Table withRowBorders={false} fz="sm">
            <Table.Tbody>
              <Table.Tr><Table.Th w={180}>Serveur MCP</Table.Th><Table.Td>{data.mcp_url ? <Code>{data.mcp_url}</Code> : "Adresse publique non configurée (APP_BASE_URL)."}
                <Text size="xs" c="dimmed">Transport HTTP streamable, sans session ; outils filtrés par les domaines de la clé.</Text></Table.Td></Table.Tr>
              <Table.Tr><Table.Th>API REST</Table.Th><Table.Td>{data.api_url ? <Code>{data.api_url}</Code> : "—"}
                <Text size="xs" c="dimmed">Lecture (GET) dans les domaines de la clé ; outils : <Code>GET /agent/tools</Code>,
                  <Code>POST /agent/tools/&lt;outil&gt;</Code>, pièces : <Code>POST /agent/files</Code> (multipart, {data.limits.file_max_mb} Mo au plus).</Text></Table.Td></Table.Tr>
              <Table.Tr><Table.Th>Limites par défaut</Table.Th><Table.Td>{data.limits.rate_per_minute} requêtes par minute,
                {" "}{data.limits.creations_per_day} créations par jour (réglables par clé) ; au-delà, réponse 429 et délai d'attente.</Table.Td></Table.Tr>
            </Table.Tbody>
          </Table>
          <Text size="sm" fw={500} mt="sm" mb={4}>Configuration d'un client MCP</Text>
          <Code block>{mcpConfig(data.mcp_url, "lyv_…")}</Code>
        </Paper>
        <Alert color="paille" title="Rien n'est définitif sans vous">Les outils d'écriture créent des brouillons : factures d'achat à vérifier,
          tiers à vérifier, écritures non validées. Aucun outil ne comptabilise, ne valide, ne numérote ni n'envoie.</Alert>
        {toolsByDomain(data).map((group) => (
          <Paper p="md" key={group.label}>
            <Title order={2} size="h4" mb="xs">{group.label}</Title>
            <Table fz="sm" verticalSpacing={6}>
              <Table.Tbody>{group.tools.map((t) => (
                <Table.Tr key={t.name}>
                  <Table.Td w={240}><Code>{t.name}</Code>{t.access === "write" && <Badge ml={6} size="xs" color="paille" variant="light">écriture</Badge>}</Table.Td>
                  <Table.Td><Text size="sm" fw={500}>{t.title}</Text><Text size="xs" c="dimmed">{t.description}</Text></Table.Td>
                </Table.Tr>
              ))}</Table.Tbody>
            </Table>
          </Paper>
        ))}
      </Stack>
    </>
  );
}
