// Compta › Cotisations MSA (lot AG7.a, claudedocs/design_msa.md § 3, AGD24) : assiette sociale de l'exercice par
// exploitant — résultat fiscal BA, réintégrations (JA, stock bloqué, à-valoir, cotisations 646 en EI), DJA déduite,
// abattement de 26 % borné (plancher même en déficit) ; lignes saisies avec motif.
import { useState } from "react";
import { Alert, Badge, Button, Center, Group, Loader, Paper, Select, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { AppLink } from "../../app/navigation";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import type { FiscalYear } from "../fiscal-years/FiscalYearsPage";
import { MsaCallsPanel } from "./MsaCallsPanel";
import { MsaEstimatePanel, type MsaEstimate } from "./MsaEstimatePanel";
import { MsaVentilationPanel } from "./MsaVentilationPanel";
import { MsaOptionPanel, type MsaBaseRow, type MsaComparison } from "./MsaOptionPanel";
import { ExplainButton } from "../assistant/AssistantDrawer";
import { CalculatorLink } from "../tools/CalculatorLink";

type Option = { value: string; label: string };
interface MsaLine { key: string; id?: number; kind?: string; label: string; amount_cents: number; basis?: string; reason?: string | null }
interface MsaPersonView {
  person: { id: number; name: string; status: string; base_option: string; option_since: string | null; atexa_category?: string | null;
    collaborator_allowed?: boolean };
  share_bp: number; fiscal_result_cents: number; lines: MsaLine[]; income_cents: number; base_cents: number | null;
  abatement: { amount_cents?: number; raw_cents?: number; floor_cents?: number; ceiling_cents?: number; pass_cents?: number;
    bound?: string | null; error?: string };
  history?: MsaBaseRow[]; comparison?: MsaComparison; estimate?: MsaEstimate;
}
export interface MsaView {
  fiscal_year: { id: number; label: string; status: string }; year: number; reason: string | null; warnings: string[];
  tax_frozen?: boolean; people: MsaPersonView[];
}
interface Meta { statuses: Option[]; base_options: Option[]; adjustment_kinds: Option[] }

const euros = (c: number) => `${(c / 100).toLocaleString("fr-FR")} €`;

/** Année civile qui couvre la plus grande partie de l'exercice (exercice décalé : 02/2024-01/2025 → 2024), pour les appels. */
function mainCivilYear(fy: { start_date: string; end_date: string } | undefined): number | null {
  if (!fy) return null;
  const start = new Date(fy.start_date).getTime(), end = new Date(fy.end_date).getTime();
  return new Date(start + (end - start) / 2).getUTCFullYear();
}

export default function MsaPage() {
  const can = useCan();
  const { data: years } = useQuery({ queryKey: ["fiscal-years"], queryFn: () => api.get<{ items: FiscalYear[] }>("/api/v1/fiscal-years") });
  const [params, setParams] = useUrlParams({ fiscal_year: "" });
  const fyId = Number(params.fiscal_year) || years?.items.find((y) => y.status === "open")?.id || years?.items[0]?.id;
  const url = `/api/v1/fiscal-years/${fyId}/msa`;
  const { data, error } = useQuery({ queryKey: ["msa", fyId], enabled: !!fyId, queryFn: () => api.get<{ item: MsaView; meta: Meta }>(url) });
  const [draft, setDraft] = useState<{ person: number | null; kind: string; amount: number | null; reason: string }>({ person: null, kind: "avaloir", amount: null, reason: "" });
  const [formError, setFormError] = useState<string | null>(null);
  const opts = { invalidate: [["msa"]] };
  const add = useAction((b: object) => api.post<{ notices: Notice[] }>(`${url}/adjustments`, b), opts);
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`${url}/adjustments/${id}`), opts);
  const patch = useAction(({ id, ...b }: { id: number; [key: string]: unknown }) => api.patch<{ notices: Notice[] }>(`/api/v1/msa/people/${id}`, b), opts);
  if (error) return <Alert color="paille">{error instanceof ApiError ? error.message : "Indisponible."}</Alert>;
  if (!years || !data) return <Center h={300}><Loader /></Center>;
  const v = data.item;
  const writable = can.write && v.fiscal_year.status !== "closed";
  const callsYear = mainCivilYear(years.items.find((y) => y.id === fyId)) ?? v.year;
  const run = (x: Promise<unknown>, after?: () => void) => { setFormError(null); x.then(after, (e) => setFormError(e instanceof ApiError ? e.message : "Action impossible.")); };
  return (
    <>
      <PageHeader title="Cotisations MSA" description="Assiette sociale des non-salariés agricoles : du résultat fiscal BA à l'assiette des cotisations, par exploitant (réforme 2026)."
        actions={<><CalculatorLink code="msa" label="Simuler" /><Button variant="default" component="a" href={`/fiscal-years/${fyId}/msa.xlsx`}>XLSX</Button></>} />
      <FilterBar>
        <Select aria-label="Exercice" w={180} allowDeselect={false} value={fyId ? String(fyId) : null}
          data={years.items.map((y) => ({ value: String(y.id), label: `Exercice ${y.label}` }))} onChange={(x) => setParams({ fiscal_year: x ?? "" })} />
        {v.tax_frozen && <Badge color="gray">Figée à la clôture</Badge>}
        <Text size="sm" c="dimmed">Revenus {v.year} : cotisations {v.year + 1} en assiette annuelle, moyenne triennale sinon.</Text>
      </FilterBar>
      {v.reason && <Alert color="gray" mb="md">{v.reason}</Alert>}
      {v.warnings.map((w) => <Alert key={w} color="paille" mb="xs">{w}
        <ExplainButton question={`Cotisations MSA (revenus ${v.year}) : explique cette alerte et ce que je dois faire : « ${w} »`} /></Alert>)}
      {v.people.map((p) => (
        <Paper key={p.person.id} withBorder p="md" mb="md">
          <Group justify="space-between" mb="xs">
            <Title order={4}>{p.person.name}{p.share_bp !== 10000 && <Text span size="sm" c="dimmed"> · quote-part {(p.share_bp / 100).toLocaleString("fr-FR")} %</Text>}</Title>
            <Group gap="xs">
              <Select aria-label="Statut" w={300} size="xs" data={data.meta.statuses.filter((o) => o.value !== "collaborator" || p.person.collaborator_allowed !== false || p.person.status === "collaborator")} value={p.person.status} allowDeselect={false} disabled={!can.write}
                onChange={(x) => x && patch.mutate({ id: p.person.id, status: x })} />
              <Select aria-label="Option d'assiette" w={280} size="xs" data={data.meta.base_options} value={p.person.base_option} allowDeselect={false} disabled={!can.write}
                onChange={(x) => x && patch.mutate({ id: p.person.id, base_option: x })} />
            </Group>
          </Group>
          <Table>
            <Table.Tbody>
              <Table.Tr><Table.Td fw={600}>Résultat fiscal BA{p.share_bp !== 10000 ? " (quote-part)" : ""}</Table.Td><Table.Td />
                <Table.Td ta="right"><MoneyText cents={p.fiscal_result_cents} /></Table.Td><Table.Td /></Table.Tr>
              {p.lines.map((l) => (
                <Table.Tr key={l.key}>
                  <Table.Td>{l.label}{l.reason && <Text size="xs" c="dimmed">{l.reason}</Text>}</Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{l.basis}</Text></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={l.amount_cents} plus /></Table.Td>
                  <Table.Td>{writable && l.id && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(remove.mutateAsync(l.id!))}>Supprimer</Button>}</Table.Td>
                </Table.Tr>))}
              <Table.Tr><Table.Td fw={600}>Revenu professionnel avant abattement</Table.Td><Table.Td />
                <Table.Td ta="right"><MoneyText cents={p.income_cents} /></Table.Td><Table.Td /></Table.Tr>
              {p.abatement.amount_cents !== undefined && (
                <Table.Tr><Table.Td>Abattement forfaitaire de 26 %{p.abatement.bound ? ` (${p.abatement.bound})` : ""}</Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">entre {euros(p.abatement.floor_cents ?? 0)} et {euros(p.abatement.ceiling_cents ?? 0)} (1,76 % et 130 % du PASS)</Text></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={-p.abatement.amount_cents} plus /></Table.Td><Table.Td /></Table.Tr>)}
              <Table.Tr><Table.Td fw={700}>Assiette sociale {v.year}</Table.Td><Table.Td />
                <Table.Td ta="right">{p.base_cents === null ? "—" : <MoneyText cents={p.base_cents} fw={700} />}</Table.Td><Table.Td /></Table.Tr>
            </Table.Tbody>
          </Table>
          {writable && (
            <Group align="end" gap="xs" mt="xs">
              <Select label="Ligne" w={280} data={data.meta.adjustment_kinds} value={draft.person === p.person.id ? draft.kind : "avaloir"} allowDeselect={false}
                onChange={(x) => setDraft({ ...(draft.person === p.person.id ? draft : { amount: null, reason: "" }), person: p.person.id, kind: x ?? "avaloir" })} />
              <MoneyInput label="Montant" w={140} value={draft.person === p.person.id ? draft.amount : null}
                onChange={(x) => setDraft({ ...(draft.person === p.person.id ? draft : { kind: "avaloir", reason: "" }), person: p.person.id, amount: x })} />
              <TextInput label="Motif" w={260} value={draft.person === p.person.id ? draft.reason : ""}
                placeholder={(draft.person === p.person.id ? draft.kind : "avaloir") === "avaloir" ? "facultatif" : "obligatoire"}
                onChange={(e) => setDraft({ ...(draft.person === p.person.id ? draft : { kind: "avaloir", amount: null }), person: p.person.id, reason: e.currentTarget.value })} />
              <Button variant="light" loading={add.isPending} disabled={draft.person !== p.person.id || !draft.amount}
                onClick={() => run(add.mutateAsync({ person_id: p.person.id, kind: draft.kind, amount_cents: draft.amount, reason: draft.reason }),
                  () => setDraft({ ...draft, amount: null, reason: "" }))}>Ajouter</Button>
            </Group>)}
          {p.comparison && <MsaOptionPanel personId={p.person.id} comparison={p.comparison} history={p.history ?? []} editable={can.write} />}
          {p.estimate && <MsaEstimatePanel estimate={p.estimate} category={p.person.atexa_category ?? null} editable={can.write}
            onCategory={(x) => patch.mutate({ id: p.person.id, atexa_category: x })} />}
        </Paper>))}
      {formError && <Alert color="brique" mb="md">{formError}</Alert>}
      <MsaCallsPanel key={callsYear} defaultYear={callsYear} editable={can.write} />
      {fyId && <MsaVentilationPanel fyId={fyId} editable={writable} />}
      <Text size="xs" c="dimmed">Point de départ : <AppLink href={`/tax-result/?fiscal_year=${fyId}`}>résultat fiscal</AppLink>. DEP, provision 73 A, étalement 75-0 A,
        abattage 75-0 D et plus-values y restent comme au fiscal (CSS L.136-4). La rente du sol n'est pas calculée.</Text>
    </>
  );
}
