// Mouvement du registre des parts : type (aide selon le type), date, valeur nominale (types qui
// changent le capital), prix, pièce, lignes « associé, nature, reçoit / cède, parts », et
// situation après le mouvement calculée par le serveur (rien n'est enregistré avant validation).
import { useState } from "react";
import {
  ActionIcon, Alert, Button, FileInput, Group, Select, SegmentedControl, SimpleGrid, Table, Text, Textarea, TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, useAction, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { emptyMovement, forcedDirection, fromMovement, newLine, readyForPreview, toPayload, type MovementValues } from "./register";
import { ASSOCIATES_KEY, CAPITAL_KINDS, KIND_HELP, NATURES, type Movement, type MovementKind, type Nature, type RegisterMeta } from "./types";

interface PreviewRow { associate_id: number; name: string; parts: Record<Nature, number>; percent: Record<Nature, number> }

function Preview({ values, movementId }: { values: MovementValues; movementId?: number }) {
  const body = { ...toPayload(values), ...(movementId ? { id: movementId } : {}) };
  const ready = readyForPreview(values);
  const { data, error, isFetching } = useQuery({
    queryKey: [...ASSOCIATES_KEY, "preview", body], enabled: ready, retry: false, staleTime: 30_000,
    queryFn: () => api.post<{ rows: PreviewRow[]; total_parts: number }>("/api/v1/share-movements/preview", body, { redirect: false }),
  });
  if (!ready) return <Text size="sm" c="dimmed">Complétez les lignes pour voir la situation après le mouvement.</Text>;
  if (error) return <Alert color="paille" title="Mouvement refusé">{(error as ApiError).message}</Alert>;
  if (!data) return <Text size="sm" c="dimmed">{isFetching ? "Calcul…" : ""}</Text>;
  return (
    <div>
      <Text size="sm" fw={600} mb={4}>Situation après le mouvement ({data.total_parts.toLocaleString("fr-FR")} parts)</Text>
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Associé</Table.Th>
          {NATURES.map((n) => <Table.Th key={n.value} ta="right">{n.short}</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>
          {data.rows.map((r) => (
            <Table.Tr key={r.associate_id}><Table.Td>{r.name}</Table.Td>
              {NATURES.map((n) => <Table.Td key={n.value} ta="right" className="lv-num">
                {r.parts[n.value] ? `${r.parts[n.value].toLocaleString("fr-FR")} (${r.percent[n.value].toLocaleString("fr-FR")} %)` : "—"}
              </Table.Td>)}</Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}

export function MovementForm({ movement, meta, onDone }: { movement: Movement | null; meta: RegisterMeta | undefined; onDone: () => void }) {
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sending, setSending] = useState(false);
  const form = useForm<MovementValues>({
    initialValues: movement ? fromMovement(movement) : emptyMovement(new Date().toISOString().slice(0, 10)),
  });
  const json = useAction((values: MovementValues) => movement
    ? api.patch<{ notices: Notice[] }>(`/api/v1/share-movements/${movement.id}`, toPayload(values))
    : api.post<{ notices: Notice[] }>("/api/v1/share-movements", toPayload(values)),
  { invalidate: [ASSOCIATES_KEY], silent: true });
  const kind = form.values.kind;
  const forced = forcedDirection(kind);
  const lines = form.values.lines;
  const path = (i: number, field: string) => `lines.${i}.${field}`;

  const submit = async (values: MovementValues) => {
    setError(null);
    if (!file) {
      json.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) });
      return;
    }
    // Avec une pièce : formulaire multipart (POST, y compris pour une modification).
    const data = new FormData();
    data.append("payload", JSON.stringify(toPayload(values)));
    data.append("attachment", file);
    setSending(true);
    try {
      const body = await upload<{ notices: Notice[] }>(movement ? `/api/v1/share-movements/${movement.id}` : "/api/v1/share-movements", data);
      showNotices(body.notices);
      void client.invalidateQueries({ queryKey: ASSOCIATES_KEY });
      onDone();
    } catch (e) {
      setError(applyApiError(form, e));
    } finally {
      setSending(false);
    }
  };

  return (
    <form onSubmit={form.onSubmit((values) => void submit(values))}>
      <FormBody error={error} submitLabel={movement ? "Enregistrer" : "Inscrire au registre"} onCancel={onDone}
        loading={json.isPending || sending}>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Type de mouvement" data={meta?.kinds ?? []} allowDeselect={false} {...form.getInputProps("kind")}
            onChange={(v) => v && form.setFieldValue("kind", v as MovementKind)} />
          <TextInput label="Date" type="date" required {...form.getInputProps("movement_date")} />
        </SimpleGrid>
        <Text size="sm" c="dimmed">{KIND_HELP[kind]}</Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {CAPITAL_KINDS.includes(kind) && (
            <TextInput label="Valeur nominale d'une part (€)" required inputMode="decimal" classNames={{ input: "lv-num" }}
              {...form.getInputProps("nominal")} />
          )}
          <TextInput label="Prix ou valeur déclarée (€)" description="Facultatif, informatif." inputMode="decimal"
            classNames={{ input: "lv-num" }} {...form.getInputProps("price")} />
        </SimpleGrid>
        <div>
          <Text size="sm" fw={500} mb={4}>Lignes</Text>
          {typeof form.errors.lines === "string" && <Text size="xs" c="var(--lv-brique)" mb={4}>{form.errors.lines}</Text>}
          <Table verticalSpacing={4}>
            <Table.Tbody>
              {lines.map((_, i) => (
                <Table.Tr key={i}>
                  <Table.Td><Select aria-label={`Associé (ligne ${i + 1})`} placeholder="Associé" searchable w={200}
                    data={meta?.associates ?? []} {...form.getInputProps(path(i, "associate_id"))} /></Table.Td>
                  <Table.Td>{forced ? <Text size="sm" c="dimmed">{forced === "in" ? "reçoit" : "cède"}</Text> : (
                    <SegmentedControl size="xs" aria-label={`Sens (ligne ${i + 1})`}
                      data={[{ value: "in", label: "reçoit" }, { value: "out", label: "cède" }]}
                      {...form.getInputProps(path(i, "direction"))} />
                  )}</Table.Td>
                  <Table.Td><TextInput aria-label={`Parts (ligne ${i + 1})`} placeholder="Parts" w={90} inputMode="numeric"
                    classNames={{ input: "lv-num" }} {...form.getInputProps(path(i, "parts"))} /></Table.Td>
                  <Table.Td><Select aria-label={`Nature (ligne ${i + 1})`} w={170} allowDeselect={false}
                    data={NATURES.map((n) => ({ value: n.value, label: n.label }))} {...form.getInputProps(path(i, "nature"))} /></Table.Td>
                  <Table.Td><ActionIcon variant="subtle" color="red" aria-label={`Retirer la ligne ${i + 1}`}
                    disabled={lines.length === 1} onClick={() => form.removeListItem("lines", i)}><X size={16} /></ActionIcon></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Group mt={4}>
            <Button variant="default" size="compact-sm" leftSection={<Plus size={14} />}
              onClick={() => form.insertListItem("lines", newLine(forced ?? "in"))}>Ajouter une ligne</Button>
          </Group>
        </div>
        <Preview values={form.values} movementId={movement?.id} />
        <Textarea label="Description" autosize minRows={2} {...form.getInputProps("description")} />
        <FileInput label="Pièce (acte, statuts…)" placeholder={movement?.attachment ? `Actuelle : ${movement.attachment.name}` : "PDF, JPEG ou PNG"}
          clearable value={file} onChange={setFile} accept="application/pdf,image/jpeg,image/png" error={form.errors.attachment} />
      </FormBody>
    </form>
  );
}
