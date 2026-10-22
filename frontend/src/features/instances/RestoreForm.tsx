// Restauration d'une instance depuis un fichier : la base (et avec une archive .zip, les pièces
// jointes) est remplacée ; confirmation forte en saisissant le slug de l'instance.
import { useState } from "react";
import { Alert, Button, Code, Group, Progress, Stack, Text, TextInput } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { FileUp } from "lucide-react";
import { ApiError } from "../../api/client";
import { showNotices, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { BACKUP_ACCEPT, megabytes } from "./types";

export function BackupDrop({ file, onFile }: { file: File | null; onFile: (file: File) => void }) {
  return (
    <Dropzone onDrop={(files) => files[0] && onFile(files[0])} multiple={false} accept={BACKUP_ACCEPT} maxSize={500 * 1024 * 1024}>
      <Group justify="center" mih={90} style={{ pointerEvents: "none" }}>
        <FileUp size={28} />
        <div>
          <Text fw={600}>{file ? `${file.name} (${megabytes(file.size)})` : "Déposer le fichier ici ou cliquer pour le choisir"}</Text>
          <Text size="sm" c="dimmed">Archive .zip (base et pièces jointes) ou ancienne sauvegarde .db (base seule) ; 500 Mo au plus.</Text>
        </div>
      </Group>
    </Dropzone>
  );
}

export function RestoreForm({ instance, onDone, onCancel }: {
  instance: { id: number; slug: string; label: string }; onDone: () => void; onCancel: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [confirm, setConfirm] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ready = file !== null && confirm === instance.slug;

  const send = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("backup_file", file);
    form.append("confirm", confirm);
    setError(null); setProgress(0);
    try {
      const body = await upload<{ notices: Notice[] }>(`/api/v1/instances/${instance.id}/restore`, form, setProgress);
      showNotices(body.notices);
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "La restauration a échoué.");
    } finally {
      setProgress(null);
    }
  };

  return (
    <Stack>
      <Alert color="paille" title="La base actuelle sera écrasée">
        Avec une archive .zip, les pièces jointes de l'instance (factures d'achat) sont aussi remplacées. Une sauvegarde de
        sécurité (pre-restore-…, base et pièces) est créée automatiquement avant l'opération.
      </Alert>
      <BackupDrop file={file} onFile={setFile} />
      <TextInput label={<>Saisissez <Code>{instance.slug}</Code> pour confirmer</>} value={confirm} autoComplete="off"
        classNames={{ input: "lv-num" }} onChange={(e) => setConfirm(e.currentTarget.value.trim())} />
      {progress !== null && <Progress value={progress} aria-label="Envoi du fichier" />}
      {error && <Alert color="brique" role="alert">{error}</Alert>}
      <Group justify="flex-end">
        <Button variant="default" onClick={onCancel}>Annuler</Button>
        <Button color="brique" disabled={!ready} loading={progress !== null} onClick={() => void send()}>
          Restaurer {instance.label}</Button>
      </Group>
    </Stack>
  );
}
