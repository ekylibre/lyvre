// Temps de travaux › Import d'un fichier CSV (séparateur ;) ou XLSX.
import { useState } from "react";
import { Alert, Button, Group, List, Paper, Progress, Stack, Text } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet } from "lucide-react";
import { ApiError } from "../../api/client";
import { showNotices, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { WORK_TIMES_KEY } from "./WorkTimesPage";

interface ImportResult { imported: number; skipped: number; errors: string[] }

const ACCEPT = {
  "text/csv": [".csv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.ms-excel": [".xls", ".csv"],
};

export default function WorkTimesImportPage() {
  const client = useQueryClient();
  const [progress, setProgress] = useState<number | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    setError(null);
    setResult(null);
    setProgress(0);
    try {
      const body = await upload<{ result: ImportResult; notices: Notice[] }>("/api/v1/work-times/import", form, setProgress);
      setResult(body.result);
      showNotices(body.notices);
      void client.invalidateQueries({ queryKey: WORK_TIMES_KEY });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "L'import a échoué.");
    } finally {
      setProgress(null);
    }
  };

  return (
    <>
      <PageHeader title="Importer des temps de travaux" description="Une ligne par temps : le bénévole et le type de tâche doivent exister."
        actions={<Button variant="default" component={AppLink} href="/work-times/">Retour aux temps</Button>} />
      <Stack maw={720}>
        <Dropzone onDrop={(files) => files[0] && void send(files[0])} accept={ACCEPT} multiple={false}
          loading={progress !== null} onReject={() => setError("Fichier refusé : CSV ou XLSX attendu.")}>
          <Group justify="center" mih={140} style={{ pointerEvents: "none" }}>
            <FileSpreadsheet size={36} />
            <div>
              <Text fw={600}>Déposer le fichier ici ou cliquer pour le choisir</Text>
              <Text size="sm" c="dimmed">CSV (séparateur ;) ou XLSX.</Text>
            </div>
          </Group>
        </Dropzone>
        {progress !== null && <Progress value={progress} aria-label="Envoi du fichier" />}
        <Text size="sm" c="dimmed">
          Colonnes : <span className="lv-num">Bénévole</span> (nom ou email), <span className="lv-num">Type de tâche</span>,{" "}
          <span className="lv-num">Date</span> (JJ/MM/AAAA ou AAAA-MM-JJ), <span className="lv-num">Heures</span> (2,5),{" "}
          <span className="lv-num">Notes</span> (facultatif).
        </Text>
        {error && <Alert color="brique" role="alert">{error}</Alert>}
        {result && (
          <Paper p="md">
            <Text fw={600}>{result.imported} temps importé(s), {result.skipped} ligne(s) ignorée(s), {result.errors.length} erreur(s).</Text>
            {result.errors.length > 0 && (
              <Alert color="paille" mt="sm" title="Lignes non importées">
                <List size="sm">{result.errors.map((e) => <List.Item key={e}>{e}</List.Item>)}</List>
              </Alert>
            )}
          </Paper>
        )}
      </Stack>
    </>
  );
}
