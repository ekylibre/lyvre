// Adhérents › Message de relance : sujet, corps (éditeur riche ou source HTML), variables,
// aperçu rendu par le serveur avec un adhérent réel (ou fictif).
import { useEffect, useState } from "react";
import { Alert, Badge, Button, Grid, Group, Paper, SegmentedControl, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { Link, RichTextEditor } from "@mantine/tiptap";
import "@mantine/tiptap/styles.css";
import { useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { AppLink } from "../../app/navigation";

interface Preview { subject: string; body_html: string; error: string | null; sample: { name: string; email: string; real: boolean } }
interface TemplateResponse { item: { subject: string; body_html: string }; preview: Preview }

const VARIABLES = [
  { label: "Nom", value: "{{ nom }}" }, { label: "Email", value: "{{ email }}" },
  { label: "Date anniversaire", value: "{{ date_anniversaire }}" },
];
const LINK_PLACEHOLDER = "{{ lien_helloasso }}";

function Editor({ initial, onChange }: { initial: string; onChange: (html: string) => void }) {
  const [mode, setMode] = useState<"rich" | "source">("rich");
  const [source, setSource] = useState(initial);
  const editor = useEditor({
    // Les variables du gabarit ({{ lien_helloasso }}) sont des liens valides ici.
    extensions: [StarterKit.configure({ link: false }),
      Link.configure({ openOnClick: false, isAllowedUri: (url, ctx) => url.startsWith("{{") || ctx.defaultValidate(url) })],
    content: initial,
    onUpdate: ({ editor: e }) => { const html = e.getHTML(); setSource(html); onChange(html); },
    immediatelyRender: true,
  });
  const insert = (text: string) => editor?.chain().focus().insertContent(text).run();
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Group gap={6}>
          {VARIABLES.map((v) => <Button key={v.value} size="compact-sm" variant="default" disabled={mode === "source"}
            onClick={() => insert(v.value)}>{`Insérer ${v.label.toLowerCase()}`}</Button>)}
          <Button size="compact-sm" variant="default" disabled={mode === "source"}
            onClick={() => editor?.chain().focus().extendMarkRange("link").setLink({ href: LINK_PLACEHOLDER }).run()}>
            Lier au renouvellement HelloAsso</Button>
        </Group>
        <SegmentedControl size="xs" value={mode} onChange={(v) => {
          if (v === "rich") editor?.commands.setContent(source);
          setMode(v as "rich" | "source");
        }} data={[{ value: "rich", label: "Mise en forme" }, { value: "source", label: "Source HTML" }]} />
      </Group>
      {mode === "rich" ? (
        <RichTextEditor editor={editor}>
          <RichTextEditor.Toolbar>
            <RichTextEditor.ControlsGroup><RichTextEditor.Bold /><RichTextEditor.Italic /><RichTextEditor.Underline /></RichTextEditor.ControlsGroup>
            <RichTextEditor.ControlsGroup><RichTextEditor.BulletList /><RichTextEditor.OrderedList /></RichTextEditor.ControlsGroup>
            <RichTextEditor.ControlsGroup><RichTextEditor.Link /><RichTextEditor.Unlink /></RichTextEditor.ControlsGroup>
          </RichTextEditor.Toolbar>
          <RichTextEditor.Content mih={220} />
        </RichTextEditor>
      ) : (
        <Textarea aria-label="Source HTML du message" classNames={{ input: "lv-num" }} autosize minRows={10} value={source}
          onChange={(e) => { setSource(e.currentTarget.value); onChange(e.currentTarget.value); }} />
      )}
    </Stack>
  );
}

export default function ReminderTemplatePage() {
  const { data } = useQuery({ queryKey: ["reminder-template"],
    queryFn: () => api.get<TemplateResponse>("/api/v1/members/reminder-template") });
  const [subject, setSubject] = useState<string | null>(null);
  const [body, setBody] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const currentSubject = subject ?? data?.item.subject ?? "";
  const currentBody = body ?? data?.item.body_html ?? "";
  const [debounced] = useDebouncedValue(`${currentSubject}\u0000${currentBody}`, 500);
  useEffect(() => {
    if (!data || (subject === null && body === null)) return;
    const [s, b] = debounced.split("\u0000");
    void api.post<{ preview: Preview }>("/api/v1/members/reminder-template/preview", { subject: s, body_html: b })
      .then((r) => setPreview(r.preview));
  }, [debounced, data, subject, body]);
  const save = useAction(() => api.put<{ notices: Notice[] }>("/api/v1/members/reminder-template",
    { subject: currentSubject, body_html: currentBody }), { invalidate: [["reminder-template"]] });
  const shown = preview ?? data?.preview;

  return (
    <>
      <PageHeader title="Message de relance" description="Envoyé aux adhérents dont l'adhésion est échue."
        actions={<>
          <Button variant="default" component={AppLink} href="/entities/members/reminders">Retour aux relances</Button>
          <Can><Button loading={save.isPending} disabled={!data} onClick={() => save.mutate(undefined)}>Enregistrer le message</Button></Can>
        </>} />
      {data && (
        <Grid gap="lg">
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <Stack>
              <TextInput label="Sujet" required value={currentSubject} onChange={(e) => setSubject(e.currentTarget.value)} />
              <Editor initial={data.item.body_html} onChange={setBody} />
              <Text size="sm" c="dimmed">Variables : <span className="lv-num">{"{{ nom }}"}</span>, <span className="lv-num">{"{{ email }}"}</span>,{" "}
                <span className="lv-num">{"{{ date_anniversaire }}"}</span>, <span className="lv-num">{LINK_PLACEHOLDER}</span>.</Text>
            </Stack>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <Paper p="md">
              <Group justify="space-between" mb="xs">
                <Text fw={600}>Aperçu</Text>
                {shown && <Badge variant="light" color={shown.sample.real ? "lichen" : "gray"} tt="none">
                  {shown.sample.real ? `Données réelles : ${shown.sample.name}` : "Exemple fictif"}</Badge>}
              </Group>
              {shown?.error ? (
                <Alert color="brique" role="alert">Le message ne peut pas être rendu : {shown.error}</Alert>
              ) : shown && (
                <Stack gap={4}>
                  <Text size="sm"><b>À :</b> {shown.sample.email}</Text>
                  <Text size="sm"><b>Objet :</b> {shown.subject}</Text>
                  {/* Aperçu isolé : aucun script, aucune requête vers l'application. */}
                  <iframe title="Aperçu de l'email" sandbox="" srcDoc={shown.body_html}
                    style={{ width: "100%", minHeight: 360, border: "1px solid var(--lv-line)", borderRadius: 10, background: "#fff" }} />
                </Stack>
              )}
            </Paper>
          </Grid.Col>
        </Grid>
      )}
    </>
  );
}
