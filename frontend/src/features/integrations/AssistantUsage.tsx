// Intégrations › Assistant Claude : usage du mois (tokens, quota, coût estimé par modèle) — lot AG9b.d.
import { Paper, Progress, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";

export interface AssistantUsageView {
  month: string; used_tokens: number; quota_tokens: number | null; left_tokens: number | null; cost_usd: number;
  models: { model: string | null; responses: number; input_tokens: number; output_tokens: number; cache_read_tokens: number; cost_usd: number }[];
}

const n = (v: number) => v.toLocaleString("fr-FR");

export function AssistantUsage() {
  const { data } = useQuery({ queryKey: ["assistant", "usage"], queryFn: () => api.get<{ item: AssistantUsageView }>("/api/v1/assistant/usage") });
  const u = data?.item;
  if (!u) return null;
  return (
    <Paper p="md" mb="md">
      <Title order={3} mb="sm">Usage du mois ({u.month})</Title>
      <Text size="sm">{n(u.used_tokens)} tokens{u.quota_tokens ? ` sur ${n(u.quota_tokens)} (quota mensuel)` : " (sans quota)"}</Text>
      {u.quota_tokens ? <Progress my={6} value={Math.min(100, (100 * u.used_tokens) / u.quota_tokens)} /> : null}
      {u.models.length > 0 && (
        <Table mt="xs">
          <Table.Thead><Table.Tr><Table.Th>Modèle</Table.Th><Table.Th ta="right">Réponses</Table.Th><Table.Th ta="right">Entrée</Table.Th>
            <Table.Th ta="right">Sortie</Table.Th><Table.Th ta="right">Cache lu</Table.Th><Table.Th ta="right">Coût estimé</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {u.models.map((m) => (
              <Table.Tr key={m.model ?? "?"}><Table.Td>{m.model}</Table.Td><Table.Td ta="right">{n(m.responses)}</Table.Td>
                <Table.Td ta="right">{n(m.input_tokens)}</Table.Td><Table.Td ta="right">{n(m.output_tokens)}</Table.Td>
                <Table.Td ta="right">{n(m.cache_read_tokens)}</Table.Td><Table.Td ta="right">{m.cost_usd.toLocaleString("fr-FR", { maximumFractionDigits: 4 })} $</Table.Td></Table.Tr>))}
          </Table.Tbody>
        </Table>)}
      <Text size="xs" c="dimmed" mt={4}>Coût estimé d'après les prix publics de l'API Claude : la facture d'Anthropic fait foi.</Text>
    </Paper>
  );
}
