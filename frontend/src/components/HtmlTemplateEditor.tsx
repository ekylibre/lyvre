// Éditeur d'un texte HTML à champs (modèles de bail, texte d'un bail) : mise en forme (Tiptap) ou
// source HTML, insertion d'un champ « {{ … }} ». La mise en forme ne connaît pas les tableaux : un
// texte qui en contient s'ouvre en source HTML.
import { useState } from "react";
import { Alert, Group, SegmentedControl, Select, Stack, Textarea } from "@mantine/core";
import { RichTextEditor } from "@mantine/tiptap";
import "@mantine/tiptap/styles.css";
import { useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useMutation } from "@tanstack/react-query";
import { postBlob } from "../api/client";

export interface FieldOption { value: string; label: string }

export function HtmlTemplateEditor({ initial, onChange, fields = [], label }: {
  initial: string; onChange: (html: string) => void; fields?: FieldOption[]; label: string;
}) {
  const hasTable = /<table/i.test(initial);
  const [mode, setMode] = useState<"rich" | "source">(hasTable ? "source" : "rich");
  const [source, setSource] = useState(initial);
  const editor = useEditor({
    extensions: [StarterKit.configure({ link: false })],
    content: hasTable ? "" : initial,
    onUpdate: ({ editor: e }) => { const html = e.getHTML(); setSource(html); onChange(html); },
    immediatelyRender: true,
  });
  const insert = (field: string | null) => {
    if (!field) return;
    if (mode === "rich") editor?.chain().focus().insertContent(field).run();
    else { const next = `${source}${field}`; setSource(next); onChange(next); }
  };
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        {fields.length > 0 ? <Select aria-label="Insérer un champ" placeholder="Insérer un champ…" searchable w={300}
          data={fields} value={null} onChange={insert} /> : <span />}
        <SegmentedControl size="xs" value={mode} onChange={(v) => {
          if (v === "rich") editor?.commands.setContent(source);
          setMode(v as "rich" | "source");
        }} data={[{ value: "rich", label: "Mise en forme" }, { value: "source", label: "Source HTML" }]} />
      </Group>
      {mode === "rich" && /<table/i.test(source) && (
        <Alert color="brique" variant="light">La mise en forme ne garde pas les tableaux : retouchez ce texte en source HTML.</Alert>
      )}
      {mode === "rich" ? (
        <RichTextEditor editor={editor}>
          <RichTextEditor.Toolbar sticky>
            <RichTextEditor.ControlsGroup><RichTextEditor.H1 /><RichTextEditor.H2 /><RichTextEditor.H3 /></RichTextEditor.ControlsGroup>
            <RichTextEditor.ControlsGroup><RichTextEditor.Bold /><RichTextEditor.Italic /><RichTextEditor.Underline /></RichTextEditor.ControlsGroup>
            <RichTextEditor.ControlsGroup><RichTextEditor.BulletList /><RichTextEditor.OrderedList /></RichTextEditor.ControlsGroup>
          </RichTextEditor.Toolbar>
          <RichTextEditor.Content mih={420} />
        </RichTextEditor>
      ) : (
        <Textarea aria-label={label} classNames={{ input: "lv-num" }} autosize minRows={18} maxRows={40} value={source}
          onChange={(e) => { setSource(e.currentTarget.value); onChange(e.currentTarget.value); }} />
      )}
    </Stack>
  );
}

/** Aperçu PDF d'un texte non enregistré (POST) : onglet ouvert tout de suite (pas de blocage des
 * fenêtres), rempli quand le PDF arrive, refermé sur erreur (notifiée comme toute mutation). */
export function usePdfPreview() {
  return useMutation({
    mutationFn: async ({ url, body }: { url: string; body: unknown }) => {
      const tab = window.open("", "_blank");
      try {
        const blob = await postBlob(url, body);
        if (tab) tab.location.href = URL.createObjectURL(blob);
      } catch (error) {
        tab?.close();
        throw error;
      }
    },
  });
}
