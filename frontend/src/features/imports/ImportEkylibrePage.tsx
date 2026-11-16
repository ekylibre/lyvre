// Imports › Sauvegarde Ekylibre (lot RE6, claudedocs/design_restauration_ekylibre.md) : dépôt d'une sauvegarde
// (zip, pièces comprises), analyse à blanc en tâche de fond (profil, période, contrôles, rapport), puis restauration
// tout-ou-rien dans l'instance courante, qui doit être vide. Administrateur, partie double.
import { useState } from "react";
import {
  Alert, Anchor, Badge, Button, Checkbox, Group, List, Paper, Progress, Radio, Select, SimpleGrid, Stack, Text, Title,
} from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, CircleAlert, CircleCheck, CircleX, Download } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { JobStatus, type Job } from "../../components/JobStatus";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";

interface Check { label: string; ok: boolean; blocking: boolean; details: string[]; more: number }
interface Analysis {
  profile: string[]; chart: string; detected_chart: string; period: { start: string; until: string }; years: number[];
  volumes: Record<string, number>; checks: Check[]; blocking: number; warnings: number;
  options: { from_year: number | null; all_history: boolean; attachments: boolean };
}
interface Overview {
  archive: { name: string; size: number; uploaded_at: string } | null;
  analysis: Analysis | null;
  imported: { name: string; at: string; period: { start: string; until: string }; stats: Record<string, number>; notes: number } | null;
  report: boolean; blockers: string[]; max_upload: number;
}

const KEY = ["imports", "ekylibre"];
const VOLUMES: [string, string][] = [
  ["entries", "Écritures"], ["purchases", "Factures d'achat"], ["sales", "Pièces de vente"],
  ["statement_items", "Lignes de relevé"], ["fixed_assets", "Immobilisations"], ["entities", "Tiers"],
  ["accounts", "Comptes"], ["activities", "Activités"],
];
const STATS: [string, string][] = [
  ["entries", "Écritures"], ["purchases", "Achats"], ["purchase_payments", "Règlements"], ["sales", "Ventes"],
  ["sale_payments", "Encaissements"], ["bank_transactions", "Transactions bancaires"], ["letterings", "Lettrages"],
  ["assets", "Immobilisations"], ["entities", "Tiers"], ["associates", "Associés"], ["attachments", "Pièces d'achat"],
  ["statement_files", "Relevés PDF"], ["activities", "Activités"], ["surfaces", "Surfaces"], ["stock_lines", "Lignes d'inventaire"],
];
const ANALYSIS_TITLES = { running: "Analyse en cours…", done: "Analyse terminée", failed: "L'analyse a échoué" };
const IMPORT_TITLES = { running: "Restauration en cours…", done: "Restauration terminée", failed: "La restauration a échoué" };

function size(bytes: number): string {
  return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} Go` : `${Math.max(1, Math.round(bytes / 1024 ** 2))} Mo`;
}

function CheckRow({ check }: { check: Check }) {
  const [Icon, color] = check.ok ? [CircleCheck, "var(--mantine-color-lichen-7)"]
    : check.blocking ? [CircleX, "var(--mantine-color-brique-7)"] : [CircleAlert, "var(--mantine-color-paille-8)"];
  return (
    <List.Item icon={<Icon size={18} color={color} aria-label={check.ok ? "passé" : check.blocking ? "bloquant" : "anomalie"} />}>
      <Text size="sm">{check.label}</Text>
      {!!check.details.length && <Text size="xs" c="dimmed">{check.details.join(" · ")}{check.more ? ` … (${check.more} de plus)` : ""}</Text>}
    </List.Item>
  );
}

function AnalysisCard({ analysis }: { analysis: Analysis }) {
  return (
    <Paper p="md">
      <Group justify="space-between" mb="xs">
        <Title order={3} size="h5">Analyse de la sauvegarde</Title>
        <Group gap="xs">
          <Badge variant="light" color={analysis.blocking ? "brique" : "lichen"}>
            {analysis.blocking ? `${analysis.blocking} contrôle(s) bloquant(s)` : "Contrôles bloquants passés"}</Badge>
          {!!analysis.warnings && <Badge variant="light" color="paille">{`${analysis.warnings} anomalie(s)`}</Badge>}
        </Group>
      </Group>
      <Text size="sm" mb="xs">{`Période reprise : du ${formatDate(analysis.period.start)} au ${formatDate(analysis.period.until)}`}</Text>
      {analysis.detected_chart !== analysis.chart &&
        <Alert color="paille" mb="sm">{`Ekylibre suggère le référentiel « ${analysis.detected_chart} », l'instance utilise « ${analysis.chart} » : la sauvegarde est reprise dans le référentiel de l'instance.`}</Alert>}
      <List size="sm" mb="sm" spacing={2}>{analysis.profile.map((line) => <List.Item key={line}>{line.replace(/\*\*|`/g, "")}</List.Item>)}</List>
      <SimpleGrid cols={{ base: 2, sm: 4 }} mb="md">
        {VOLUMES.map(([key, label]) => (
          <div key={key}><Text size="xs" c="dimmed">{label}</Text><Text fw={600} className="lv-num">{analysis.volumes[key] ?? 0}</Text></div>
        ))}
      </SimpleGrid>
      <Title order={4} size="h6" mb={4}>Contrôles</Title>
      <List spacing={6}>{analysis.checks.map((c) => <CheckRow key={c.label} check={c} />)}</List>
    </Paper>
  );
}

export default function ImportEkylibrePage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: () => api.get<{ item: Overview; job: Job | null }>("/api/v1/imports/ekylibre") });
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<"open" | "all" | "from">("open");
  const [fromYear, setFromYear] = useState<string | null>(null);
  const [attachments, setAttachments] = useState(true);
  const [job, setJob] = useState<Job | null>(null);
  const item = query.data?.item;
  const shownJob = job ?? (query.data?.job?.status === "running" ? query.data.job : null);
  const refresh = () => void client.invalidateQueries({ queryKey: KEY });

  const send = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    setError(null); setProgress(0); setJob(null);
    try {
      const body = await upload<{ notices: Notice[] }>("/api/v1/imports/ekylibre/upload", form, setProgress);
      showNotices(body.notices);
      refresh();
    } catch (e) { setError(e instanceof ApiError ? e.message : "Échec du dépôt."); } finally { setProgress(null); }
  };
  const options = () => ({ all_history: period === "all", from_year: period === "from" && fromYear ? Number(fromYear) : null, attachments });
  const start = async (path: "analyze" | "run") => {
    setError(null);
    try {
      const body = await api.post<{ job: Job }>(`/api/v1/imports/ekylibre/${path}`, options());
      setJob(body.job);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Échec."); }
  };
  const discard = async () => {
    const body = await api.delete<{ notices: Notice[] }>("/api/v1/imports/ekylibre");
    showNotices(body.notices); setJob(null); refresh();
  };

  if (!item) return <PageHeader title="Sauvegarde Ekylibre" />;
  const running = shownJob?.status === "running";
  const analysis = item.analysis;
  const blocked = !!item.blockers.length;
  return (
    <>
      <PageHeader title="Sauvegarde Ekylibre"
        description="Restaurez une sauvegarde téléchargée depuis Ekylibre : écritures, achats et ventes, banque, immobilisations, tiers, pièces de la période et, pour une exploitation, activités, surfaces et dernier inventaire. Rien n'est écrit tant que l'analyse signale un contrôle bloquant." />
      <Stack>
        {blocked && <Alert color="paille" title="Restauration impossible dans cette instance">
          <List size="sm">{item.blockers.map((b) => <List.Item key={b}>{b}</List.Item>)}</List>
          <Text size="sm" mt="xs">Vous pouvez tout de même analyser la sauvegarde.</Text></Alert>}
        {error && <Alert color="brique" role="alert">{error}</Alert>}
        {shownJob && <JobStatus key={shownJob.id} job={shownJob} onDone={refresh}
          titles={shownJob.kind === "ekylibre_restore" ? IMPORT_TITLES : ANALYSIS_TITLES}
          renderResult={(r) => <Text size="sm">{shownJob.kind === "ekylibre_restore"
            ? `${r.entries ?? 0} écriture(s), ${r.purchases ?? 0} achat(s), ${r.sales ?? 0} vente(s) et ${r.entities ?? 0} tiers repris ; ${r.notes ?? 0} remarque(s) dans le rapport.`
            : `${r.entries ?? 0} écriture(s) lue(s), ${r.blocking ?? 0} contrôle(s) bloquant(s), ${r.warnings ?? 0} anomalie(s) signalée(s).`}</Text>} />}

        <Paper p="md">
          <Title order={3} size="h5" mb="xs">1. Sauvegarde</Title>
          {item.archive ? (
            <Group justify="space-between">
              <div><Text fw={600}>{item.archive.name}</Text>
                <Text size="xs" c="dimmed">{`${size(item.archive.size)}, déposée le ${formatDate(item.archive.uploaded_at)}`}</Text></div>
              <Button variant="subtle" color="brique" onClick={() => void discard()} disabled={running}>Retirer du serveur</Button>
            </Group>
          ) : (
            <Dropzone onDrop={(files) => { if (files[0]) void send(files[0]); }} multiple={false} loading={progress !== null}
              accept={{ "application/zip": [".zip"] }} maxSize={item.max_upload}>
              <Group justify="center" gap="sm" mih={90}><ArchiveRestore size={28} />
                <div><Text>Déposez la sauvegarde Ekylibre (.zip)</Text>
                  <Text size="xs" c="dimmed">{`Jusqu'à ${size(item.max_upload)}, pièces jointes comprises. Ekylibre › Paramétrage › Sauvegardes.`}</Text></div></Group>
            </Dropzone>
          )}
          {progress !== null && <Progress value={progress} mt="sm" animated aria-label="Dépôt" />}
        </Paper>

        {item.archive && (
          <Paper p="md">
            <Title order={3} size="h5" mb="xs">2. Période et pièces</Title>
            <Radio.Group value={period} onChange={(v) => setPeriod(v as typeof period)} mb="sm">
              <Stack gap={6}>
                <Radio value="open" label="À partir du premier exercice ouvert dans Ekylibre (recommandé), à-nouveaux calculés" />
                <Radio value="from" label="À partir d'une année choisie" />
                <Radio value="all" label="Tout l'historique" />
              </Stack>
            </Radio.Group>
            {period === "from" && <Select w={160} mb="sm" label="Première année" data={(analysis?.years ?? []).map(String)}
              value={fromYear} onChange={setFromYear} placeholder={analysis ? "Choisir" : "Analysez d'abord"} disabled={!analysis} />}
            <Checkbox label="Reprendre les pièces de la période (factures d'achat, relevés bancaires PDF)" checked={attachments}
              onChange={(e) => setAttachments(e.currentTarget.checked)} mb="md" />
            <Group>
              <Button variant="default" onClick={() => void start("analyze")} loading={running && shownJob?.kind !== "ekylibre_restore"} disabled={running}>
                {analysis ? "Analyser à nouveau" : "Analyser"}</Button>
              {item.report && <Anchor href="/api/v1/imports/ekylibre/report" download size="sm"><Group gap={4}><Download size={16} />Rapport détaillé (Markdown)</Group></Anchor>}
            </Group>
          </Paper>
        )}

        {analysis && <AnalysisCard analysis={analysis} />}

        {analysis && item.archive && (
          <Paper p="md">
            <Title order={3} size="h5" mb="xs">3. Restauration</Title>
            <Text size="sm" mb="sm">Tout ou rien : en cas d'échec, l'instance reste vide. La restauration dure de quelques secondes à quelques minutes ; vous pouvez quitter l'écran, une notification annoncera la fin.</Text>
            <Button leftSection={<ArchiveRestore size={16} />} onClick={() => void start("run")}
              disabled={running || blocked || !!analysis.blocking} loading={running && shownJob?.kind === "ekylibre_restore"}>
              Restaurer dans cette instance</Button>
          </Paper>
        )}

        {item.imported && (
          <Paper p="md">
            <Group justify="space-between" mb="xs"><Title order={3} size="h5">Dernière restauration</Title>
              {item.report && <Anchor href="/api/v1/imports/ekylibre/report" download size="sm">Rapport d'import</Anchor>}</Group>
            <Text size="sm" mb="sm">{`${item.imported.name}, le ${formatDate(item.imported.at)} : du ${formatDate(item.imported.period.start)} au ${formatDate(item.imported.period.until)}.`}</Text>
            <SimpleGrid cols={{ base: 2, sm: 4 }}>
              {STATS.filter(([key]) => item.imported?.stats[key]).map(([key, label]) => (
                <div key={key}><Text size="xs" c="dimmed">{label}</Text><Text fw={600} className="lv-num">{item.imported?.stats[key]}</Text></div>
              ))}
            </SimpleGrid>
            {!!item.imported.notes && <Text size="xs" c="dimmed" mt="sm">{`${item.imported.notes} remarque(s) détaillée(s) dans le rapport.`}</Text>}
          </Paper>
        )}
      </Stack>
    </>
  );
}
