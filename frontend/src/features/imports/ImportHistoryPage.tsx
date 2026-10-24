// Imports › Reprise d'historique (lot F6, administrateur) : FEC d'un autre logiciel (historique
// complet d'un exercice, ou soldes d'ouverture) et écritures d'un tableur (CSV, XLSX) ; analyse,
// correspondance des comptes, puis import tout-ou-rien.
import { useState } from "react";
import {
  Alert, Badge, Button, Group, List, Paper, Radio, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, TextInput, Title,
} from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { useCurrentSession } from "../../api/session";
import { AccountSelect } from "../../components/AccountSelect";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import type { Account } from "../../lib/types";

interface PlanRow { key: string; code: string; label: string; aux: string; aux_label: string; action: "existing" | "mapped" | "create"; account_id: number | null; target_code: string | null }
interface FecAnalysis {
  entries: number; lines: number; debit_cents: number; credit_cents: number; first_date: string; last_date: string;
  fiscal_year: { start_date: string; end_date: string }; journals: { code: string; exists: boolean }[]; letterings: number;
  accounts: PlanRow[]; problems: string[]; to_create: number;
}
interface SheetAnalysis {
  headers: string[]; mapping: Record<string, string>; sample: string[][]; rows: number; fields: { value: string; label: string }[];
  entries: number; problems: string[]; accounts: PlanRow[]; to_create?: number; profiles: { id: number; name: string; mapping: Record<string, string> }[];
}

const ACTION = { existing: ["lichen", "existant"], mapped: ["ardoise", "correspondance"], create: ["paille", "à créer"] } as const;

function problemsOf(error: unknown): string[] {
  return error instanceof ApiError && Array.isArray(error.details?.problems) ? (error.details.problems as string[]) : [];
}

function Problems({ items }: { items: string[] }) {
  return items.length ? <Alert color="brique" role="alert" title={`${items.length} anomalie(s)`}>
    <List size="sm">{items.slice(0, 15).map((p) => <List.Item key={p}>{p}</List.Item>)}</List></Alert> : null;
}

function AccountsTable({ rows, overrides, setOverrides, scope }: {
  rows: PlanRow[]; overrides: Record<string, Account | null>; setOverrides: (o: Record<string, Account | null>) => void; scope: string;
}) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.filter((r) => r.action !== "existing");
  return (
    <Paper p={0}>
      <Group justify="space-between" p="sm"><Title order={3} size="h5">{`Comptes du fichier (${rows.length})`}</Title>
        <Button size="compact-sm" variant="subtle" onClick={() => setAll(!all)}>{all ? "Masquer les comptes existants" : "Tout afficher"}</Button></Group>
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Fichier</Table.Th><Table.Th>Lyvre</Table.Th><Table.Th>Correspondance</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{shown.map((r) => (
          <Table.Tr key={r.key}>
            <Table.Td><Text size="sm" className="lv-num">{r.aux ? `${r.code} / ${r.aux}` : r.code}</Text>
              <Text size="xs" c="dimmed">{r.aux_label || r.label}</Text></Table.Td>
            <Table.Td><Badge variant="light" color={ACTION[r.action][0]}>{ACTION[r.action][1]}</Badge>{" "}
              <Text span size="sm" className="lv-num">{r.target_code}</Text></Table.Td>
            <Table.Td w={320}><AccountSelect label="Correspondance" recentsScope={scope} value={overrides[r.key] ?? null}
              onChange={(account) => setOverrides({ ...overrides, [r.key]: account })} /></Table.Td>
          </Table.Tr>
        ))}</Table.Tbody>
      </Table>
      {!shown.length && <Text size="sm" c="dimmed" p="sm">Tous les comptes du fichier existent dans le plan.</Text>}
    </Paper>
  );
}

function mappingsField(overrides: Record<string, Account | null>) {
  return JSON.stringify(Object.fromEntries(Object.entries(overrides).filter(([, a]) => a).map(([k, a]) => [k, a!.id])));
}

function FecImport({ scope }: { scope: string }) {
  const client = useQueryClient();
  const years = useQuery({ queryKey: ["fiscal-years"], queryFn: () => api.get<{ items: { id: number; label: string; closed: boolean }[] }>("/api/v1/fiscal-years") });
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<FecAnalysis | null>(null);
  const [overrides, setOverrides] = useState<Record<string, Account | null>>({});
  const [mode, setMode] = useState<"history" | "opening">("history");
  const [dates, setDates] = useState({ start: "", end: "" });
  const [target, setTarget] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const analyze = async (chosen: File, current = overrides) => {
    const form = new FormData();
    form.append("file", chosen);
    form.append("mappings", mappingsField(current));
    setBusy(true); setError(null);
    try {
      const result = await upload<FecAnalysis>("/api/v1/imports/fec/analyze", form);
      setAnalysis(result);
      setDates({ start: result.fiscal_year.start_date, end: result.fiscal_year.end_date });
    } catch (e) { setError(e); setAnalysis(null); } finally { setBusy(false); }
  };
  const run = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("mode", mode);
    form.append("mappings", mappingsField(overrides));
    if (mode === "history") { form.append("start_date", dates.start); form.append("end_date", dates.end); }
    else form.append("fiscal_year_id", target ?? "");
    setBusy(true); setError(null);
    try {
      const body = await upload<{ notices: Notice[] }>("/api/v1/imports/fec", form);
      showNotices(body.notices);
      setAnalysis(null); setFile(null);
      void client.invalidateQueries();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return (
    <Stack>
      <Dropzone onDrop={(files) => { if (files[0]) { setFile(files[0]); setOverrides({}); void analyze(files[0], {}); } }} multiple={false} loading={busy}>
        <Group justify="center" gap="sm" mih={80}><FileUp size={28} /><Text>{file ? file.name : "Déposez le FEC (.txt, tabulation ou barre verticale)"}</Text></Group>
      </Dropzone>
      {error != null && <Alert color="brique" role="alert">{error instanceof ApiError ? error.message : "Échec."}</Alert>}
      <Problems items={problemsOf(error)} />
      {analysis && <>
        <SimpleGrid cols={{ base: 2, md: 4 }}>
          <Paper p="sm"><Text size="sm" c="dimmed">Écritures</Text><Text fw={700}>{`${analysis.entries} (${analysis.lines} lignes)`}</Text></Paper>
          <Paper p="sm"><Text size="sm" c="dimmed">Total débit</Text><MoneyText cents={analysis.debit_cents} fw={700} /></Paper>
          <Paper p="sm"><Text size="sm" c="dimmed">Période</Text><Text fw={700}>{`${formatDate(analysis.first_date)} → ${formatDate(analysis.last_date)}`}</Text></Paper>
          <Paper p="sm"><Text size="sm" c="dimmed">Lettrages</Text><Text fw={700}>{analysis.letterings}</Text></Paper>
        </SimpleGrid>
        <Problems items={analysis.problems} />
        <AccountsTable rows={analysis.accounts} overrides={overrides} setOverrides={setOverrides} scope={scope} />
        <Group><Button variant="default" onClick={() => file && analyze(file)} loading={busy}>Réanalyser avec ces correspondances</Button></Group>
        <Paper p="md">
          <Radio.Group label="Que reprendre ?" value={mode} onChange={(v) => setMode(v as "history" | "opening")}>
            <Stack gap={6} mt={6}>
              <Radio value="history" label="L'historique complet de l'exercice (écritures validées, exercice clôturé provisoirement)" />
              <Radio value="opening" label="Seulement les soldes, en à-nouveaux du premier exercice Lyvre" />
            </Stack>
          </Radio.Group>
          {mode === "history" ? (
            <SimpleGrid cols={2} mt="sm">
              <TextInput label="Début de l'exercice" type="date" value={dates.start} onChange={(e) => setDates({ ...dates, start: e.currentTarget.value })} />
              <TextInput label="Fin de l'exercice" type="date" value={dates.end} onChange={(e) => setDates({ ...dates, end: e.currentTarget.value })} />
            </SimpleGrid>
          ) : (
            <Select mt="sm" label="Exercice qui reçoit les à-nouveaux" value={target} onChange={setTarget}
              data={(years.data?.items ?? []).filter((y) => !y.closed).map((y) => ({ value: String(y.id), label: y.label }))} />
          )}
          <Group mt="md"><Button onClick={run} loading={busy} disabled={!!analysis.problems.length || (mode === "opening" && !target)}>
            {`Importer (${analysis.to_create} compte(s) à créer)`}</Button></Group>
        </Paper>
      </>}
    </Stack>
  );
}

function SheetImport({ scope }: { scope: string }) {
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<SheetAnalysis | null>(null);
  const [columns, setColumns] = useState<Record<string, string>>({});
  const [overrides, setOverrides] = useState<Record<string, Account | null>>({});
  const [profile, setProfile] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const analyze = async (chosen: File, cols: Record<string, string> | null) => {
    const form = new FormData();
    form.append("file", chosen);
    if (cols) form.append("columns", JSON.stringify(cols));
    form.append("mappings", mappingsField(overrides));
    setBusy(true); setError(null);
    try {
      const result = await upload<SheetAnalysis>("/api/v1/imports/sheet/analyze", form);
      setAnalysis(result); setColumns(result.mapping);
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const run = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("columns", JSON.stringify(columns));
    form.append("mappings", mappingsField(overrides));
    if (profile.trim()) form.append("profile_name", profile.trim());
    setBusy(true); setError(null);
    try {
      const body = await upload<{ notices: Notice[] }>("/api/v1/imports/sheet", form);
      showNotices(body.notices);
      setAnalysis(null); setFile(null);
      void client.invalidateQueries();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const headers = (analysis?.headers ?? []).map((h) => ({ value: h, label: h }));
  return (
    <Stack>
      <Dropzone onDrop={(files) => { if (files[0]) { setFile(files[0]); void analyze(files[0], null); } }} multiple={false} loading={busy}>
        <Group justify="center" gap="sm" mih={80}><FileUp size={28} /><Text>{file ? file.name : "Déposez le fichier (CSV ou XLSX, une ligne par ligne d'écriture)"}</Text></Group>
      </Dropzone>
      {error != null && <Alert color="brique" role="alert">{error instanceof ApiError ? error.message : "Échec."}</Alert>}
      <Problems items={problemsOf(error)} />
      {analysis && <>
        <Paper p="md">
          <Group justify="space-between" mb="xs"><Title order={3} size="h5">Colonnes</Title>
            {!!analysis.profiles.length && <Select size="xs" placeholder="Appliquer un profil" w={220} data={analysis.profiles.map((p) => ({ value: String(p.id), label: p.name }))}
              onChange={(v) => { const p = analysis.profiles.find((x) => String(x.id) === v); if (p && file) void analyze(file, p.mapping); }} />}</Group>
          <SimpleGrid cols={{ base: 2, md: 3 }}>
            {analysis.fields.map((f) => <Select key={f.value} label={f.label} clearable data={headers} value={columns[f.value] ?? null}
              onChange={(v) => { const next = { ...columns }; if (v) next[f.value] = v; else delete next[f.value]; setColumns(next); }} />)}
          </SimpleGrid>
          <Group mt="sm"><Button variant="default" loading={busy} onClick={() => file && analyze(file, columns)}>Appliquer</Button>
            <Text size="sm">{`${analysis.rows} ligne(s), ${analysis.entries} écriture(s)`}</Text></Group>
        </Paper>
        <Problems items={analysis.problems} />
        {!!analysis.accounts.length && <AccountsTable rows={analysis.accounts} overrides={overrides} setOverrides={setOverrides} scope={scope} />}
        <Group align="flex-end">
          <TextInput label="Mémoriser les colonnes sous le nom" placeholder="facultatif" value={profile} onChange={(e) => setProfile(e.currentTarget.value)} />
          <Button onClick={run} loading={busy} disabled={!analysis.entries || !!analysis.problems.length}>Importer en brouillard</Button>
        </Group>
      </>}
    </Stack>
  );
}

export default function ImportHistoryPage() {
  const [kind, setKind] = useState<"fec" | "sheet">("fec");
  const scope = useCurrentSession().instance?.slug ?? "default";
  return (
    <>
      <PageHeader title="Reprise d'historique" description="Arrivez avec l'historique ou les soldes de votre ancien logiciel (FEC), ou des écritures tenues dans un tableur. Rien n'est importé tant qu'une anomalie subsiste." />
      <SegmentedControl mb="md" value={kind} onChange={(v) => setKind(v as "fec" | "sheet")}
        data={[{ value: "fec", label: "Fichier FEC" }, { value: "sheet", label: "Tableur (CSV, XLSX)" }]} />
      {kind === "fec" ? <FecImport scope={scope} /> : <SheetImport scope={scope} />}
    </>
  );
}
