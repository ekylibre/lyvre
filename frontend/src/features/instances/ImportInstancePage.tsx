// Administration › Importer une instance : un fichier de sauvegarde crée une nouvelle instance,
// ou restaure l'instance existante de même slug (confirmation forte : saisir le slug). À la
// création seulement, utilisateurs et rôles de la nouvelle instance (une restauration garde les accès).
import { useState } from "react";
import { Alert, Button, Code, Group, List, Progress, Stack, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { showNotices, useList, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { PageHeader } from "../../components/PageHeader";
import { AppLink, useGoTo } from "../../app/navigation";
import { MembersEditor } from "../access/MembersEditor";
import { memberRowErrors, toMembersPayload, type MemberRow, type RoleOption, type UserOption } from "../access/members";
import { BackupDrop } from "./RestoreForm";
import { INSTANCES_KEY, labelFromSlug, slugFromFilename, type Instance } from "./types";

export default function ImportInstancePage() {
  const client = useQueryClient();
  const goTo = useGoTo();
  const [file, setFile] = useState<File | null>(null);
  const [slug, setSlug] = useState("");
  const [label, setLabel] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null);  // null : pas de restauration annoncée
  const [restoreMessage, setRestoreMessage] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: instances } = useList<Instance>(INSTANCES_KEY, "/api/v1/instances");
  const { data: users } = useList<UserOption, { roles: RoleOption[] }>(["users"], "/api/v1/users");
  const members = useForm({ initialValues: { members: [] as MemberRow[] } });
  // Slug connu : restauration, accès inchangés ; sinon création avec ses utilisateurs.
  const creating = !!slug && !(instances?.items ?? []).some((i) => i.slug === slug) && restoreMessage === null;

  const choose = (f: File) => {
    setFile(f); setConfirm(null); setRestoreMessage(null); setError(null);
    const derived = slugFromFilename(f.name);
    if (!slug) setSlug(derived);
    if (!label && derived) setLabel(labelFromSlug(derived));
  };

  const send = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("backup_file", file);
    form.append("slug", slug);
    form.append("label", label);
    if (confirm !== null) form.append("confirm", confirm);
    if (creating && members.getValues().members.length) {
      const rowErrors = memberRowErrors(members.getValues().members);
      if (Object.keys(rowErrors).length) { members.setErrors(rowErrors); return; }
      form.append("members", JSON.stringify(toMembersPayload(members.getValues().members)));
    }
    setError(null); setProgress(0);
    try {
      const body = await upload<{ item: Instance; notices: Notice[] }>("/api/v1/instances/import", form, setProgress);
      showNotices(body.notices);
      void client.invalidateQueries({ queryKey: INSTANCES_KEY });
      void client.invalidateQueries({ queryKey: ["users"] });
      goTo(`/instances/${body.item.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "confirmation_required") {
        setRestoreMessage(e.message); setConfirm("");
      } else if (e instanceof ApiError && Object.keys(e.fields ?? {}).some((f) => f.startsWith("members"))) {
        members.setErrors(e.fields);
        setError(e.message);
      } else {
        setError(e instanceof ApiError ? e.message : "L'import a échoué.");
      }
    } finally {
      setProgress(null);
    }
  };

  return (
    <>
      <PageHeader title="Importer une instance" actions={<Button variant="default" component={AppLink} href="/instances/">Instances</Button>} />
      <Stack maw={720}>
        <Alert color="ardoise" variant="light">
          <List size="sm">
            <List.Item>Slug d'une instance existante : <b>restauration</b> de cette instance (sauvegarde de sécurité créée avant).</List.Item>
            <List.Item>Sinon : <b>création</b> d'une instance qui utilise le fichier comme base.</List.Item>
          </List>
        </Alert>
        <BackupDrop file={file} onFile={choose} />
        <TextInput label="Slug" description="Déduit du nom du fichier ; lettres minuscules, chiffres et tirets." value={slug}
          classNames={{ input: "lv-num" }} onChange={(e) => { setSlug(e.currentTarget.value.trim().toLowerCase()); setConfirm(null); setRestoreMessage(null); }} />
        <TextInput label="Libellé" description="Création seulement." value={label} onChange={(e) => setLabel(e.currentTarget.value)} />
        {creating && <MembersEditor form={members} users={users?.items ?? []} roles={users?.meta?.roles ?? []} />}
        {restoreMessage && (
          <Alert color="paille" title="Restauration d'une instance existante">
            {restoreMessage}
            <TextInput mt="xs" label={<>Saisissez <Code>{slug}</Code> pour confirmer</>} value={confirm ?? ""} autoComplete="off"
              classNames={{ input: "lv-num" }} onChange={(e) => setConfirm(e.currentTarget.value.trim())} />
          </Alert>
        )}
        {progress !== null && <Progress value={progress} aria-label="Envoi du fichier" />}
        {error && <Alert color="brique" role="alert">{error}</Alert>}
        <Group>
          <Button disabled={!file || (confirm !== null && confirm !== slug)} loading={progress !== null} onClick={() => void send()}
            color={restoreMessage ? "brique" : undefined}>{restoreMessage ? "Restaurer l'instance" : "Importer"}</Button>
        </Group>
      </Stack>
    </>
  );
}
