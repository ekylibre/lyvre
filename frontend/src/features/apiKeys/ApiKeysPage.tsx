// Configuration › Accès API (lot AK1, claudedocs/design_api_mcp_aiffel.md § 9.1) : clés qui ouvrent la structure à un
// agent (Aiffel) ou à un script, par domaine en lecture et en écriture. La clé n'est affichée qu'une fois.
import { useState } from "react";
import {
  Accordion, Alert, Button, Checkbox, Code, CopyButton, Group, NumberInput, Select, Stack, Table, Text, TextInput, Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate, formatDateTime } from "../../lib/format";
import {
  canWrite, domainSummary, isoInDays, mcpConfig, STATE_LABELS, toggleDomain,
  type ApiKeyItem, type ApiKeysMeta, type DomainGrid,
} from "./apiKeys";

const QUERY_KEY = ["api-keys"];
const ENDPOINT = "/api/v1/api-keys";

function DomainTable({ meta, grid, role, onChange }: {
  meta: ApiKeysMeta; grid: DomainGrid; role: string | undefined; onChange: (grid: DomainGrid) => void;
}) {
  return (
    <Table withRowBorders={false} verticalSpacing={4}>
      <Table.Thead>
        <Table.Tr><Table.Th>Domaine</Table.Th><Table.Th w={80} ta="center">Lecture</Table.Th><Table.Th w={80} ta="center">Écriture</Table.Th></Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {meta.domains.map((d) => {
          const writable = canWrite(d, role);
          const writeBox = (
            <Checkbox aria-label={`Écriture : ${d.label}`} disabled={!writable} checked={grid.write.includes(d.key)}
              onChange={(e) => onChange(toggleDomain(grid, d.key, "write", e.currentTarget.checked))} />
          );
          return (
            <Table.Tr key={d.key}>
              <Table.Td><Text size="sm" fw={500}>{d.label}</Text><Text size="xs" c="dimmed">{d.description}</Text></Table.Td>
              <Table.Td><Group justify="center"><Checkbox aria-label={`Lecture : ${d.label}`} checked={grid.read.includes(d.key)}
                onChange={(e) => onChange(toggleDomain(grid, d.key, "read", e.currentTarget.checked))} /></Group></Table.Td>
              <Table.Td><Group justify="center">{writable ? writeBox : (
                <Tooltip label={d.writable ? "Un expert-comptable consulte sans modifier." : "Lecture seule pour l'instant."}>
                  <span>{writeBox}</span></Tooltip>)}</Group></Table.Td>
            </Table.Tr>
          );
        })}
      </Table.Tbody>
    </Table>
  );
}

interface KeyValues {
  name: string; user_id: string | null; expires_on: string; rate_per_minute: number | string;
  creations_per_day: number | string; grid: DomainGrid;
}

function KeyForm({ meta, item, onDone, onCreated }: {
  meta: ApiKeysMeta; item?: ApiKeyItem; onDone: () => void; onCreated?: (token: string, name: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm<KeyValues>({ initialValues: {
    name: item?.name ?? "", user_id: item ? String(item.user.id) : null,
    expires_on: item ? item.expires_at.slice(0, 10) : isoInDays(meta.defaults.days),
    rate_per_minute: item?.rate_per_minute ?? meta.defaults.rate_per_minute,
    creations_per_day: item?.creations_per_day ?? meta.defaults.creations_per_day,
    grid: { read: item?.read_domains ?? [], write: item?.write_domains ?? [] },
  } });
  const save = useAction((v: KeyValues) => {
    const body = { name: v.name, expires_on: v.expires_on, rate_per_minute: v.rate_per_minute,
      creations_per_day: v.creations_per_day, read_domains: v.grid.read, write_domains: v.grid.write,
      ...(item ? {} : { user_id: v.user_id ? Number(v.user_id) : undefined }) };
    return item
      ? api.patch<{ notices: Notice[] }>(`${ENDPOINT}/${item.id}`, body)
      : api.post<{ notices: Notice[]; token: string }>(ENDPOINT, body);
  }, { invalidate: [QUERY_KEY], silent: true });
  const userId = item ? String(item.user.id) : form.values.user_id;
  const role = meta.members.find((m) => String(m.id) === userId)?.role;
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: (res) => {
        if (!item && "token" in res) onCreated?.((res as { token: string }).token, values.name);
        else onDone();
      },
      onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={item ? "Enregistrer" : "Créer la clé"} onCancel={onDone} loading={save.isPending}>
        <TextInput label="Nom de l'usage" required data-autofocus placeholder="Aiffel — saisie terrain"
          description="Il sert aussi de badge sur ce que la clé saisit." {...form.getInputProps("name")} />
        {!item && (
          <Select label="Utilisateur rattaché" required searchable allowDeselect={false}
            description="La clé ne donne jamais plus que le rôle de cette personne."
            data={meta.members.map((m) => ({ value: String(m.id), label: m.full_name ? `${m.full_name} — ${m.email}` : m.email }))}
            {...form.getInputProps("user_id")} />
        )}
        <div>
          <Text size="sm" fw={500}>Domaines</Text>
          <Text size="xs" c="dimmed">L'écriture crée seulement des brouillons, que vous vérifiez dans Lyvre.</Text>
          <DomainTable meta={meta} grid={form.values.grid} role={role} onChange={(grid) => form.setFieldValue("grid", grid)} />
          {form.errors.read_domains && <Text size="xs" c="var(--lv-brique-ink)">{form.errors.read_domains}</Text>}
          {form.errors.write_domains && <Text size="xs" c="var(--lv-brique-ink)">{form.errors.write_domains}</Text>}
        </div>
        <TextInput type="date" label="Expire le" max={isoInDays(meta.defaults.max_days)} {...form.getInputProps("expires_on")} />
        <Accordion variant="contained">
          <Accordion.Item value="limits">
            <Accordion.Control>Limites</Accordion.Control>
            <Accordion.Panel>
              <Group grow>
                <NumberInput label="Requêtes par minute" min={1} {...form.getInputProps("rate_per_minute")} />
                <NumberInput label="Créations par jour" min={0} {...form.getInputProps("creations_per_day")} />
              </Group>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      </FormBody>
    </form>
  );
}

function TokenShown({ token, name, mcpUrl, onClose }: { token: string; name: string; mcpUrl: string | null; onClose: () => void }) {
  return (
    <Stack>
      <Alert color="paille" title="Copiez la clé maintenant">Elle ne sera plus affichée. Si elle est perdue, révoquez-la et créez-en une autre.</Alert>
      <div>
        <Text size="sm" fw={500} mb={4}>Clé « {name} »</Text>
        <Group gap="xs" wrap="nowrap">
          <Code style={{ flex: 1, wordBreak: "break-all" }}>{token}</Code>
          <CopyButton value={token}>{({ copied, copy }) => <Button variant="light" onClick={copy}>{copied ? "Copiée" : "Copier"}</Button>}</CopyButton>
        </Group>
      </div>
      <div>
        <Text size="sm" fw={500} mb={4}>Adresse du serveur MCP</Text>
        {mcpUrl ? <Code>{mcpUrl}</Code> : <Text size="sm" c="dimmed">Adresse publique de Lyvre non configurée (APP_BASE_URL).</Text>}
      </div>
      <div>
        <Group justify="space-between" mb={4}>
          <Text size="sm" fw={500}>Configuration d'un client MCP</Text>
          <CopyButton value={mcpConfig(mcpUrl, token)}>{({ copied, copy }) => (
            <Button size="compact-sm" variant="subtle" onClick={copy}>{copied ? "Copiée" : "Copier"}</Button>)}</CopyButton>
        </Group>
        <Code block>{mcpConfig(mcpUrl, token)}</Code>
      </div>
      <Group justify="flex-end"><Button onClick={onClose}>J'ai copié la clé</Button></Group>
    </Stack>
  );
}

export default function ApiKeysPage() {
  const can = useCan();
  const { data, isFetching, error } = useList<ApiKeyItem, ApiKeysMeta>(QUERY_KEY, ENDPOINT, { enabled: can.instanceAdmin });
  const [editing, setEditing] = useState<ApiKeyItem | "new" | null>(null);
  const [created, setCreated] = useState<{ token: string; name: string } | null>(null);
  const revoke = useAction((k: ApiKeyItem) => api.post<{ notices: Notice[] }>(`${ENDPOINT}/${k.id}/revoke`), { invalidate: [QUERY_KEY] });
  const meta = data?.meta;

  if (!can.instanceAdmin) {
    return <><PageHeader title="Accès API" /><Alert color="ardoise">Réservé à l'administrateur de l'instance.</Alert></>;
  }

  const columns: GridColumn<ApiKeyItem>[] = [
    { accessor: "name", title: "Clé", hideable: false, sortable: true, render: (k) => (
      <div><Text size="sm" fw={500}>{k.name}</Text><Text size="xs" c="dimmed" ff="monospace">{k.prefix}</Text></div>) },
    { accessor: "user", title: "Utilisateur", render: (k) => <Text size="sm">{k.user.full_name ?? k.user.email}</Text> },
    { accessor: "read_domains", title: "Domaines", render: (k) => (
      <Text size="xs">{domainSummary(k, meta?.domains ?? []).map((d) => `${d.label}${d.write ? " (écriture)" : ""}`).join(", ")}</Text>) },
    { accessor: "last_used_at", title: "Dernier usage", render: (k) => <Text size="sm">{k.last_used_at ? formatDateTime(k.last_used_at) : "Jamais"}</Text> },
    { accessor: "expires_at", title: "Expire le", render: (k) => <Text size="sm">{formatDate(k.expires_at.slice(0, 10))}</Text> },
    { accessor: "state", title: "État", render: (k) => <StatusBadge tone={STATE_LABELS[k.state].tone}>{STATE_LABELS[k.state].label}</StatusBadge> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right", render: (k) => k.state !== "revoked" && (
      <Group gap={4} justify="flex-end" wrap="nowrap">
        <Button variant="subtle" size="compact-sm" onClick={() => setEditing(k)}>Modifier</Button>
        <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
          title: `Révoquer la clé « ${k.name} » ?`, message: "Elle cesse de fonctionner immédiatement. Cette action est définitive.",
          confirmLabel: "Révoquer", onConfirm: () => revoke.mutate(k) })}>Révoquer</Button>
      </Group>) },
  ];

  return (
    <>
      <PageHeader title="Accès API"
        description="Clés qui ouvrent cette structure à un agent (Aiffel) ou à un script : domaines lus et écrits, expiration, limites."
        actions={<Button onClick={() => setEditing("new")} disabled={!meta}>Créer une clé</Button>} />
      {error && <Alert color="brique" mb="sm">{(error as Error).message}</Alert>}
      {meta?.mcp_url && <Text size="sm" c="dimmed" mb="sm">Serveur MCP : <Code>{meta.mcp_url}</Code></Text>}
      <DataGrid id="api-keys" records={data?.items} columns={columns} fetching={isFetching}
        emptyText="Aucune clé. Créez-en une par usage (par exemple « Aiffel — saisie terrain »)." />
      {meta && (
        <FormModal opened={editing !== null && created === null} onClose={() => setEditing(null)} size="lg"
          title={editing === "new" ? "Créer une clé" : "Modifier la clé"}>
          {editing !== null && (
            <KeyForm meta={meta} item={editing === "new" ? undefined : editing} onDone={() => setEditing(null)}
              onCreated={(token, name) => setCreated({ token, name })} />
          )}
        </FormModal>
      )}
      <FormModal opened={created !== null} onClose={() => { setCreated(null); setEditing(null); }} title="Clé créée" size="lg">
        {created && <TokenShown token={created.token} name={created.name} mcpUrl={meta?.mcp_url ?? null}
          onClose={() => { setCreated(null); setEditing(null); }} />}
      </FormModal>
    </>
  );
}
