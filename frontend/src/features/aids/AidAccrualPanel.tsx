// Clôture › Inventaire (lot AG3.c, claudedocs/design_aides_pac.md § 4) : aides acquises et non versées (produit à
// recevoir, D 441) ou versées avant leur fait générateur (produit constaté d'avance, C 487), proposées par dossier ;
// montant modifiable avec un motif, proposition écartée avec un motif. Écritures extournées à l'ouverture de N+1.
import { useState } from "react";
import { Alert, Anchor, Button, Checkbox, Group, List, Paper, Table, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyInput, MoneyText } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { AppLink } from "../../app/navigation";
import { formatDate } from "../../lib/format";

export interface AidAccrual {
  key: string; aid_id: number; kind: "accrued" | "deferred"; kind_label: string; label: string; account_code: string;
  counterpart: string; trigger_on: string; trigger_provisional: boolean; acquired_cents: number; paid_cents: number;
  amount_cents: number; posted: boolean; posted_cents: number | null; entry: { id: number; reference: string } | null;
  dismissed: boolean; reason: string | null; mixed: boolean;
}
export interface AidAccruals { items: AidAccrual[]; issues: { aid_id: number; label: string; message: string }[]; enabled: boolean }

type Choice = { amount: number | null; reason: string };

export function AidAccrualPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const key = ["closing", fyId, "aids"];
  const url = `/api/v1/fiscal-years/${fyId}/closing/aids`;
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<AidAccruals>(url) });
  const [chosen, setChosen] = useState<Record<string, Choice>>({});
  const [dismissing, setDismissing] = useState<{ aid: number; reason: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["closing", fyId]] };
  const post = useAction(() => api.post<{ notices: Notice[] }>(url, { items: Object.entries(chosen).map(([k, c]) => (
    { key: k, amount_cents: c.amount ?? undefined, reason: c.reason || undefined })) }), opts);
  const dismiss = useAction((v: { aid: number; reason: string }) => api.post<{ notices: Notice[] }>(`${url}/dismissed`,
    { aid_id: v.aid, reason: v.reason }), opts);
  const restore = useAction((aid: number) => api.delete<{ notices: Notice[] }>(`${url}/dismissed/${aid}`), opts);
  if (!data?.enabled || (!data.items.length && !data.issues.length)) return null;
  const toggle = (p: AidAccrual, on: boolean) => {
    const next = { ...chosen };
    if (on) next[p.key] = { amount: p.amount_cents, reason: "" }; else delete next[p.key];
    setChosen(next);
  };
  const run = (promise: Promise<unknown>, after?: () => void) => {
    setError(null);
    promise.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible."));
  };
  return (
    <Paper withBorder p="sm">
      <Text fw={600} size="sm" mb={4}>Aides et subventions à la clôture</Text>
      <Text size="xs" c="dimmed" mb="xs">Aide acquise (date limite de la demande PAC, sinon décision) et non versée : produit à
        recevoir en 441 ; versée avant son fait générateur : produit constaté d'avance en 487.</Text>
      {data.issues.length > 0 && (
        <Alert color="paille" mb="xs" title="Dossiers à compléter">
          <List size="sm">{data.issues.map((i) => <List.Item key={`${i.aid_id}-${i.message}`}>
            <Anchor component={AppLink} href="/aids/" size="sm">{i.label}</Anchor> : {i.message}</List.Item>)}</List>
        </Alert>)}
      {data.items.length > 0 && (
        <Table>
          <Table.Thead><Table.Tr>{editable && <Table.Th w={36} />}<Table.Th>Dossier</Table.Th><Table.Th>Comptes</Table.Th>
            <Table.Th ta="right">Acquis</Table.Th><Table.Th ta="right">Versé</Table.Th><Table.Th ta="right">Écriture</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.items.map((p) => {
              const c = chosen[p.key];
              const open = !p.posted && !p.dismissed;
              return (
                <Table.Tr key={p.key}>
                  {editable && <Table.Td>{open && <Checkbox aria-label={`Retenir ${p.label}`} checked={!!c}
                    onChange={(e) => toggle(p, e.currentTarget.checked)} />}</Table.Td>}
                  <Table.Td><Text size="sm">{p.label}</Text>
                    <Text size="xs" c="dimmed">{p.kind_label} · fait générateur {formatDate(p.trigger_on)}{p.trigger_provisional ? " (à confirmer)" : ""}</Text>
                    {p.dismissed && p.reason && <Text size="xs" c="dimmed">Écartée : {p.reason}</Text>}</Table.Td>
                  <Table.Td className="lv-num">{p.kind === "accrued" ? `441 / ${p.account_code}` : `${p.account_code} / 487`}</Table.Td>
                  <Table.Td ta="right"><MoneyText cents={p.acquired_cents} /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={p.paid_cents} /></Table.Td>
                  <Table.Td ta="right">
                    {p.posted ? <><StatusBadge tone="ok">passée</StatusBadge> <MoneyText cents={p.posted_cents ?? 0} /></>
                      : p.dismissed ? <StatusBadge tone="neutral">écartée</StatusBadge>
                        : c && editable ? (
                          <Group gap={4} justify="end" wrap="nowrap">
                            <MoneyInput aria-label={`Montant ${p.label}`} w={120} value={c.amount}
                              onChange={(v) => setChosen({ ...chosen, [p.key]: { ...c, amount: v } })} />
                            {c.amount !== p.amount_cents && <TextInput aria-label={`Motif ${p.label}`} placeholder="Motif de l'écart" w={180}
                              value={c.reason} onChange={(e) => setChosen({ ...chosen, [p.key]: { ...c, reason: e.currentTarget.value } })} />}
                          </Group>)
                          : <MoneyText cents={p.amount_cents} />}
                  </Table.Td>
                  <Table.Td ta="right">{editable && open && !c && (
                    <Button size="compact-sm" variant="subtle" onClick={() => setDismissing({ aid: p.aid_id, reason: "" })}>Écarter…</Button>)}
                    {editable && p.dismissed && <Button size="compact-sm" variant="subtle" onClick={() => run(restore.mutateAsync(p.aid_id))}>Rétablir</Button>}
                  </Table.Td>
                </Table.Tr>);
            })}
          </Table.Tbody>
        </Table>)}
      {dismissing && (
        <Group mt="xs" align="end">
          <TextInput label="Motif pour écarter la proposition" w={360} value={dismissing.reason} data-autofocus
            onChange={(e) => setDismissing({ ...dismissing, reason: e.currentTarget.value })} />
          <Button disabled={dismissing.reason.trim().length < 5} loading={dismiss.isPending}
            onClick={() => run(dismiss.mutateAsync(dismissing), () => setDismissing(null))}>Écarter</Button>
          <Button variant="default" onClick={() => setDismissing(null)}>Annuler</Button>
        </Group>)}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
      {editable && Object.keys(chosen).length > 0 && (
        <Group mt="sm"><Button loading={post.isPending}
          onClick={() => run(post.mutateAsync(undefined), () => setChosen({}))}>{`Passer les écritures (${Object.keys(chosen).length})`}</Button></Group>)}
    </Paper>
  );
}
