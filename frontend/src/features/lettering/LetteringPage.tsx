// Compta › Lettrage (lot F3) : comptes de tiers lettrables, lignes d'un compte (non lettrées,
// lettrées, toutes), sélection au clavier (Espace coche, Entrée lettre), total en direct, lettrage
// avec écart sous le seuil, propositions à accepter, délettrage.
import { useMemo, useState, type KeyboardEvent } from "react";
import { Alert, Anchor, Badge, Button, Checkbox, Group, Paper, SegmentedControl, Select, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { Can } from "../../components/Can";
import { useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";

export const LETTERING_KEY = ["lettering"];

interface AccountRow { id: number; code: string; label: string; open_lines: number; open_balance_cents: number }
interface Line {
  id: number; entry_id: number; reference: string | null; journal: string; date: string; label: string;
  debit_cents: number; credit_cents: number; carried: boolean;
  lettering: { id: number; code: string; partial: boolean; origin: string } | null;
}
interface LinesResponse { account: { id: number; code: string; label: string }; items: Line[]; open_balance_cents: number }
interface Proposal { kind: "pair" | "combination"; line_ids: number[]; amount_cents: number }


export default function LetteringPage() {
  const can = useCan();
  const [params, setParams] = useUrlParams({ account: "", state: "open" });
  const accounts = useQuery({ queryKey: [...LETTERING_KEY, "accounts"],
    queryFn: () => api.get<{ items: AccountRow[]; gap_threshold_cents: number }>("/api/v1/lettering/accounts") });
  const firstOpen = accounts.data?.items.find((a) => a.open_lines > 0) ?? accounts.data?.items[0];
  const accountId = params.account || (firstOpen ? String(firstOpen.id) : "");
  const lines = useQuery({ queryKey: [...LETTERING_KEY, "lines", accountId, params.state], enabled: !!accountId,
    queryFn: () => api.get<LinesResponse>(`/api/v1/lettering/accounts/${accountId}/lines?state=${params.state}`) });
  const proposals = useQuery({ queryKey: [...LETTERING_KEY, "proposals", accountId], enabled: !!accountId && params.state === "open",
    queryFn: () => api.get<{ items: Proposal[] }>(`/api/v1/lettering/accounts/${accountId}/proposals`) });
  const [selected, setSelected] = useState<number[]>([]);
  const letter = useAction((body: { line_ids: number[]; gap?: boolean; proposal?: boolean }) =>
    api.post<{ notices: Notice[] }>("/api/v1/lettering", body), { invalidate: [LETTERING_KEY] });
  const reprise = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/lettering/reprise", {}), { invalidate: [LETTERING_KEY] });
  const unletter = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/lettering/${id}`), { invalidate: [LETTERING_KEY] });

  const items = lines.data?.items ?? [];
  const byId = useMemo(() => new Map(items.map((l) => [l.id, l])), [items]);
  const chosen = selected.map((id) => byId.get(id)).filter((l): l is Line => !!l);
  const debit = chosen.reduce((s, l) => s + l.debit_cents, 0);
  const credit = chosen.reduce((s, l) => s + l.credit_cents, 0);
  const balance = debit - credit;
  const threshold = accounts.data?.gap_threshold_cents ?? 100;
  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const submit = (gap = false) => {
    if (chosen.length < 2) return;
    letter.mutate({ line_ids: selected, gap }, { onSuccess: () => setSelected([]) });
  };
  const onRowKey = (event: KeyboardEvent<HTMLTableRowElement>, line: Line) => {
    if (event.key === " ") { event.preventDefault(); toggle(line.id); }
    if (event.key === "Enter") { event.preventDefault(); submit(); }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next = (event.key === "ArrowDown" ? event.currentTarget.nextElementSibling : event.currentTarget.previousElementSibling) as HTMLElement | null;
      next?.focus();
    }
  };
  const accountOptions = (accounts.data?.items ?? []).map((a) => ({ value: String(a.id),
    label: `${a.code} — ${a.label} (${a.open_lines} ligne(s) ouverte(s))` }));
  if (lines.data && !accountOptions.some((o) => o.value === accountId)) {
    accountOptions.push({ value: accountId, label: `${lines.data.account.code} — ${lines.data.account.label}` });
  }
  const selectable = (l: Line) => can.write && (!l.lettering || l.lettering.partial);
  const proposalText = (p: Proposal) => p.line_ids.map((id) => byId.get(id)).filter(Boolean)
    .map((l) => `${l!.reference ?? `#${l!.entry_id}`} (${formatDate(l!.date)})`).join(" + ");

  return (
    <>
      <PageHeader title="Lettrage" description="Rapprochez les lignes d'un compte de tiers qui se soldent : facture et règlement, avoir, acompte. Les factures de Lyvre se lettrent seules à l'encaissement."
        actions={can.instanceAdmin ? <Button variant="default" loading={reprise.isPending} onClick={() => reprise.mutate(undefined)}
          title="Factures de vente et d'achat déjà payées avant le lettrage">Lettrer les pièces déjà payées</Button> : undefined} />
      <Group align="flex-end" mb="md">
        <Select label="Compte" searchable data={accountOptions} value={accountId || null} w={420} nothingFoundMessage="Aucun compte"
          onChange={(v) => { setSelected([]); setParams({ account: v ?? "" }); }} />
        <SegmentedControl value={params.state} onChange={(v) => { setSelected([]); setParams({ state: v }); }}
          data={[{ value: "open", label: "Non lettrées" }, { value: "lettered", label: "Lettrées" }, { value: "all", label: "Toutes" }]} />
        {lines.data && <Text size="sm">Solde non lettré : <MoneyText cents={lines.data.open_balance_cents} /></Text>}
      </Group>
      {!accountId && accounts.isSuccess && <Alert color="ardoise" variant="light">Aucun compte de tiers à lettrer.</Alert>}

      {!!proposals.data?.items.length && can.write && (
        <Paper p="md" mb="md">
          <Group justify="space-between" mb="xs">
            <Title order={3} size="h5">{`Propositions (${proposals.data.items.length})`}</Title>
            <Button size="compact-sm" variant="default" loading={letter.isPending}
              onClick={() => proposals.data!.items.forEach((p) => letter.mutate({ line_ids: p.line_ids, proposal: true }))}>Tout accepter</Button>
          </Group>
          <Stack gap={4}>
            {proposals.data.items.map((p) => (
              <Group key={p.line_ids.join("-")} justify="space-between" wrap="nowrap">
                <Text size="sm">{proposalText(p)} · <MoneyText cents={p.amount_cents} size="sm" />
                  {p.kind === "combination" && <Text span size="xs" c="dimmed"> (combinaison)</Text>}</Text>
                <Button size="compact-sm" variant="subtle" onClick={() => letter.mutate({ line_ids: p.line_ids, proposal: true })}>Accepter</Button>
              </Group>
            ))}
          </Stack>
        </Paper>
      )}

      {accountId && (
        <Paper p={0} style={{ overflowX: "auto" }}>
          <Table verticalSpacing="xs" highlightOnHover>
            <Table.Thead bg="var(--lv-sauge)"><Table.Tr>
              <Table.Th w={36} /><Table.Th>Date</Table.Th><Table.Th>Pièce</Table.Th><Table.Th>Libellé</Table.Th>
              <Table.Th ta="right">Débit</Table.Th><Table.Th ta="right">Crédit</Table.Th><Table.Th>Lettrage</Table.Th>
            </Table.Tr></Table.Thead>
            <Table.Tbody>
              {items.map((l) => (
                <Table.Tr key={l.id} tabIndex={0} onKeyDown={(e) => onRowKey(e, l)}
                  bg={selected.includes(l.id) ? "var(--lv-sauge)" : undefined} aria-selected={selected.includes(l.id)}>
                  <Table.Td>{selectable(l) && <Checkbox aria-label={`Sélectionner ${l.reference ?? l.id}`} checked={selected.includes(l.id)}
                    onChange={() => toggle(l.id)} tabIndex={-1} />}</Table.Td>
                  <Table.Td className="lv-num">{formatDate(l.date)}</Table.Td>
                  <Table.Td><Anchor component={AppLink} href={`/entries/${l.entry_id}`} size="sm" className="lv-num">{l.reference ?? `#${l.entry_id}`}</Anchor>
                    {l.carried && <Text span size="xs" c="dimmed"> à-nouveau</Text>}</Table.Td>
                  <Table.Td><Text size="sm" lineClamp={1}>{l.label}</Text></Table.Td>
                  <Table.Td ta="right">{l.debit_cents ? <MoneyText cents={l.debit_cents} /> : null}</Table.Td>
                  <Table.Td ta="right">{l.credit_cents ? <MoneyText cents={l.credit_cents} /> : null}</Table.Td>
                  <Table.Td>{l.lettering && <Group gap={4} wrap="nowrap">
                    <Badge variant="light" color={l.lettering.partial ? "paille" : "lichen"} title={l.lettering.partial ? "Lettrage partiel" : "Lettré"}>{l.lettering.code}</Badge>
                    <Can><Button size="compact-xs" variant="subtle" onClick={() => unletter.mutate(l.lettering!.id)}>Délettrer</Button></Can>
                  </Group>}</Table.Td>
                </Table.Tr>
              ))}
              {!items.length && lines.isSuccess && <Table.Tr><Table.Td colSpan={7}><Text size="sm" c="dimmed">Aucune ligne.</Text></Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        </Paper>
      )}

      {chosen.length > 0 && (
        <Paper p="sm" mt="sm" withBorder style={{ position: "sticky", bottom: 8 }}>
          <Group justify="space-between">
            <Text size="sm">{chosen.length} ligne(s) · débit <MoneyText cents={debit} /> · crédit <MoneyText cents={credit} /> · solde{" "}
              <MoneyText cents={balance} c={balance ? "var(--lv-brique)" : "var(--lv-lichen-strong)"} /></Text>
            <Group gap="xs">
              <Button variant="default" onClick={() => setSelected([])}>Effacer</Button>
              {balance !== 0 && Math.abs(balance) <= threshold &&
                <Button variant="default" loading={letter.isPending} onClick={() => submit(true)}>Lettrer avec écart</Button>}
              <Button loading={letter.isPending} disabled={chosen.length < 2} onClick={() => submit()}>
                {balance === 0 ? "Lettrer (Entrée)" : "Lettrer en partiel"}</Button>
            </Group>
          </Group>
        </Paper>
      )}
    </>
  );
}
