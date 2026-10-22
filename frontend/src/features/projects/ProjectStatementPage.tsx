// Compte de résultat d'un projet sur une période, pour un financeur : charges et produits par
// compte, détail des lignes avec leur pièce ; impression (PDF) et export tableur.
import { Anchor, Button, Center, Group, Loader, Paper, SimpleGrid, Table, Text, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { Download, Paperclip, Printer } from "lucide-react";
import { api } from "../../api/client";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { PROJECTS_KEY, type Project } from "./ProjectsPage";

interface Statement {
  project: Project; start: string; end: string; export_url: string;
  accounts: { code: string; label: string; kind: "expense" | "income"; amount_cents: number }[];
  lines: { date: string; reference: string | null; entry_url: string; label: string; account: string;
    kind: "expense" | "income"; amount_cents: number; document_url: string | null }[];
  totals: { expense_cents: number; income_cents: number; result_cents: number };
}

export default function ProjectStatementPage() {
  const id = Number(useParams().project_id);
  const [params, setParams] = useUrlParams({ start: "", end: "" });
  const url = `/api/v1/projects/${id}/statement?start=${params.start}&end=${params.end}`;
  const { data } = useQuery({ queryKey: [...PROJECTS_KEY, "statement", url], placeholderData: (prev) => prev,
    queryFn: () => api.get<Statement>(url) });
  if (!data) return <Center h={300}><Loader /></Center>;
  const sections = [{ kind: "expense", title: "Charges", total: data.totals.expense_cents },
    { kind: "income", title: "Produits", total: data.totals.income_cents }] as const;
  return (
    <>
      <PageHeader title={`Projet « ${data.project.name} »`}
        description={`Compte de résultat du ${formatDate(data.start)} au ${formatDate(data.end)}${data.project.manager ? ` · responsable : ${data.project.manager}` : ""}`}
        actions={<>
          <Button variant="default" component={AppLink} href="/projects/" className="lv-no-print">Projets</Button>
          <Button variant="default" component="a" href={data.export_url} leftSection={<Download size={16} />}>Exporter (XLSX)</Button>
          <Button variant="default" leftSection={<Printer size={16} />} onClick={() => window.print()}>Imprimer</Button>
        </>} />
      <FilterBar>
        <DateInput label="Du" w={160} valueFormat="DD/MM/YYYY" value={params.start || data.start}
          onChange={(v) => setParams({ ...params, start: v ?? "" })} />
        <DateInput label="Au" w={160} valueFormat="DD/MM/YYYY" value={params.end || data.end}
          onChange={(v) => setParams({ ...params, end: v ?? "" })} />
      </FilterBar>
      {data.project.description && <Text mb="md">{data.project.description}</Text>}
      <SimpleGrid cols={{ base: 1, sm: 2 }} mb="md">
        {sections.map((s) => (
          <Paper p={0} key={s.kind}>
            <Table verticalSpacing={6}>
              <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th>{s.title}</Table.Th><Table.Th ta="right">Montant</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {data.accounts.filter((a) => a.kind === s.kind).map((a) => (
                  <Table.Tr key={a.code}><Table.Td><Text size="sm"><span className="lv-num">{a.code}</span> {a.label}</Text></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={a.amount_cents} size="sm" /></Table.Td></Table.Tr>
                ))}
              </Table.Tbody>
              <Table.Tfoot><Table.Tr><Table.Th>Total {s.title.toLowerCase()}</Table.Th><Table.Th ta="right"><MoneyText cents={s.total} /></Table.Th></Table.Tr></Table.Tfoot>
            </Table>
          </Paper>
        ))}
      </SimpleGrid>
      <Group justify="flex-end" mb="lg">
        <Text fw={700}>{data.totals.result_cents >= 0 ? "Excédent" : "Déficit"} :</Text>
        <MoneyText cents={data.totals.result_cents} fw={700} anomaly={data.totals.result_cents < 0} />
      </Group>
      <Title order={2} size="h4" mb="xs">Détail des opérations</Title>
      <Paper p={0} style={{ overflowX: "auto" }}>
        <Table verticalSpacing={4} miw={700}>
          <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Pièce</Table.Th><Table.Th>Libellé</Table.Th>
            <Table.Th>Compte</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th>Justificatif</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.lines.map((l, i) => (
              <Table.Tr key={i}>
                <Table.Td className="lv-num">{formatDate(l.date)}</Table.Td>
                <Table.Td><Anchor component={AppLink} href={l.entry_url} size="sm" className="lv-num">{l.reference ?? "—"}</Anchor></Table.Td>
                <Table.Td><Text size="sm">{l.label}</Text></Table.Td>
                <Table.Td className="lv-num">{l.account}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={l.kind === "expense" ? -l.amount_cents : l.amount_cents} size="sm" /></Table.Td>
                <Table.Td>{l.document_url && <Anchor href={l.document_url} target="_blank" size="sm"><Paperclip size={14} /> facture</Anchor>}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>
      {data.lines.length === 0 && <Text size="sm" c="dimmed" mt="sm">Aucune opération affectée au projet sur la période.</Text>}
      <Text size="xs" c="dimmed" mt="md" className="lv-print-only">Imprimé le {new Date().toLocaleDateString("fr-FR")}</Text>
    </>
  );
}
