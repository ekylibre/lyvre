// Cotisations MSA › ventilation (lot AG7.d, claudedocs/design_msa.md § 6) : EI — CSG non déductible reportée au résultat
// fiscal, charge à payer D 646 / C 4311 des appels non réglés à la clôture, contrôle du 646 ; société — cotisations des
// associés en compte courant 455, part déductible affichée par associé (à valider).
import { useState } from "react";
import { Alert, Anchor, Button, Group, Paper, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { AppLink } from "../../app/navigation";
import { MoneyText } from "../../components/Money";

export interface MsaVentilationView {
  mode: "ei" | "company" | "is";
  tax_lines: { key: string; label: string; amount_cents: number; to_validate?: boolean }[];
  accrual: { amount_cents: number; calls: { id: number; due_on: string; amount_cents: number }[];
    entry: { id: number; reference: string; amount_cents: number } | null } | null;
  checks: { key: string; label: string; severity: string }[];
  associates: { person_id: number; name: string; calls_cents: number; deductible_cents: number; non_deductible_cents: number; missing_split: number }[];
}

export function MsaVentilationPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const url = `/api/v1/fiscal-years/${fyId}/msa`;
  const { data } = useQuery({ queryKey: ["msa", "ventilation", fyId], queryFn: () => api.get<{ item: MsaVentilationView }>(`${url}/ventilation`) });
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["msa"], ["tax-result"]] };
  const post = useAction(() => api.post<{ notices: Notice[] }>(`${url}/accrual`, {}), opts);
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`${url}/accrual`), opts);
  if (!data?.item || data.item.mode === "is") return null;
  const v = data.item;
  const run = (x: Promise<unknown>) => { setError(null); x.catch((e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  return (
    <Paper withBorder p="md" mt="lg">
      <Title order={4} mb="xs">Ventilation de l'exercice</Title>
      {v.checks.map((c) => <Alert key={c.key} color={c.severity === "anomaly" ? "brique" : "paille"} mb="xs">{c.label}</Alert>)}
      {v.mode === "ei" && (
        <>
          <Text size="sm">Résultat fiscal : {v.tax_lines.length
            ? v.tax_lines.map((l) => <span key={l.key}>CSG non déductible et CRDS <MoneyText cents={l.amount_cents} /> réintégrées{l.to_validate ? " (détail estimé)" : ""}</span>)
            : "aucune CSG non déductible au registre pour l'exercice."}{" "}
            <Anchor component={AppLink} href={`/tax-result/?fiscal_year=${fyId}`} size="sm">voir le résultat fiscal</Anchor></Text>
          {v.accrual && (
            <Group gap="xs" mt="xs">
              <Text size="sm">Appels de l'exercice non réglés à la clôture : <MoneyText cents={v.accrual.amount_cents} />
                {v.accrual.entry ? <> — charge à payer passée ({v.accrual.entry.reference}, <MoneyText cents={v.accrual.entry.amount_cents} />)</> : " (D 646 / C 4311, extournée à l'ouverture)"}</Text>
              {editable && (v.accrual.entry
                ? <Button size="compact-xs" variant="subtle" color="brique" loading={remove.isPending} onClick={() => run(remove.mutateAsync(undefined))}>Supprimer l'écriture</Button>
                : v.accrual.amount_cents > 0 && <Button size="compact-xs" variant="light" loading={post.isPending} onClick={() => run(post.mutateAsync(undefined))}>Passer la charge à payer</Button>)}
            </Group>)}
        </>)}
      {v.mode === "company" && (
        <>
          <Text size="sm" mb="xs">Cotisations des associés débitées de leur compte courant 455 : sans charge pour la société. Part déductible sur la
            quote-part de chaque associé (cotisations et CSG déductible), à valider avec l'expert-comptable.</Text>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Associé</Table.Th><Table.Th ta="right">Appels de l'exercice</Table.Th>
              <Table.Th ta="right">Part déductible</Table.Th><Table.Th ta="right">CSG non déd. + CRDS</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {v.associates.map((a) => (
                <Table.Tr key={a.person_id}><Table.Td>{a.name}{a.missing_split > 0 && <Text size="xs" c="dimmed">{a.missing_split} appel(s) sans détail</Text>}</Table.Td>
                  <Table.Td ta="right"><MoneyText cents={a.calls_cents} /></Table.Td><Table.Td ta="right"><MoneyText cents={a.deductible_cents} /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={a.non_deductible_cents} /></Table.Td></Table.Tr>))}
            </Table.Tbody>
          </Table>
        </>)}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
    </Paper>
  );
}
