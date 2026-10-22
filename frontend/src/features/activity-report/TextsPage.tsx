// Rapport d'activité › Textes (admin) : un bloc par rubrique (titre, contenu mis en forme ou
// HTML) ; import depuis le site. Le HTML d'un bloc reste intact tant qu'il n'est pas modifié.
import { useEffect, useState } from "react";
import { Alert, Anchor, Button, Center, Checkbox, Code, Collapse, Group, Loader, Paper, Stack, Text, TextInput, Textarea, Title } from "@mantine/core";
import { Link, RichTextEditor } from "@mantine/tiptap";
import "@mantine/tiptap/styles.css";
import { useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { FiscalYearSelect, REPORT_KEY, useReportContext, withFy } from "./shared";

interface Block { key: string; label: string; title: string; body: string }
interface Texts {
  fiscal_year: { id: number; label: string }; blocks: Block[];
  site: { available: boolean; preview: { block_key: string; filename: string; count: number | null }[] };
}

function BlockEditor({ block, onChange }: { block: Block; onChange: (patch: Partial<Block>) => void }) {
  const [showSource, setShowSource] = useState(false);
  const [source, setSource] = useState(block.body);
  const editor = useEditor({
    extensions: [StarterKit.configure({ link: false }), Link.configure({ openOnClick: false })],
    content: block.body,
    // Seule une vraie modification réécrit le HTML enregistré (le rendu de l'éditeur peut le normaliser).
    onUpdate: ({ editor: e }) => { const html = e.getHTML(); setSource(html); onChange({ body: html }); },
    immediatelyRender: true,
  });
  return (
    <Paper p="md" mb="md">
      <Group gap="xs" mb="xs"><Title order={4}>{block.label}</Title><Code>{block.key}</Code></Group>
      <TextInput label="Titre" description="Facultatif" value={block.title} maxLength={200} mb="xs"
        onChange={(e) => onChange({ title: e.currentTarget.value })} />
      <Text size="sm" fw={500} mb={4}>Contenu</Text>
      <RichTextEditor editor={editor}>
        <RichTextEditor.Toolbar>
          <RichTextEditor.ControlsGroup><RichTextEditor.H2 /><RichTextEditor.H3 /></RichTextEditor.ControlsGroup>
          <RichTextEditor.ControlsGroup><RichTextEditor.Bold /><RichTextEditor.Italic /><RichTextEditor.Underline /></RichTextEditor.ControlsGroup>
          <RichTextEditor.ControlsGroup><RichTextEditor.BulletList /><RichTextEditor.OrderedList /></RichTextEditor.ControlsGroup>
          <RichTextEditor.ControlsGroup><RichTextEditor.Link /><RichTextEditor.Unlink /><RichTextEditor.ClearFormatting /></RichTextEditor.ControlsGroup>
        </RichTextEditor.Toolbar>
        <RichTextEditor.Content mih={140} />
      </RichTextEditor>
      <Anchor component="button" type="button" size="sm" mt={4} onClick={() => setShowSource((s) => !s)}>
        {showSource ? "Masquer le code HTML" : "Afficher / éditer le code HTML"}</Anchor>
      <Collapse expanded={showSource}>
        <Textarea mt={4} autosize minRows={4} maxRows={16} classNames={{ input: "lv-num" }} aria-label={`Code HTML : ${block.label}`}
          value={source} onChange={(e) => setSource(e.currentTarget.value)} />
        <Group justify="space-between" mt={4}>
          <Text size="xs" c="dimmed">Modifiez le HTML brut puis chargez-le dans l'éditeur visuel.</Text>
          <Button size="compact-sm" variant="default" onClick={() => {
            onChange({ body: source });
            editor?.commands.setContent(source, { emitUpdate: false });
          }}>Charger dans l'éditeur</Button>
        </Group>
      </Collapse>
    </Paper>
  );
}

export default function TextsPage() {
  const { setParams, context } = useReportContext();
  const [params] = useUrlParams({ fy_id: "" });
  const key = [...REPORT_KEY, "texts", params.fy_id];
  const { data } = useQuery({ queryKey: key, enabled: !context.error,
    queryFn: () => api.get<Texts>(`/api/v1/activity-report/texts${params.fy_id ? `?fy_id=${params.fy_id}` : ""}`) });
  const [blocks, setBlocks] = useState<Block[] | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  useEffect(() => { if (data) setBlocks(data.blocks); }, [data]);
  const fyId = data?.fiscal_year.id;
  const save = useAction(() => api.put<{ notices: Notice[] }>("/api/v1/activity-report/texts", { fy_id: fyId, blocks }), { invalidate: [key] });
  const importSite = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/activity-report/texts/import-site", { fy_id: fyId, overwrite }),
    { invalidate: [key] });
  if (context.error) return <Alert color="ardoise" mt="md">{(context.error as Error).message}</Alert>;
  if (!data || !blocks) return <Center h={300}><Loader /></Center>;
  return (
    <>
      <PageHeader title={`Textes du rapport — exercice ${data.fiscal_year.label}`}
        description="Éditeur visuel ; le code HTML de chaque bloc reste accessible."
        actions={<Button variant="default" component={AppLink} href={withFy("/rapport-activite/", fyId)}>Aperçu</Button>} />
      <FilterBar><FiscalYearSelect context={context.data} onChange={(fy_id) => setParams({ fy_id })} /></FilterBar>
      <Stack maw={900}>
        {data.site.available && (
          <Paper p="md">
            <Title order={4}>Importer depuis le site</Title>
            <Text size="sm" c="dimmed" mb="xs">Pré-remplit certains blocs à partir des données du site web.</Text>
            <Text size="xs" c="dimmed" mb="xs">{data.site.preview.map((p) => `${p.block_key} ← ${p.filename}${p.count !== null ? ` (${p.count})` : ""}`).join(" · ")}</Text>
            <Group>
              <Checkbox label="Écraser les blocs déjà remplis" checked={overwrite} onChange={(e) => setOverwrite(e.currentTarget.checked)} />
              <Button size="compact-md" variant="default" loading={importSite.isPending} onClick={() => importSite.mutate()}>Importer</Button>
            </Group>
          </Paper>
        )}
        <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          {blocks.map((b, i) => (
            <BlockEditor key={`${fyId}-${b.key}-${data.blocks[i].body.length}`} block={b}
              onChange={(patch) => setBlocks((current) => current!.map((x) => (x.key === b.key ? { ...x, ...patch } : x)))} />
          ))}
          <Button type="submit" loading={save.isPending}>Enregistrer</Button>
        </form>
      </Stack>
    </>
  );
}
