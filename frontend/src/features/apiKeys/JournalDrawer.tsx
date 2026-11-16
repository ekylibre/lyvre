// Journal d'une clé d'API (lot AK4) : 200 derniers appels, refus et créations, lien vers l'objet créé.
import { useState } from "react";
import { Alert, Anchor, Drawer, Group, Loader, SegmentedControl, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { AppLink } from "../../app/navigation";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDateTime } from "../../lib/format";
import type { ApiKeyItem } from "./apiKeys";

export interface CallItem {
  id: number; at: string; channel: "mcp" | "rest"; target: string; domain: string | null; domain_label: string | null;
  access: "read" | "write" | null; status: number; error: string | null;
  object: { type: string; id: number; url: string; label: string } | null; duration_ms: number | null;
}

/** Résultat lisible d'un appel. */
export function callOutcome(c: Pick<CallItem, "status">): { label: string; tone: "ok" | "todo" | "gap" } {
  if (c.status === 429) return { label: "Limite atteinte", tone: "todo" };
  if (c.status === 401 || c.status === 403) return { label: "Refusé", tone: "gap" };
  if (c.status >= 400) return { label: "Erreur", tone: "gap" };
  return { label: "Accepté", tone: "ok" };
}

export function JournalDrawer({ apiKey, onClose }: { apiKey: ApiKeyItem | null; onClose: () => void }) {
  const [kind, setKind] = useState("all");
  const { data, isPending, error } = useQuery({
    queryKey: ["api-keys", "calls", apiKey?.id, kind], enabled: apiKey !== null,
    queryFn: () => api.get<{ items: CallItem[]; meta: { creations_today: number } }>(
      `/api/v1/api-keys/${apiKey!.id}/calls${kind === "all" ? "" : `?kind=${kind}`}`),
  });
  return (
    <Drawer opened={apiKey !== null} onClose={onClose} position="right" size="xl" title={apiKey ? `Journal de « ${apiKey.name} »` : ""}>
      <Group justify="space-between" mb="sm">
        <SegmentedControl value={kind} onChange={setKind} data={[
          { value: "all", label: "Tout" }, { value: "errors", label: "Refus et erreurs" }, { value: "creations", label: "Créations" }]} />
        {data && apiKey && <Text size="sm" c="dimmed">Créations aujourd'hui : {data.meta.creations_today} sur {apiKey.creations_per_day}</Text>}
      </Group>
      {error && <Alert color="brique">{(error as Error).message}</Alert>}
      {isPending && apiKey ? <Loader size="sm" /> : data && (data.items.length ? (
        <Table verticalSpacing={6} fz="sm">
          <Table.Thead><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Appel</Table.Th><Table.Th>Domaine</Table.Th>
            <Table.Th>Résultat</Table.Th><Table.Th>Objet créé</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{data.items.map((c) => {
            const outcome = callOutcome(c);
            return (
              <Table.Tr key={c.id}>
                <Table.Td className="lv-num" style={{ whiteSpace: "nowrap" }}>{formatDateTime(c.at)}</Table.Td>
                <Table.Td><Text size="sm">{c.target}</Text><Text size="xs" c="dimmed">{c.channel === "mcp" ? "MCP" : "API REST"}
                  {c.access === "write" ? " · écriture" : ""}{c.duration_ms != null ? ` · ${c.duration_ms} ms` : ""}</Text></Table.Td>
                <Table.Td>{c.domain_label ?? "—"}</Table.Td>
                <Table.Td><StatusBadge tone={outcome.tone}>{outcome.label}</StatusBadge>
                  {c.error && <Text size="xs" c="dimmed" mt={2}>{c.error}</Text>}</Table.Td>
                <Table.Td>{c.object ? <Anchor component={AppLink} href={c.object.url} size="sm">{c.object.label}</Anchor> : "—"}</Table.Td>
              </Table.Tr>
            );
          })}</Table.Tbody>
        </Table>
      ) : <Text size="sm" c="dimmed">Aucun appel.</Text>)}
    </Drawer>
  );
}
