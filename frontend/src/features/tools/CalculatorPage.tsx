// Outils › une calculette (lot AG12) : formulaire construit depuis la spécification (saisie libre ou préremplie,
// origine de chaque valeur), résultat selon le gabarit commun (C1) : chiffres, détail, tableau, avertissements,
// méthode et limites, paramètres réglementaires avec leur fiabilité, sources, actions ; copie en texte (C4).
import { lazy, Suspense, useState } from "react";
import { useParams } from "react-router";
import {
  Alert, Anchor, Badge, Button, CopyButton, Grid, Group, List, Loader, Paper, Select, Stack, Table, Text, TextInput, Title,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { TOOLS_KEY, type CalcInput, type CalcResult, type CalcSpec } from "./types";

const CalcMap = lazy(() => import("./CalcMap"));
const FRANCE: [number, number] = [46.6, 2.4];

function parsePoint(value: string): [number, number] | null {
  const parts = value.split(",").map((p) => Number(p.trim()));
  return parts.length === 2 && parts.every((n) => Number.isFinite(n) && value.trim() !== "") ? [parts[0], parts[1]] : null;
}

/** Point choisi d'un clic sur la carte (centrée sur la structure), ou saisi « latitude, longitude ». */
function PointField({ input, value, onChange }: { input: CalcInput; value: string; onChange: (v: string) => void }) {
  const { data } = useQuery({ queryKey: ["geo", "organization"], staleTime: Infinity,
    queryFn: () => api.get<{ center: { lat: number; lon: number; zoom: number } }>("/api/v1/geo/organization") });
  const point = parsePoint(value);
  const center: [number, number] = point ?? (data ? [data.center.lat, data.center.lon] : FRANCE);
  return (
    <Stack gap={4}>
      <TextInput label={input.label} required={input.required} description={input.help ?? undefined} value={value}
        placeholder="45.8295, -0.7870" onChange={(e) => onChange(e.currentTarget.value)} />
      <Suspense fallback={<Loader size="sm" />}>
        <CalcMap center={center} zoom={point ? 16 : data?.center.zoom ?? 6} point={point}
          onPick={(lat, lon) => onChange(`${lat},${lon}`)} height={260} />
      </Suspense>
    </Stack>
  );
}

const RELIABILITY: Record<string, { label: string; color: string }> = {
  V: { label: "vérifié", color: "lichen" }, R: { label: "recoupé", color: "ardoise" }, A: { label: "à vérifier", color: "paille" },
  I: { label: "incertain", color: "brique" },
};

function Field({ input, value, origin, onChange }: { input: CalcInput; value: string; origin?: string; onChange: (v: string) => void }) {
  const description = [input.help, origin && `Origine : ${origin}`].filter(Boolean).join(" · ") || undefined;
  if (input.kind === "point") return <PointField input={input} value={value} onChange={onChange} />;
  if (input.kind === "choice") {
    return <Select label={input.label} required={input.required} data={input.choices ?? []} value={value || null}
      description={description} onChange={(v) => onChange(v ?? "")} allowDeselect={!input.required} />;
  }
  return <TextInput label={input.label} required={input.required} description={description} value={value}
    type={input.kind === "date" ? "date" : "text"} inputMode={input.kind === "date" || input.kind === "text" ? undefined : "decimal"}
    rightSection={input.unit ? <Text size="xs" c="dimmed">{input.unit}</Text> : undefined} rightSectionWidth={input.unit ? 48 : undefined}
    onChange={(e) => onChange(e.currentTarget.value)} />;
}

export function ResultView({ spec, result }: { spec: CalcSpec; result: CalcResult }) {
  return (
    <Stack>
      <Group gap="xl">{result.headline.map((h) => (
        <div key={h.label}><Text size="sm" c="dimmed">{h.label}</Text><Text fw={700} size="xl" className="lv-num">{h.value}</Text></div>))}</Group>
      {result.warnings.map((w) => <Alert key={w} color="paille">{w}</Alert>)}
      {result.map && <Suspense fallback={<Loader size="sm" />}>
        <CalcMap center={result.map.center} zoom={result.map.zoom} point={result.map.center} features={result.map.features} />
      </Suspense>}
      {result.details.length > 0 && <Table><Table.Tbody>{result.details.map((d) => (
        <Table.Tr key={d.label}><Table.Td>{d.label}</Table.Td><Table.Td ta="right" className="lv-num">
          {d.value.startsWith("https://") || d.value.startsWith("http://")
            ? <Anchor href={d.value} target="_blank" size="sm">ouvrir</Anchor> : d.value}</Table.Td></Table.Tr>))}
      </Table.Tbody></Table>}
      {result.table && <Table.ScrollContainer minWidth={500}><Table striped>
        <Table.Thead><Table.Tr>{result.table.columns.map((c) => <Table.Th key={c}>{c}</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>{result.table.rows.map((r, i) => <Table.Tr key={i}>{r.map((c, j) => <Table.Td key={j} className="lv-num">{c}</Table.Td>)}</Table.Tr>)}</Table.Tbody>
      </Table></Table.ScrollContainer>}
      <div><Title order={4}>Méthode et limites</Title><Text size="sm">{spec.method}</Text></div>
      {result.params.length > 0 && <div><Title order={4} mb={4}>Paramètres réglementaires</Title>
        <List size="sm">{result.params.map((p) => (
          <List.Item key={p.key}><Text span className="lv-num">{p.key}</Text> = {String(p.value)}
            {p.reliability && <Badge ml={6} size="xs" variant="light" color={RELIABILITY[p.reliability]?.color}>{RELIABILITY[p.reliability]?.label ?? p.reliability}</Badge>}
            {p.source && <> · <Anchor href={p.source} target="_blank" size="sm">{p.source_label || "source"}</Anchor></>}
            {p.verified_on && <Text span size="xs" c="dimmed"> (vérifié le {p.verified_on})</Text>}</List.Item>))}</List></div>}
      {spec.sources.length > 0 && <div><Title order={4} mb={4}>Sources</Title>
        <List size="sm">{spec.sources.map((s) => <List.Item key={s.url}><Anchor href={s.url} target="_blank" size="sm">{s.label}</Anchor></List.Item>)}</List></div>}
      <Group>
        <CopyButton value={result.text}>{({ copied, copy }) => <Button variant="default" onClick={copy}>{copied ? "Copié" : "Copier le résultat"}</Button>}</CopyButton>
        {result.actions.map((a) => <Button key={a.route} variant="default" component={AppLink} href={a.route}>{a.label}</Button>)}
      </Group>
    </Stack>
  );
}

export function CalculatorForm({ spec, onResult }: { spec: CalcSpec; onResult?: (r: CalcResult) => void }) {
  const initial = Object.fromEntries(spec.inputs.map((i) => [i.key, spec.prefill?.[i.key]?.value ?? i.default ?? ""]));
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [origins, setOrigins] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(spec.prefill ?? {}).map(([k, v]) => [k, v.origin])));
  const [result, setResult] = useState<CalcResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: string, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    setOrigins((o) => { const { [key]: _gone, ...rest } = o; return rest; });   // valeur modifiée : saisie
  };
  const compute = async () => {
    setBusy(true); setError(null);
    try {
      const body = await api.post<{ result: CalcResult }>(`/api/v1/calculators/${spec.code}`, { values, origins });
      setResult(body.result); onResult?.(body.result);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Échec du calcul."); setResult(null); } finally { setBusy(false); }
  };
  return (
    <Grid>
      <Grid.Col span={{ base: 12, md: 5 }}>
        <Paper p="md">
          <form onSubmit={(e) => { e.preventDefault(); void compute(); }}>
            <Stack gap="sm">
              {spec.inputs.map((i) => <Field key={i.key} input={i} value={values[i.key] ?? ""} origin={origins[i.key]} onChange={(v) => set(i.key, v)} />)}
              <Group justify="space-between">
                <Button variant="subtle" onClick={() => { setValues({ ...initial, ...spec.example }); setOrigins({}); }}>Charger l'exemple</Button>
                <Button type="submit" loading={busy}>Calculer</Button>
              </Group>
            </Stack>
          </form>
        </Paper>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 7 }}>
        <Paper p="md">
          {error && <Alert color="brique" role="alert">{error}</Alert>}
          {result ? <ResultView spec={spec} result={result} /> : !error && <Text c="dimmed">Renseignez les valeurs, puis « Calculer ».</Text>}
        </Paper>
      </Grid.Col>
    </Grid>
  );
}

export default function CalculatorPage() {
  const code = useParams().code ?? "";
  const [choice, setChoice] = useState<string | null>(null);
  const { data, error } = useQuery({ queryKey: [...TOOLS_KEY, code, choice], retry: false,
    queryFn: () => api.get<{ item: CalcSpec }>(`/api/v1/calculators/${code}${choice ? `?choice=${choice}` : ""}`) });
  if (error) return <Alert color="brique" mt="md">{(error as Error).message}</Alert>;
  if (!data) return <Loader />;
  const spec = data.item;
  return (
    <>
      <PageHeader title={spec.title} description={spec.summary}
        actions={<Button variant="default" component={AppLink} href="/outils/">Calculettes</Button>} />
      {spec.prefill_options && spec.prefill_options.length > 0 && (
        <Select mb="md" w={360} label={`Préremplir depuis : ${(spec.prefill_label ?? "").toLowerCase()}`} clearable
          data={spec.prefill_options} value={choice} onChange={setChoice} />)}
      {spec.prefill_empty && (
        <Text size="sm" c="dimmed" mb="md">Rien à reprendre du dossier : {spec.prefill_empty}. Saisissez les valeurs à la main.</Text>)}
      <CalculatorForm key={JSON.stringify(spec.prefill ?? {})} spec={spec} />
    </>
  );
}
