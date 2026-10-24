// Configuration › Modèles de bail (lot L2) : un modèle par type de bail (dérogatoire commercial,
// commercial 3-6-9, habitation, rural), champs « {{ … }} » remplis à la rédaction. Les modèles livrés
// sont à relire ; enregistrer un modèle ne change pas les baux déjà rédigés.
import { useState } from "react";
import { Alert, Button, Center, Group, Loader, Paper, Select, Stack, Tabs, Text } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { confirmAction } from "../../components/ConfirmButton";
import { HtmlTemplateEditor, usePdfPreview, type FieldOption } from "../../components/HtmlTemplateEditor";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";

interface Template { kind: string; title: string; version: number; reviewed: boolean; updated_at: string | null; body_html?: string }
interface ListResponse { items: Template[]; meta: { fields: FieldOption[]; leases: (FieldOption & { kind: string })[] } }
const KEY = ["lease-templates"];

function TemplateEditor({ kind, meta }: { kind: string; meta: ListResponse["meta"] }) {
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: [...KEY, kind], queryFn: () => api.get<{ item: Template }>(`/api/v1/lease-templates/${kind}`) });
  const [body, setBody] = useState<string | null>(null);
  const [leaseId, setLeaseId] = useState<string | null>(meta.leases.find((l) => l.kind === kind)?.value ?? meta.leases[0]?.value ?? null);
  const done = (r: { item: Template }) => { setBody(null); client.setQueryData([...KEY, kind], { item: r.item }); void client.invalidateQueries({ queryKey: KEY }); };
  const save = useAction(() => api.put<{ item: Template; notices: Notice[] }>(`/api/v1/lease-templates/${kind}`, { body_html: body }));
  const reset = useAction(() => api.post<{ item: Template; notices: Notice[] }>(`/api/v1/lease-templates/${kind}/reset`));
  const preview = usePdfPreview();
  if (!data) return <Center h={200}><Loader /></Center>;
  const t = data.item;
  return (
    <Stack>
      {!t.reviewed && <Alert color="paille" title="Modèle livré, à relire">Relisez ce modèle et adaptez-le à vos baux (les mentions entre
        crochets sont à compléter), puis enregistrez-le.</Alert>}
      <HtmlTemplateEditor key={`${kind}-${t.version}`} label={`Source du modèle ${t.title}`} initial={t.body_html ?? ""}
        onChange={setBody} fields={meta.fields} />
      <Group justify="space-between">
        <Group gap="xs">
          <Select aria-label="Bail pour l'aperçu" placeholder="Bail pour l'aperçu" w={280} data={meta.leases} value={leaseId} onChange={setLeaseId} />
          <Button variant="default" disabled={!leaseId} loading={preview.isPending}
            onClick={() => preview.mutate({ url: `/api/v1/lease-templates/${kind}/preview`, body: { body_html: body ?? t.body_html, lease_id: leaseId } })}>
            Aperçu (PDF)</Button>
        </Group>
        <Group gap="xs">
          <Button variant="subtle" color="brique" onClick={() => confirmAction({
            title: "Rétablir le modèle livré ?", message: "Vos modifications de ce modèle seront perdues (les baux déjà rédigés ne changent pas).",
            confirmLabel: "Rétablir", onConfirm: () => reset.mutate(undefined, { onSuccess: done }) })}>Rétablir le modèle livré</Button>
          <Button disabled={body === null} loading={save.isPending} onClick={() => save.mutate(undefined, { onSuccess: done })}>Enregistrer</Button>
        </Group>
      </Group>
      <Text size="xs" c="dimmed">Version {t.version}{t.updated_at ? ` · modifiée le ${formatDate(t.updated_at)}` : ""}</Text>
    </Stack>
  );
}

export default function LeaseTemplatesPage() {
  const { data } = useQuery({ queryKey: KEY, queryFn: () => api.get<ListResponse>("/api/v1/lease-templates") });
  const [kind, setKind] = useState<string | null>("derogatory");
  if (!data) return <Center h={300}><Loader /></Center>;
  return (
    <>
      <PageHeader title="Modèles de bail"
        description="Un modèle par type de bail. Les champs entre accolades sont remplis à la rédaction ; le texte d'un bail se retouche ensuite depuis sa fiche." />
      <Paper p="md">
        <Tabs value={kind} onChange={setKind} keepMounted={false}>
          <Tabs.List mb="md">
            {data.items.map((t) => <Tabs.Tab key={t.kind} value={t.kind}>{t.title}{!t.reviewed && " · à relire"}</Tabs.Tab>)}
          </Tabs.List>
          {data.items.map((t) => (
            <Tabs.Panel key={t.kind} value={t.kind}><TemplateEditor kind={t.kind} meta={data.meta} /></Tabs.Panel>
          ))}
        </Tabs>
      </Paper>
    </>
  );
}
