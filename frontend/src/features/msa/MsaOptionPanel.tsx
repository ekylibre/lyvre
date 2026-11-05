// Cotisations MSA › option d'assiette et historique (lot AG7.b, claudedocs/design_msa.md § 4) : comparaison entre la
// moyenne triennale et l'assiette annuelle pour l'année de cotisation suivante, délais d'option et de dénonciation,
// assiettes des années antérieures saisies depuis les avis MSA (y compris 2023 et 2024 reconstituées par la caisse).
import { useState } from "react";
import { Alert, Badge, Button, Group, NumberInput, Table, Text, TextInput } from "@mantine/core";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyInput, MoneyText } from "../../components/Money";

export interface MsaBaseRow { id: number; year: number; source: "lyvre" | "entered"; income_cents: number | null;
  abatement_cents: number | null; base_cents: number; note: string | null }
export interface MsaComparison {
  contribution_year: number; span: number[]; bases: Record<string, number | null>; missing: number[];
  annual_cents: number | null; triennial_cents: number | null; difference_cents: number | null; best: "annual" | "triennial" | null;
  retained_cents: number | null; notes: string[];
  option: { current: string; since: string | null; deadline: string; deadline_label: string; commitment_end?: string | null };
}

const money = (v: number | null | undefined) => (v === null || v === undefined ? "—" : <MoneyText cents={v} />);

export function MsaOptionPanel({ personId, comparison: c, history, editable }:
  { personId: number; comparison: MsaComparison; history: MsaBaseRow[]; editable: boolean }) {
  const [draft, setDraft] = useState<{ year: number | null; base: number | null; note: string }>({ year: c.missing[0] ?? null, base: null, note: "" });
  const [error, setError] = useState<string | null>(null);
  const base = `/api/v1/msa/people/${personId}/bases`;
  const opts = { invalidate: [["msa"]] };
  const save = useAction(({ year, ...b }: { year: number; [key: string]: unknown }) => api.put<{ notices: Notice[] }>(`${base}/${year}`, b), opts);
  const remove = useAction((year: number) => api.delete<{ notices: Notice[] }>(`${base}/${year}`), opts);
  const run = (x: Promise<unknown>, after?: () => void) => { setError(null); x.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  const label = (k: string) => (k === "annual" ? "assiette annuelle" : "moyenne triennale");
  return (
    <>
      <Text fw={600} size="sm" mt="md">Assiette des cotisations {c.contribution_year}</Text>
      <Table>
        <Table.Thead><Table.Tr>{c.span.map((y) => <Table.Th key={y} ta="right">Revenus {y}</Table.Th>)}
          <Table.Th ta="right">Annuelle</Table.Th><Table.Th ta="right">Triennale</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody><Table.Tr>{c.span.map((y) => <Table.Td key={y} ta="right">{money(c.bases[String(y)])}</Table.Td>)}
          <Table.Td ta="right">{money(c.annual_cents)}</Table.Td><Table.Td ta="right">{money(c.triennial_cents)}</Table.Td></Table.Tr></Table.Tbody>
      </Table>
      <Group gap="xs" mt={4}>
        <Badge variant="light">Option en vigueur : {label(c.option.current)}{c.option.since ? ` depuis le ${new Date(c.option.since).toLocaleDateString("fr-FR")}` : ""}</Badge>
        {c.best && c.difference_cents !== null && <Text size="sm">La {label(c.best)} est plus basse de <MoneyText cents={Math.abs(c.difference_cents)} />.</Text>}
        {c.missing.length > 0 && <Text size="sm" c="dimmed">Moyenne incomplète : revenus {c.missing.join(", ")} à saisir.</Text>}
      </Group>
      <Text size="xs" c="dimmed">{c.option.deadline_label}{c.option.commitment_end ? ` Engagement jusqu'au ${new Date(c.option.commitment_end).toLocaleDateString("fr-FR")}.` : ""}</Text>
      {c.notes.map((n) => <Text key={n} size="xs" c="dimmed">{n}</Text>)}

      <Text fw={600} size="sm" mt="md">Historique des assiettes</Text>
      {history.length > 0 && (
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Revenus</Table.Th><Table.Th>Origine</Table.Th><Table.Th ta="right">Assiette</Table.Th><Table.Th>Note</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {history.map((h) => (
              <Table.Tr key={h.id}><Table.Td>{h.year}</Table.Td><Table.Td>{h.source === "lyvre" ? "calculée (clôture)" : "saisie"}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={h.base_cents} /></Table.Td><Table.Td><Text size="xs">{h.note}</Text></Table.Td>
                <Table.Td>{editable && h.source === "entered" && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(remove.mutateAsync(h.year))}>Supprimer</Button>}</Table.Td></Table.Tr>))}
          </Table.Tbody>
        </Table>)}
      {editable && (
        <Group align="end" gap="xs" mt="xs">
          <NumberInput label="Revenus de" w={110} min={2000} max={2100} value={draft.year ?? ""} onChange={(x) => setDraft({ ...draft, year: typeof x === "number" ? x : null })} />
          <MoneyInput label="Assiette (avis MSA)" w={160} value={draft.base} onChange={(x) => setDraft({ ...draft, base: x })} />
          <TextInput label="Note" w={240} value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.currentTarget.value })} />
          <Button variant="light" loading={save.isPending} disabled={!draft.year}
            onClick={() => run(save.mutateAsync({ year: draft.year!, base_cents: draft.base, note: draft.note }), () => setDraft({ year: null, base: null, note: "" }))}>Enregistrer</Button>
        </Group>)}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
    </>
  );
}
