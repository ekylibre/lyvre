// Ventes › Décomptes de coopérative (lot AG10.d) : apports, compléments de prix, ristournes (ventes 70x),
// acomptes déjà versés, parts sociales retenues (2621), frais ; une écriture unique au journal des ventes,
// activité et campagne par ligne de vente (analytique AG8). Brouillon modifiable, retour en brouillon possible.
import { useState } from "react";
import {
  ActionIcon, Alert, Anchor, Button, FileInput, Group, List, Paper, Select, SimpleGrid, Stack, Table, Text, TextInput,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { Can } from "../../components/Can";
import { ConfirmButton } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";

export const COOP_KEY = ["coop-statements"] as const;

type Kind = "delivery" | "complement" | "rebate" | "advance" | "shares" | "fee";

export interface CoopLine {
  kind: Kind; label: string; quantity: string; unit: string; amount: string; vat_rate: string; account_code: string;
  activity_id: string; campaign_year: string;
}

interface Totals {
  sales_cents: number; sales_vat_cents: number; advances_cents: number; shares_cents: number; fees_cents: number;
  fees_vat_cents: number; customer_cents: number; net_cents: number;
}

export interface CoopRow extends Totals {
  id: number; number: string; statement_date: string; label: string; status: "draft" | "posted"; status_label: string;
  entity: { id: number; name: string };
}

export interface CoopDetail extends CoopRow {
  entity_id: string; journal_code?: string; lines: (CoopLine & { id: number; amount_cents: number; vat_cents: number })[]; problems: string[];
  journal_entry: { id: number; reference: string } | null; attachment: { name: string; url: string } | null;
}

interface Options {
  entities: { value: string; label: string; group?: string; journal?: string }[]; journals?: { value: string; label: string }[]; kinds: { value: Kind; label: string }[];
  accounts: { value: string; label: string }[]; activities: { value: string; label: string }[];
}

const SALE_KINDS: Kind[] = ["delivery", "complement", "rebate"];
const blank = (kind: Kind = "delivery"): CoopLine =>
  ({ kind, label: "", quantity: "", unit: "", amount: "", vat_rate: "", account_code: "", activity_id: "", campaign_year: "" });

export function CoopTotals({ t }: { t: Totals }) {
  return (
    <SimpleGrid cols={{ base: 2, md: 4 }}>
      <Paper p="sm"><Text size="sm" c="dimmed">Ventes HT (+ TVA)</Text><MoneyText cents={t.sales_cents} fw={700} />
        <Text size="xs" c="dimmed">TVA <MoneyText cents={t.sales_vat_cents} size="xs" /></Text></Paper>
      <Paper p="sm"><Text size="sm" c="dimmed">Retenues</Text><MoneyText cents={t.shares_cents + t.fees_cents + t.fees_vat_cents} fw={700} />
        <Text size="xs" c="dimmed">parts <MoneyText cents={t.shares_cents} size="xs" /> · frais TTC <MoneyText cents={t.fees_cents + t.fees_vat_cents} size="xs" /></Text></Paper>
      <Paper p="sm"><Text size="sm" c="dimmed">Acomptes déjà versés</Text><MoneyText cents={t.advances_cents} fw={700} /></Paper>
      <Paper p="sm"><Text size="sm" c="dimmed">Net à payer</Text><MoneyText cents={t.net_cents} fw={700} />
        <Text size="xs" c="dimmed">au compte client <MoneyText cents={t.customer_cents} size="xs" /></Text></Paper>
    </SimpleGrid>
  );
}

/** Saisie d'un décompte : en-tête, lignes typées, pièce jointe ; enregistrement en brouillon. */
export function CoopForm({ statement, options, onDone }: { statement?: CoopDetail; options: Options; onDone: (s?: CoopDetail) => void }) {
  const [head, setHead] = useState({
    entity_id: statement?.entity_id ?? "", number: statement?.number ?? "", statement_date: statement?.statement_date ?? "",
    label: statement?.label ?? "", journal_code: statement?.journal_code ?? "",
  });
  const groups = options.entities.reduce<{ group: string; items: { value: string; label: string }[] }[]>((acc, e) => {
    const name = e.group ?? "Tiers";
    const g = acc.find((x) => x.group === name);
    if (g) g.items.push({ value: e.value, label: e.label }); else acc.push({ group: name, items: [{ value: e.value, label: e.label }] });
    return acc;
  }, []);
  const journalOf = (id: string) => options.entities.find((e) => e.value === id)?.journal ?? "";
  const [lines, setLines] = useState<CoopLine[]>(statement?.lines.map(({ id: _id, amount_cents: _a, vat_cents: _v, ...l }) => l) ?? [blank()]);
  const [file, setFile] = useState<File | null>(null);
  const set = (i: number, patch: Partial<CoopLine>) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const save = useAction(async () => {
    let attachment_token: string | undefined;
    if (file) {
      const form = new FormData();
      form.append("invoice_file", file);
      attachment_token = (await upload<{ token: string }>("/api/v1/purchases/stage", form)).token;
    }
    const body = { ...head, lines, attachment_token };
    return statement ? api.put<{ item: CoopDetail; notices: Notice[] }>(`/api/v1/coop-statements/${statement.id}`, body)
      : api.post<{ item: CoopDetail; notices: Notice[] }>("/api/v1/coop-statements", body);
  }, { invalidate: [COOP_KEY] });
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined, { onSuccess: (r) => onDone(r.item) }); }}>
      <Stack>
        <SimpleGrid cols={{ base: 1, md: 5 }}>
          <Select label="Coopérative" required searchable data={groups} value={head.entity_id || null}
            onChange={(v) => setHead({ ...head, entity_id: v ?? "", journal_code: v ? journalOf(v) : head.journal_code })} />
          {options.journals && (
            <Select label="Journal" placeholder="Ventes (VE)" data={options.journals}
              value={head.journal_code || null} onChange={(v) => setHead({ ...head, journal_code: v ?? "" })} clearable />)}
          <TextInput label="N° du décompte" required value={head.number} onChange={(e) => setHead({ ...head, number: e.currentTarget.value })} />
          <TextInput label="Date" type="date" required value={head.statement_date}
            onChange={(e) => setHead({ ...head, statement_date: e.currentTarget.value })} />
          <TextInput label="Libellé" value={head.label} onChange={(e) => setHead({ ...head, label: e.currentTarget.value })} />
        </SimpleGrid>
        <Table.ScrollContainer minWidth={1100}>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Type</Table.Th><Table.Th>Désignation</Table.Th><Table.Th>Qté</Table.Th><Table.Th>Unité</Table.Th>
              <Table.Th>Montant HT</Table.Th><Table.Th>TVA %</Table.Th><Table.Th>Compte</Table.Th><Table.Th>Activité</Table.Th>
              <Table.Th>Campagne</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>
              {lines.map((l, i) => {
                const sale = SALE_KINDS.includes(l.kind);
                return (
                  <Table.Tr key={i}>
                    <Table.Td miw={170}><Select size="xs" data={options.kinds} value={l.kind} aria-label={`Type de la ligne ${i + 1}`}
                      onChange={(v) => set(i, { kind: (v ?? "delivery") as Kind, ...(SALE_KINDS.includes(v as Kind) ? {} : { activity_id: "", campaign_year: "" }) })} /></Table.Td>
                    <Table.Td miw={160}><TextInput size="xs" value={l.label} aria-label={`Désignation de la ligne ${i + 1}`}
                      onChange={(e) => set(i, { label: e.currentTarget.value })} /></Table.Td>
                    <Table.Td w={80}><TextInput size="xs" value={l.quantity} onChange={(e) => set(i, { quantity: e.currentTarget.value })} /></Table.Td>
                    <Table.Td w={70}><TextInput size="xs" value={l.unit} onChange={(e) => set(i, { unit: e.currentTarget.value })} /></Table.Td>
                    <Table.Td w={110}><TextInput size="xs" value={l.amount} aria-label={`Montant de la ligne ${i + 1}`}
                      onChange={(e) => set(i, { amount: e.currentTarget.value })} /></Table.Td>
                    <Table.Td w={70}><TextInput size="xs" value={l.vat_rate} disabled={l.kind === "advance" || l.kind === "shares"}
                      onChange={(e) => set(i, { vat_rate: e.currentTarget.value })} /></Table.Td>
                    <Table.Td miw={200}>{l.kind !== "advance" && <Select size="xs" searchable clearable data={options.accounts}
                      value={l.account_code || null} placeholder="proposé" onChange={(v) => set(i, { account_code: v ?? "" })} />}</Table.Td>
                    <Table.Td miw={160}>{sale && <Select size="xs" searchable clearable data={options.activities} value={l.activity_id || null}
                      onChange={(v) => set(i, { activity_id: v ?? "" })} />}</Table.Td>
                    <Table.Td w={90}>{sale && <TextInput size="xs" value={l.campaign_year} placeholder="auto"
                      onChange={(e) => set(i, { campaign_year: e.currentTarget.value })} />}</Table.Td>
                    <Table.Td><ActionIcon variant="subtle" aria-label={`Retirer la ligne ${i + 1}`}
                      onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}><Trash2 size={16} /></ActionIcon></Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Group justify="space-between">
          <Button variant="default" size="compact-sm" leftSection={<Plus size={14} />} onClick={() => setLines((ls) => [...ls, blank()])}>Ligne</Button>
          <FileInput size="xs" w={260} clearable placeholder={statement?.attachment?.name ?? "Pièce (PDF, photo)"} value={file} onChange={setFile}
            accept="application/pdf,image/jpeg,image/png" aria-label="Pièce jointe" />
        </Group>
        <Text size="xs" c="dimmed">Montants HT positifs : le type donne le sens. Sans compte, Lyvre propose celui de l'activité, de la désignation
          déjà reçue, ou 2621 pour les parts. Un acompte n'est pas comptabilisé (déjà crédité au compte client à son encaissement).</Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={() => onDone()}>Annuler</Button>
          <Button type="submit" loading={save.isPending}>Enregistrer le brouillon</Button>
        </Group>
      </Stack>
    </form>
  );
}

export default function CoopStatementsPage() {
  const { data, isFetching } = useList<CoopRow>(COOP_KEY, "/api/v1/coop-statements");
  const options = useQuery({ queryKey: [...COOP_KEY, "options"], queryFn: () => api.get<Options>("/api/v1/coop-statements/form-options") });
  const [openId, setOpenId] = useState<number | null>(null);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const detail = useQuery({ queryKey: [...COOP_KEY, openId], enabled: openId != null,
    queryFn: () => api.get<{ item: CoopDetail }>(`/api/v1/coop-statements/${openId}`) });
  const act = useAction((path: string) => api.post<{ item: CoopDetail; notices: Notice[] }>(`/api/v1/coop-statements/${openId}/${path}`),
    { invalidate: [COOP_KEY] });
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/coop-statements/${openId}`), { invalidate: [COOP_KEY] });
  const s = detail.data?.item;
  const columns: GridColumn<CoopRow>[] = [
    { accessor: "number", title: "N°", hideable: false,
      render: (r) => <Anchor size="sm" className="lv-num" onClick={() => setOpenId(r.id)}>{r.number}</Anchor> },
    { accessor: "entity", title: "Coopérative", render: (r) => r.entity.name },
    { accessor: "statement_date", title: "Date", render: (r) => <span className="lv-num">{formatDate(r.statement_date)}</span> },
    { accessor: "sales_cents", title: "Ventes HT", textAlign: "right", render: (r) => <MoneyText cents={r.sales_cents} size="sm" /> },
    { accessor: "net_cents", title: "Net à payer", textAlign: "right", render: (r) => <MoneyText cents={r.net_cents} size="sm" /> },
    { accessor: "status", title: "Statut", render: (r) => <StatusBadge tone={r.status === "posted" ? "ok" : "todo"}>{r.status_label}</StatusBadge> },
  ];
  return (
    <>
      <PageHeader title="Décomptes de coopérative"
        description="Apports, compléments de prix, ristournes, acomptes, parts sociales et frais : une écriture au journal des ventes ou à celui de la coopérative, sur le compte de la coopérative ; activité et campagne par apport."
        actions={<Can><Button onClick={() => setEditing("new")}>Nouveau décompte</Button></Can>} />
      <DataGrid id="coop-statements" records={data?.items} columns={columns} fetching={isFetching} emptyText="Aucun décompte saisi." />

      {s && openId != null && editing == null && (
        <FormModal opened onClose={() => setOpenId(null)} title={`Décompte ${s.number} — ${s.entity.name}`} size="xl">
          <Stack>
            <Group gap="xs"><StatusBadge tone={s.status === "posted" ? "ok" : "todo"}>{s.status_label}</StatusBadge>
              <Text size="sm">{formatDate(s.statement_date)}{s.label && ` · ${s.label}`}</Text>
              {s.journal_entry && <Anchor component={AppLink} href={`/entries/${s.journal_entry.id}`} size="sm" className="lv-num">{s.journal_entry.reference}</Anchor>}
              {s.attachment && <Anchor href={s.attachment.url} target="_blank" size="sm">{s.attachment.name}</Anchor>}</Group>
            {s.problems.length > 0 && <Alert color="paille" title="À compléter avant de comptabiliser :">
              <List size="sm">{s.problems.map((p) => <List.Item key={p}>{p}</List.Item>)}</List></Alert>}
            <CoopTotals t={s} />
            <Table>
              <Table.Tbody>{s.lines.map((l) => <Table.Tr key={l.id}>
                <Table.Td>{options.data?.kinds.find((k) => k.value === l.kind)?.label}</Table.Td><Table.Td>{l.label}</Table.Td>
                <Table.Td className="lv-num">{l.quantity} {l.unit}</Table.Td><Table.Td className="lv-num">{l.account_code}</Table.Td>
                <Table.Td>{options.data?.activities.find((a) => a.value === l.activity_id)?.label}{l.campaign_year && ` ${l.campaign_year}`}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={l.amount_cents} size="sm" /></Table.Td>
                <Table.Td ta="right" c="dimmed">{l.vat_cents ? <MoneyText cents={l.vat_cents} size="sm" /> : ""}</Table.Td></Table.Tr>)}</Table.Tbody>
            </Table>
            <Can><Group justify="flex-end">
              {s.status === "draft" && <>
                <ConfirmButton title="Supprimer ce décompte ?" confirmLabel="Supprimer" loading={remove.isPending}
                  onConfirm={() => remove.mutate(undefined, { onSuccess: () => setOpenId(null) })}>Supprimer</ConfirmButton>
                <Button variant="default" onClick={() => setEditing(s.id)}>Modifier</Button>
                <Button disabled={s.problems.length > 0} loading={act.isPending} onClick={() => act.mutate("post")}>Comptabiliser</Button>
              </>}
              {s.status === "posted" && <ConfirmButton danger={false} title="Repasser en brouillon ?" confirmLabel="Repasser en brouillon"
                message="L'écriture du décompte est supprimée (refusé si elle est validée : contrepassez-la)." loading={act.isPending}
                onConfirm={() => act.mutate("unpost")}>Repasser en brouillon</ConfirmButton>}
            </Group></Can>
          </Stack>
        </FormModal>
      )}
      {editing != null && options.data && (
        <FormModal opened onClose={() => setEditing(null)} title={editing === "new" ? "Nouveau décompte" : `Modifier le décompte ${s?.number ?? ""}`} size="100%">
          <CoopForm statement={editing === "new" ? undefined : s} options={options.data}
            onDone={(item) => { setEditing(null); if (item) setOpenId(item.id); }} />
        </FormModal>
      )}
    </>
  );
}
