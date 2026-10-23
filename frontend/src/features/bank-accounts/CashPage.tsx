// Banque › Caisse : mouvements d'une caisse (entrées, sorties, dépôts en banque) avec solde
// courant ; saisie d'un mouvement (compte de contrepartie, projet) et dépôt d'espèces en banque
// (par le compte 581 : ni recette ni dépense).
import { useState } from "react";
import { useParams } from "react-router";
import { Anchor, Badge, Button, Center, Group, Input, Loader, Paper, SegmentedControl, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { AccountSelect } from "../../components/AccountSelect";
import { Can } from "../../components/Can";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import type { Account } from "../../lib/types";
import { AppLink } from "../../app/navigation";
import { useProjectOptions } from "../projects/LineProjectModal";
import { BANK_ACCOUNTS_KEY, type BankAccount } from "./types";

interface Row { line_id: number; entry_id: number; date: string; reference: string | null; label: string; counterpart: string;
  amount_cents: number; balance_cents: number; deposit: boolean }
interface CashView { item: BankAccount; banks: { value: string; label: string }[]; opening_cents: number; closing_cents: number; rows: Row[] }

const today = () => new Date().toISOString().slice(0, 10);

export default function CashPage() {
  const id = Number(useParams().ba_id);
  const key = ["cash", id];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<CashView>(`/api/v1/bank-accounts/${id}/cash`) });
  const [form, setForm] = useState<"movement" | "deposit" | null>(null);
  if (!data) return <Center h={300}><Loader /></Center>;
  return (
    <>
      <PageHeader title={data.item.label} description={`Caisse · compte ${data.item.account.code} ${data.item.account.label}`}
        actions={<>
          <Button variant="default" component={AppLink} href="/bank-accounts/">Comptes</Button>
          <Can><Button variant="default" onClick={() => setForm("deposit")} disabled={!data.banks.length}>Dépôt en banque</Button>
            <Button onClick={() => setForm("movement")}>Nouveau mouvement</Button></Can>
        </>} />
      <Group mb="md" gap="xl">
        <div><Text size="sm" c="dimmed">Solde de la caisse</Text>
          <Text fz={24} fw={500} className="lv-num"><MoneyText cents={data.closing_cents} anomaly={data.closing_cents < 0} /></Text></div>
      </Group>
      <Paper p={0} style={{ overflowX: "auto" }}>
        <Table verticalSpacing={6} miw={720}>
          <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Pièce</Table.Th><Table.Th>Libellé</Table.Th>
            <Table.Th>Contrepartie</Table.Th><Table.Th ta="right">Entrée</Table.Th><Table.Th ta="right">Sortie</Table.Th><Table.Th ta="right">Solde</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.rows.map((r) => (
              <Table.Tr key={r.line_id}>
                <Table.Td className="lv-num">{formatDate(r.date)}</Table.Td>
                <Table.Td><Anchor component={AppLink} href={`/entries/${r.entry_id}`} size="sm" className="lv-num">{r.reference}</Anchor></Table.Td>
                <Table.Td><Text size="sm">{r.label}{r.deposit && <Badge ml="xs" size="xs" variant="light" color="ardoise">dépôt en banque</Badge>}</Text></Table.Td>
                <Table.Td className="lv-num">{r.counterpart}</Table.Td>
                <Table.Td ta="right">{r.amount_cents > 0 && <MoneyText cents={r.amount_cents} size="sm" />}</Table.Td>
                <Table.Td ta="right">{r.amount_cents < 0 && <MoneyText cents={-r.amount_cents} size="sm" />}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={r.balance_cents} size="sm" anomaly={r.balance_cents < 0} /></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {data.rows.length === 0 && <Text size="sm" c="dimmed" p="md">Aucun mouvement : saisissez les entrées et sorties d'espèces.</Text>}
      </Paper>
      <FormModal opened={form === "movement"} onClose={() => setForm(null)} title="Nouveau mouvement de caisse">
        {form === "movement" && <MovementForm id={id} invalidate={key} onDone={() => setForm(null)} />}
      </FormModal>
      <FormModal opened={form === "deposit"} onClose={() => setForm(null)} title="Dépôt d'espèces en banque">
        {form === "deposit" && <DepositForm id={id} banks={data.banks} balance={data.closing_cents} invalidate={key} onDone={() => setForm(null)} />}
      </FormModal>
    </>
  );
}

function MovementForm({ id, invalidate, onDone }: { id: number; invalidate: unknown[]; onDone: () => void }) {
  const projects = useProjectOptions().data?.items ?? [];
  const [direction, setDirection] = useState("in");
  const [when, setWhen] = useState<string | null>(today());
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState<number | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [project, setProject] = useState<string | null>(null);
  const save = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/bank-accounts/${id}/cash`, {
    date: when, label, direction, amount_cents: amount, account_id: account?.id, project_id: project ? Number(project) : null,
  }), { invalidate: [invalidate, BANK_ACCOUNTS_KEY] });
  return (
    <Stack>
      <SegmentedControl value={direction} onChange={setDirection}
        data={[{ value: "in", label: "Entrée d'espèces (recette)" }, { value: "out", label: "Sortie d'espèces (dépense)" }]} />
      <Group grow>
        <DateInput label="Date" required valueFormat="DD/MM/YYYY" value={when} onChange={setWhen} />
        <MoneyInput label="Montant" required value={amount} onChange={setAmount} />
      </Group>
      <TextInput label="Libellé" required placeholder={direction === "in" ? "Vente buvette, cotisations…" : "Achat de fournitures…"}
        value={label} onChange={(e) => setLabel(e.currentTarget.value)} data-autofocus />
      <Input.Wrapper label={direction === "in" ? "Compte de produit (ou de tiers)" : "Compte de charge (ou de tiers)"} required>
        <AccountSelect label="Compte de contrepartie" recentsScope="cash" value={account} onChange={setAccount} />
      </Input.Wrapper>
      {projects.length > 0 && <Select label="Projet" clearable searchable data={projects} value={project} onChange={setProject} />}
      <Group justify="flex-end">
        <Button variant="default" onClick={onDone}>Annuler</Button>
        <Button loading={save.isPending} disabled={!when || !label.trim() || !amount || !account}
          onClick={() => save.mutate(undefined, { onSuccess: onDone })}>Enregistrer</Button>
      </Group>
    </Stack>
  );
}

function DepositForm({ id, banks, balance, invalidate, onDone }: {
  id: number; banks: { value: string; label: string }[]; balance: number; invalidate: unknown[]; onDone: () => void;
}) {
  const [when, setWhen] = useState<string | null>(today());
  const [amount, setAmount] = useState<number | null>(balance > 0 ? balance : null);
  const [bank, setBank] = useState<string | null>(banks[0]?.value ?? null);
  const save = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/bank-accounts/${id}/cash/deposit`, {
    date: when, amount_cents: amount, bank_account_id: bank ? Number(bank) : null,
  }), { invalidate: [invalidate, BANK_ACCOUNTS_KEY] });
  return (
    <Stack>
      <Text size="sm">Le dépôt passe par le compte 581 (virements internes) : la caisse diminue, la banque augmente,
        sans recette ni dépense. La ligne bancaire se rapprochera du relevé.</Text>
      <Group grow>
        <DateInput label="Date du dépôt" required valueFormat="DD/MM/YYYY" value={when} onChange={setWhen} />
        <MoneyInput label="Montant" required value={amount} onChange={setAmount} />
      </Group>
      <Select label="Compte bancaire" required data={banks} value={bank} onChange={setBank} allowDeselect={false} />
      <Group justify="flex-end">
        <Button variant="default" onClick={onDone}>Annuler</Button>
        <Button loading={save.isPending} disabled={!when || !amount || !bank} onClick={() => save.mutate(undefined, { onSuccess: onDone })}>
          Enregistrer le dépôt</Button>
      </Group>
    </Stack>
  );
}
