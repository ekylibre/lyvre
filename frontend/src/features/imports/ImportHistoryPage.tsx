// Imports › Reprise d'historique (lot F6, administrateur) : FEC d'un autre logiciel (historique
// complet d'un exercice, ou soldes d'ouverture) et écritures d'un tableur (CSV, XLSX) ; analyse,
// correspondance des comptes, puis import tout-ou-rien. Exploitation agricole (lot AG10.a) : FEC de
// cabinet en ancien plan agricole (1986) repris dans le plan actuel, sous-comptes de ventes proposés
// comme activités ; export Isacompta (.ISA, lot AG10.b) : même parcours, plus les sections analytiques
// choisies qui deviennent des ateliers et activités, avec les ventilations du dossier.
import { useState } from "react";
import {
  Alert, Badge, Button, Checkbox, Group, List, Paper, Radio, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, TextInput, Title,
} from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, useAction, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { useCurrentSession } from "../../api/session";
import { AccountSelect } from "../../components/AccountSelect";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import type { Account } from "../../lib/types";

interface PlanRow {
  key: string; code: string; label: string; aux: string; aux_label: string; action: "existing" | "mapped" | "create";
  account_id: number | null; target_code: string | null; origin?: "pcga1986" | null; pcga_target?: string;
}
interface ActivityProposal {
  account_id: number; code: string; label: string; name: string; lexicon_reference: string | null;
  lexicon_name: string | null; family: string; activity_id: number | null;
}
interface FecAnalysis {
  entries: number; lines: number; debit_cents: number; credit_cents: number; first_date: string; last_date: string;
  fiscal_year: { start_date: string; end_date: string }; journals: { code: string; exists: boolean }[]; letterings: number;
  accounts: PlanRow[]; problems: string[]; to_create: number; pcga1986?: boolean; isa?: IsaInfo;
}
interface IsaSection { code: string; label: string; unit: string | null; quantity: number | null; workshop: string | null; lexicon_name: string | null; proposed: boolean }
interface IsaInfo {
  sections: IsaSection[]; line_allocations: number; account_allocations: number; due_dates: number; reconciliations: number;
  vat_codes: { code: string; label: string; account: string; rate: string }[];
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
              <Text span size="sm" className="lv-num">{r.target_code}</Text>
              {r.origin === "pcga1986" && <Text size="xs" c="dimmed">{r.action === "create" ? `plan 1986 : sous-compte de ${r.pcga_target}` : "plan 1986"}</Text>}</Table.Td>
            <Table.Td w={320}><AccountSelect label="Correspondance" recentsScope={scope} value={overrides[r.key] ?? null}
              onChange={(account) => setOverrides({ ...overrides, [r.key]: account })} /></Table.Td>
          </Table.Tr>
        ))}</Table.Tbody>
      </Table>
      {!shown.length && <Text size="sm" c="dimmed" p="sm">Tous les comptes du fichier existent dans le plan.</Text>}
    </Paper>
  );
}

/** Sections analytiques d'un export Isacompta : celles cochées deviennent des activités (AG8). */
export function IsaSections({ info, chosen, setChosen }: { info: IsaInfo; chosen: string[]; setChosen: (c: string[]) => void }) {
  return (
    <Paper p={0}>
      <Stack gap={2} p="sm">
        <Title order={3} size="h5">{`Sections analytiques (${info.sections.length})`}</Title>
        <Text size="sm" c="dimmed">{`Les sections cochées deviennent des activités, avec leur surface. ${info.line_allocations} ligne(s) et ${info.account_allocations} compte(s) ventilés dans le dossier ; une ventilation sur un regroupement de sections devient une clé de répartition à la surface. Échéances (${info.due_dates}) et pointages (${info.reconciliations}) ne sont pas repris.`}</Text>
      </Stack>
      {info.sections.length > 0 && <Table>
        <Table.Thead><Table.Tr><Table.Th w={40} /><Table.Th>Section</Table.Th><Table.Th>Atelier</Table.Th><Table.Th>Surface</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{info.sections.map((s) => (
          <Table.Tr key={s.code}>
            <Table.Td><Checkbox aria-label={`Section ${s.code}`} checked={chosen.includes(s.code)}
              onChange={(e) => setChosen(e.currentTarget.checked ? [...chosen, s.code] : chosen.filter((c) => c !== s.code))} /></Table.Td>
            <Table.Td><Text size="sm"><span className="lv-num">{s.code}</span>{` ${s.label}`}</Text>
              {s.lexicon_name && <Text size="xs" c="dimmed">{`production Lexicon : ${s.lexicon_name}`}</Text>}</Table.Td>
            <Table.Td><Text size="sm">{s.workshop ?? "—"}</Text></Table.Td>
            <Table.Td><Text size="sm" className="lv-num">{s.quantity ? `${s.quantity} ${s.unit ?? ""}` : "—"}</Text></Table.Td>
          </Table.Tr>
        ))}</Table.Tbody>
      </Table>}
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
  const [sections, setSections] = useState<string[]>([]);
  const isa = !!file && file.name.toLowerCase().endsWith(".isa");
  const base = isa ? "/api/v1/imports/isa" : "/api/v1/imports/fec";
  const analyze = async (chosen: File, current = overrides, fresh = false) => {
    const form = new FormData();
    form.append("file", chosen);
    form.append("mappings", mappingsField(current));
    setBusy(true); setError(null);
    try {
      const url = chosen.name.toLowerCase().endsWith(".isa") ? "/api/v1/imports/isa" : "/api/v1/imports/fec";
      const result = await upload<FecAnalysis>(`${url}/analyze`, form);
      setAnalysis(result);
      if (result.isa && fresh) setSections(result.isa.sections.filter((s) => s.proposed).map((s) => s.code));
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
    if (isa && mode === "history") form.append("sections", JSON.stringify(sections));
    setBusy(true); setError(null);
    try {
      const body = await upload<{ notices: Notice[] }>(base, form);
      showNotices(body.notices);
      setAnalysis(null); setFile(null);
      void client.invalidateQueries();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return (
    <Stack>
      <Dropzone onDrop={(files) => { if (files[0]) { setFile(files[0]); setOverrides({}); setAnalysis(null); void analyze(files[0], {}, true); } }} multiple={false} loading={busy}>
        <Group justify="center" gap="sm" mih={80}><FileUp size={28} /><Text>{file ? file.name : "Déposez le FEC (.txt, tabulation ou barre verticale) ou l'export Isacompta (.ISA)"}</Text></Group>
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
        {analysis.pcga1986 && <Alert color="ardoise" title="Ancien plan comptable agricole (1986)">
          Les comptes sur 8 chiffres sont repris dans le plan agricole actuel. Les sous-comptes (cultures, produits, banques) restent distincts, sous le compte du plan. Vérifiez les correspondances avant l'import.</Alert>}
        <AccountsTable rows={analysis.accounts} overrides={overrides} setOverrides={setOverrides} scope={scope} />
        {analysis.isa && mode === "history" && <IsaSections info={analysis.isa} chosen={sections} setChosen={setSections} />}
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

/** Sous-comptes de ventes de produits repris, proposés comme activités (AG8) avec leur règle de ventilation. */
export function ActivityProposals() {
  const query = useQuery({ queryKey: ["imports", "activities"],
    queryFn: () => api.get<{ items: ActivityProposal[] }>("/api/v1/imports/activities") });
  const [picked, setPicked] = useState<number[]>([]);
  const create = useAction((items: { account_id: number }[]) => api.post<{ notices: Notice[] }>("/api/v1/imports/activities", { items }),
    { invalidate: [["imports", "activities"], ["activities"]] });
  const items = Array.isArray(query.data?.items) ? query.data.items : [];
  if (!items.length) return null;
  const chosen = picked.filter((id) => items.some((p) => p.account_id === id));
  return (
    <Paper p="md" mt="md">
      <Title order={3} size="h5">{`Activités proposées (${items.length})`}</Title>
      <Text size="sm" c="dimmed" mb="sm">Sous-comptes de ventes repris du dossier. Cochez ceux qui deviennent des activités : l'activité est créée (ou reprise si elle existe) avec la règle de ventilation du compte.</Text>
      <Table>
        <Table.Thead><Table.Tr><Table.Th w={40} /><Table.Th>Compte</Table.Th><Table.Th>Activité</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{items.map((p) => (
          <Table.Tr key={p.account_id}>
            <Table.Td><Checkbox aria-label={`Retenir ${p.code}`} checked={chosen.includes(p.account_id)}
              onChange={(e) => setPicked(e.currentTarget.checked ? [...chosen, p.account_id] : chosen.filter((id) => id !== p.account_id))} /></Table.Td>
            <Table.Td><Text size="sm" className="lv-num">{p.code}</Text><Text size="xs" c="dimmed">{p.label}</Text></Table.Td>
            <Table.Td><Text size="sm">{p.name}</Text>
              <Text size="xs" c="dimmed">{p.activity_id ? "activité existante" : p.lexicon_name ? `production Lexicon : ${p.lexicon_name}` : "sans production Lexicon"}</Text></Table.Td>
          </Table.Tr>
        ))}</Table.Tbody>
      </Table>
      <Group mt="sm">
        <Button variant="default" size="compact-sm" onClick={() => setPicked(items.map((p) => p.account_id))}>Tout cocher</Button>
        <Button onClick={() => create.mutate(chosen.map((account_id) => ({ account_id })), { onSuccess: () => setPicked([]) })}
          loading={create.isPending} disabled={!chosen.length}>{`Créer ${chosen.length} activité(s)`}</Button>
      </Group>
    </Paper>
  );
}

export default function ImportHistoryPage() {
  const [kind, setKind] = useState<"fec" | "sheet">("fec");
  const session = useCurrentSession();
  const scope = session.instance?.slug ?? "default";
  const agri = session.instance?.chart === "agri";
  return (
    <>
      <PageHeader title="Reprise d'historique" description="Arrivez avec l'historique ou les soldes de votre ancien logiciel (FEC), ou des écritures tenues dans un tableur. Rien n'est importé tant qu'une anomalie subsiste." />
      <SegmentedControl mb="md" value={kind} onChange={(v) => setKind(v as "fec" | "sheet")}
        data={[{ value: "fec", label: "Fichier FEC" }, { value: "sheet", label: "Tableur (CSV, XLSX)" }]} />
      {kind === "fec" ? <FecImport scope={scope} /> : <SheetImport scope={scope} />}
      {agri && <ActivityProposals />}
    </>
  );
}
