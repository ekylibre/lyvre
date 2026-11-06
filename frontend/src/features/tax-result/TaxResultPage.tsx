// Compta › Résultat fiscal (lot AG6.a, claudedocs/design_fiscalite_ba.md § 3) : passage du résultat comptable au
// résultat fiscal BA, sans écriture — lignes proposées (écart de valeur fiscale des stocks, abattage sanitaire) et
// saisies (CSG non déductible, réintégrations et déductions motivées) —, répartition par associé, figé à la clôture.
import { useState } from "react";
import { Alert, Anchor, Badge, Button, Center, Group, Loader, Paper, Select, SimpleGrid, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { AppLink } from "../../app/navigation";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import type { FiscalYear } from "../fiscal-years/FiscalYearsPage";
import { CowProvisionPanel } from "./CowProvisionPanel";
import { DepPanel } from "./DepPanel";
import { GainsCreditsPanel } from "./GainsCreditsPanel";
import { LiassePanel } from "./LiassePanel";
import { SpreadPanel } from "./SpreadPanel";
import { ExplainButton } from "../assistant/AssistantDrawer";
import { CalculatorLink } from "../tools/CalculatorLink";

export interface TaxLine { key: string; id?: number; kind?: string; label: string; amount_cents: number; reason?: string | null;
  source: string; link?: string; to_validate?: boolean }
export interface TaxResultView {
  fiscal_year: { id: number; label: string; end_date: string; status: string }; accounting_result_cents: number; lines: TaxLine[];
  additions_cents: number; deductions_cents: number; fiscal_result_cents: number; company_is: boolean; warnings: string[];
  frozen: boolean; frozen_at: string | null;
  associates: { associate_id: number; name: string; share_bp: number; basis: string; is_operator: boolean; fiscal_result_cents: number; ja_cents?: number }[];
  fiscal_result_before_ja_cents?: number;
}
type Option = { value: string; label: string };

export default function TaxResultPage() {
  const can = useCan();
  const { data: years } = useQuery({ queryKey: ["fiscal-years"], queryFn: () => api.get<{ items: FiscalYear[] }>("/api/v1/fiscal-years") });
  const [params, setParams] = useUrlParams({ fiscal_year: "" });
  const fyId = Number(params.fiscal_year) || years?.items.find((y) => y.status === "open")?.id || years?.items[0]?.id;
  const key = ["tax-result", fyId];
  const { data, error } = useQuery({ queryKey: key, enabled: !!fyId,
    queryFn: () => api.get<{ item: TaxResultView; meta: { kinds: Option[] } }>(`/api/v1/fiscal-years/${fyId}/tax-result`) });
  const [draft, setDraft] = useState<{ kind: string; label: string; amount: number | null; reason: string }>({ kind: "csg", label: "", amount: null, reason: "" });
  const [formError, setFormError] = useState<string | null>(null);
  const add = useAction((b: object) => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/tax-result/lines`, b), { invalidate: [["tax-result"]] });
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/tax-result/lines/${id}`), { invalidate: [["tax-result"]] });
  if (error) return <Alert color="paille">{error instanceof ApiError ? error.message : "Indisponible."}</Alert>;
  if (!years || !data) return <Center h={300}><Loader /></Center>;
  const r = data.item;
  const writable = can.write && !r.frozen;
  return (
    <>
      <PageHeader title="Résultat fiscal" description="Passage du résultat comptable au résultat fiscal (bénéfices agricoles), sans écriture : retraitements proposés et saisis, puis répartition par associé."
        actions={<><CalculatorLink code="dep" label="Plafond DEP" /><CalculatorLink code="micro-ba" label="Micro-BA ou réel" />
          <Button variant="default" component="a" href={`/fiscal-years/${fyId}/tax-result.xlsx`}>XLSX</Button></>} />
      <FilterBar>
        <Select aria-label="Exercice" w={180} allowDeselect={false} value={fyId ? String(fyId) : null}
          data={years.items.map((y) => ({ value: String(y.id), label: `Exercice ${y.label}` }))} onChange={(x) => setParams({ fiscal_year: x ?? "" })} />
        {r.frozen && <Badge color="gray">Figé à la clôture</Badge>}
      </FilterBar>
      {r.warnings.map((w) => <Alert key={w} color="paille" mb="xs">{w}
        <ExplainButton question={`Résultat fiscal de l'exercice ${r.fiscal_year.label} : explique cette alerte et ce que je dois faire : « ${w} »`} /></Alert>)}
      <SimpleGrid cols={{ base: 2, sm: 4 }} mb="md">
        <Paper withBorder p="sm"><Text size="xs" c="dimmed">Résultat comptable</Text><MoneyText cents={r.accounting_result_cents} /></Paper>
        <Paper withBorder p="sm"><Text size="xs" c="dimmed">Réintégrations</Text><MoneyText cents={r.additions_cents} /></Paper>
        <Paper withBorder p="sm"><Text size="xs" c="dimmed">Déductions</Text><MoneyText cents={r.deductions_cents} /></Paper>
        <Paper withBorder p="sm"><Text size="xs" c="dimmed">Résultat fiscal</Text><Title order={4}><MoneyText cents={r.fiscal_result_cents} /></Title></Paper>
      </SimpleGrid>
      <Table mb="md">
        <Table.Tbody>
          <Table.Tr><Table.Td fw={600}>Résultat comptable</Table.Td><Table.Td /><Table.Td ta="right"><MoneyText cents={r.accounting_result_cents} /></Table.Td><Table.Td /></Table.Tr>
          {r.lines.map((l) => (
            <Table.Tr key={l.key}>
              <Table.Td>{l.link ? <Anchor component={AppLink} href={l.link} size="sm">{l.label}</Anchor> : l.label}
                {l.reason && <Text size="xs" c="dimmed">{l.reason}</Text>}</Table.Td>
              <Table.Td><Text size="xs" c="dimmed">{l.source === "manual" ? "saisie" : l.source === "young_farmer" ? "calculée (art. 73 B)" : l.source === "dep" ? "DEP" : l.source === "cow_provision" ? "provision 73 A" : l.source === "ba_regime" ? "régime (72 E bis, 75-0 A)" : l.source === "capital_gains" ? "plus-values" : l.source === "msa" ? "appels MSA" : "proposée"}{l.to_validate ? " · à valider" : ""}</Text></Table.Td>
              <Table.Td ta="right"><MoneyText cents={l.amount_cents} plus /></Table.Td>
              <Table.Td>{writable && l.id && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => remove.mutate(l.id!)}>Supprimer</Button>}</Table.Td>
            </Table.Tr>))}
          <Table.Tr><Table.Td fw={700}>Résultat fiscal</Table.Td><Table.Td /><Table.Td ta="right"><MoneyText cents={r.fiscal_result_cents} fw={700} /></Table.Td><Table.Td /></Table.Tr>
        </Table.Tbody>
      </Table>
      {writable && (
        <Group align="end" gap="xs" mb="lg">
          <Select label="Ligne" w={240} data={data.meta.kinds} value={draft.kind} allowDeselect={false} onChange={(v) => setDraft({ ...draft, kind: v ?? "csg" })} />
          <TextInput label="Libellé" w={220} value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.currentTarget.value })} />
          <MoneyInput label="Montant" w={130} value={draft.amount} onChange={(v) => setDraft({ ...draft, amount: v })} />
          <TextInput label="Motif" w={240} value={draft.reason} placeholder={draft.kind === "csg" ? "appel MSA" : "obligatoire"}
            onChange={(e) => setDraft({ ...draft, reason: e.currentTarget.value })} />
          <Button disabled={!draft.amount} loading={add.isPending} onClick={() => {
            setFormError(null);
            add.mutateAsync({ kind: draft.kind, label: draft.label, amount_cents: draft.amount, reason: draft.reason })
              .then(() => setDraft({ ...draft, label: "", amount: null, reason: "" }), (e) => setFormError(e instanceof ApiError ? e.message : "Enregistrement impossible."));
          }}>Ajouter</Button>
        </Group>)}
      {formError && <Alert color="brique" mb="md">{formError}</Alert>}
      {!r.company_is && fyId && <DepPanel fyId={fyId} editable={writable} />}
      {fyId && <CowProvisionPanel fyId={fyId} editable={writable} />}
      {!r.company_is && fyId && <SpreadPanel fyId={fyId} editable={writable} />}
      {fyId && <GainsCreditsPanel fyId={fyId} editable={writable} />}
      {!r.company_is && fyId && <LiassePanel fyId={fyId} />}
      {r.company_is && <Text size="sm" c="dimmed">Société à l'impôt sur les sociétés : pas de répartition entre associés.</Text>}
      {r.associates.length > 0 && (
        <>
          <Title order={4} mb="xs">Répartition par associé</Title>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Associé</Table.Th><Table.Th>Base</Table.Th><Table.Th ta="right">Quote-part</Table.Th><Table.Th ta="right">Abattement JA</Table.Th><Table.Th ta="right">Résultat fiscal</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {r.associates.map((a) => (
                <Table.Tr key={a.associate_id}><Table.Td>{a.name}{a.is_operator && <Text span size="xs" c="dimmed"> · exploitant</Text>}</Table.Td>
                  <Table.Td><Text size="xs">{a.basis}</Text></Table.Td>
                  <Table.Td ta="right" className="lv-num">{(a.share_bp / 100).toLocaleString("fr-FR")} %</Table.Td>
                  <Table.Td ta="right">{a.ja_cents ? <MoneyText cents={a.ja_cents} /> : "—"}</Table.Td>
                  <Table.Td ta="right"><MoneyText cents={a.fiscal_result_cents} /></Table.Td></Table.Tr>))}
            </Table.Tbody>
          </Table>
        </>)}
    </>
  );
}
