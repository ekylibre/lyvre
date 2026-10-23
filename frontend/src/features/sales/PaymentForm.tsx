// Encaisser une facture : transaction bancaire créditrice (montant égal au restant dû proposé en
// premier ; une écriture de règle est remplacée) ou saisie d'un chèque, d'espèces… sur une banque
// ou une caisse. L'écriture 512 (53x) / 411 est passée ; la TVA à l'encaissement est virée.
import { useState } from "react";
import { Alert, Badge, Center, Group, Loader, Radio, SegmentedControl, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { FormBody } from "../../components/ApiForm";
import { MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";
import { SALES_KEY, type PaymentOptions, type SaleDetail } from "./types";

export function PaymentForm({ sale, onDone }: { sale: SaleDetail; onDone: (item?: SaleDetail) => void }) {
  const { data } = useQuery({ queryKey: [...SALES_KEY, sale.id, "payment-options"],
    queryFn: () => api.get<PaymentOptions>(`/api/v1/sales/${sale.id}/payment-options`) });
  const [mode, setMode] = useState<"bank" | "manual">("bank");
  const [txnId, setTxnId] = useState<string>("");
  const [amount, setAmount] = useState(() => (sale.due_cents / 100).toFixed(2).replace(".", ","));
  const [paidOn, setPaidOn] = useState(new Date().toISOString().slice(0, 10));
  const [account, setAccount] = useState<string | null>(null);
  const [method, setMethod] = useState<string | null>("check");
  const [error, setError] = useState<string | null>(null);
  const match = useAction(() => {
    const txn = data!.candidates.find((c) => String(c.id) === txnId)!;
    return api.post<{ items: SaleDetail[]; notices: Notice[] }>("/api/v1/sales/match",
      { bank_transaction_id: txn.id, allocations: [{ sale_id: sale.id, amount_cents: txn.amount_cents }] });
  }, { invalidate: [SALES_KEY], silent: true });
  const manual = useAction(() => api.post<{ item: SaleDetail; notices: Notice[] }>(`/api/v1/sales/${sale.id}/payments`,
    { amount, paid_on: paidOn, bank_account_id: account, method }), { invalidate: [SALES_KEY], silent: true });

  if (!data) return <Center h={120}><Loader /></Center>;
  const chosen = data.candidates.find((c) => String(c.id) === txnId);
  const tooMuch = chosen && chosen.amount_cents > data.due_cents;
  const submit = () => {
    setError(null);
    const fail = (e: unknown) => setError(e instanceof Error ? e.message : "Erreur inattendue.");
    if (mode === "bank" && (!chosen || tooMuch)) {
      setError(chosen ? "Montant supérieur au restant dû." : "Choisissez la transaction.");
      return;
    }
    if (mode === "bank") match.mutate(undefined, { onSuccess: (r) => onDone(r.items[0]), onError: fail });
    else manual.mutate(undefined, { onSuccess: (r) => onDone(r.item), onError: fail });
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <FormBody error={error} submitLabel="Encaisser" onCancel={() => onDone()} loading={match.isPending || manual.isPending}>
        <Text size="sm">Restant dû : <MoneyText cents={data.due_cents} fw={600} /></Text>
        <SegmentedControl value={mode} onChange={(v) => setMode(v as "bank" | "manual")}
          data={[{ value: "bank", label: "Transaction bancaire" }, { value: "manual", label: "Chèque, espèces…" }]} />
        {mode === "bank" ? (
          data.candidates.length === 0
            ? <Alert color="ardoise">Aucun crédit bancaire disponible autour de la date de la facture. Importez le relevé, ou saisissez l'encaissement.</Alert>
            : <Radio.Group value={txnId} onChange={setTxnId} label="Transaction">
              <Table mt={4}>
                <Table.Tbody>
                  {data.candidates.map((c) => (
                    <Table.Tr key={c.id}>
                      <Table.Td w={30}><Radio value={String(c.id)} aria-label={`${formatDate(c.date)} ${c.label}`} /></Table.Td>
                      <Table.Td className="lv-num">{formatDate(c.date)}</Table.Td>
                      <Table.Td><Text size="sm">{c.label}</Text><Text size="xs" c="dimmed">{c.account}</Text></Table.Td>
                      <Table.Td ta="right"><MoneyText cents={c.amount_cents} size="sm" /></Table.Td>
                      <Table.Td><Group gap={4}>
                        {c.exact && <Badge size="xs" color="lichen">montant exact</Badge>}
                        {c.same_client && <Badge size="xs" variant="light">même client</Badge>}
                        {c.rule && <Badge size="xs" color="paille" title="L'écriture de la règle sera remplacée par l'encaissement">règle</Badge>}
                      </Group></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              {tooMuch && <Text size="sm" c="var(--lv-brique)" mt={4}>Montant supérieur au restant dû : une transaction encaisse ici une seule facture.</Text>}
            </Radio.Group>
        ) : (
          <Stack>
            <Group grow>
              <TextInput label="Montant (€)" required inputMode="decimal" value={amount} onChange={(e) => setAmount(e.currentTarget.value)} />
              <TextInput label="Date" type="date" required value={paidOn} onChange={(e) => setPaidOn(e.currentTarget.value)} />
            </Group>
            <Group grow>
              <Select label="Encaissé sur" required data={data.accounts} value={account} onChange={setAccount}
                description="Banque (chèque remis, à rapprocher du relevé) ou caisse" />
              <Select label="Mode" data={data.methods} value={method} onChange={setMethod} allowDeselect={false} />
            </Group>
          </Stack>
        )}
      </FormBody>
    </form>
  );
}
