// Mes clés d'API (lot AK4) : clés rattachées à l'utilisateur dans cette structure, journal et révocation. La création
// reste à l'administrateur (Configuration › Accès API).
import { useState } from "react";
import { Alert, Anchor, Button, Group, Text } from "@mantine/core";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { AppLink } from "../../app/navigation";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate, formatDateTime } from "../../lib/format";
import { domainSummary, STATE_LABELS, type ApiKeyItem, type DomainOption } from "./apiKeys";
import { JournalDrawer } from "./JournalDrawer";

const KEY = ["api-keys", "mine"];

export default function MyApiKeysPage() {
  const { data, isFetching, error } = useList<ApiKeyItem, { domains: DomainOption[]; mcp_url: string | null }>(KEY, "/api/v1/me/api-keys");
  const [journal, setJournal] = useState<ApiKeyItem | null>(null);
  const revoke = useAction((k: ApiKeyItem) => api.post<{ notices: Notice[] }>(`/api/v1/api-keys/${k.id}/revoke`), { invalidate: [KEY] });
  const columns: GridColumn<ApiKeyItem>[] = [
    { accessor: "name", title: "Clé", hideable: false, render: (k) => (
      <div><Text size="sm" fw={500}>{k.name}</Text><Text size="xs" c="dimmed" ff="monospace">{k.prefix}</Text></div>) },
    { accessor: "read_domains", title: "Domaines", render: (k) => (
      <Text size="xs">{domainSummary(k, data?.meta?.domains ?? []).map((d) => `${d.label}${d.write ? " (écriture)" : ""}`).join(", ")}</Text>) },
    { accessor: "last_used_at", title: "Dernier usage", render: (k) => <Text size="sm">{k.last_used_at ? formatDateTime(k.last_used_at) : "Jamais"}</Text> },
    { accessor: "expires_at", title: "Expire le", render: (k) => <Text size="sm">{formatDate(k.expires_at.slice(0, 10))}</Text> },
    { accessor: "state", title: "État", render: (k) => <StatusBadge tone={STATE_LABELS[k.state].tone}>{STATE_LABELS[k.state].label}</StatusBadge> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right", render: (k) => (
      <Group gap={4} justify="flex-end" wrap="nowrap">
        <Button variant="subtle" size="compact-sm" onClick={() => setJournal(k)}>Journal</Button>
        {k.state !== "revoked" && <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
          title: `Révoquer la clé « ${k.name} » ?`, message: "Elle cesse de fonctionner immédiatement. Cette action est définitive.",
          confirmLabel: "Révoquer", onConfirm: () => revoke.mutate(k) })}>Révoquer</Button>}
      </Group>) },
  ];
  return (
    <>
      <PageHeader title="Mes clés d'API"
        description="Clés rattachées à vous dans cette structure : elles agissent avec vos droits, jamais plus."
        actions={<Button variant="default" component={AppLink} href="/configuration/api-keys/help">Aide API et MCP</Button>} />
      {error && <Alert color="brique" mb="sm">{(error as Error).message}</Alert>}
      <DataGrid id="my-api-keys" records={data?.items} columns={columns} fetching={isFetching}
        emptyText="Aucune clé rattachée à vous. L'administrateur de la structure les crée dans Configuration › Accès API." />
      <Text size="xs" c="dimmed" mt="sm">Une clé perdue ou divulguée se révoque ici ; <Anchor component={AppLink} href="/configuration/api-keys/help" size="xs">l'aide</Anchor> explique comment la brancher.</Text>
      <JournalDrawer apiKey={journal} onClose={() => setJournal(null)} />
    </>
  );
}
