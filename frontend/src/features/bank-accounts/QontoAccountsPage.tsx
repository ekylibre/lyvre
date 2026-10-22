// Banque › Comptes Qonto (admin) : rattacher chaque compte Qonto à un compte bancaire (existant,
// proposé s'il a le même IBAN, ou nouveau) ; seuls les comptes rattachés sont synchronisés.
import { useState } from "react";
import { Alert, Anchor, Button, Center, Group, Loader, Paper, Radio, Select, Stack, Text, TextInput, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { BANK_ACCOUNTS_KEY, type BankAccount, type Option } from "./types";

interface QontoAccount {
  qonto_id: string; name: string; iban: string | null; status: string; main: boolean; closed: boolean;
  balance_cents: number | null; linked: BankAccount | null; proposed_id: number | null;
}
interface Response {
  items: QontoAccount[]; error: string | null;
  meta: { gl_accounts: Option[]; default_gl_id: number | null; unlinked: Option[]; default_sync_from: string };
}

const KEY = [...BANK_ACCOUNTS_KEY, "qonto"];

function LinkForm({ account, meta }: { account: QontoAccount; meta: Response["meta"] }) {
  const [mode, setMode] = useState(account.proposed_id ? "existing" : "new");
  const [bankAccountId, setBankAccountId] = useState<string | null>(account.proposed_id ? String(account.proposed_id) : meta.unlinked[0]?.value ?? null);
  const [label, setLabel] = useState(`Qonto — ${account.name}`);
  const [glAccountId, setGlAccountId] = useState<string | null>(meta.default_gl_id ? String(meta.default_gl_id) : null);
  const [syncFrom, setSyncFrom] = useState<string | null>(meta.default_sync_from);
  const link = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/qonto/accounts/link", {
    qonto_account_id: account.qonto_id, mode, sync_from: syncFrom,
    ...(mode === "existing" ? { bank_account_id: bankAccountId } : { label, gl_account_id: glAccountId }),
  }), { invalidate: [BANK_ACCOUNTS_KEY] });
  return (
    <Stack gap="sm">
      <Radio.Group label="Rattacher à" value={mode} onChange={setMode}>
        <Group mt={4}>
          <Radio value="existing" label="un compte bancaire existant" disabled={!meta.unlinked.length} />
          <Radio value="new" label="un nouveau compte bancaire" />
        </Group>
      </Radio.Group>
      <Group grow align="flex-start">
        {mode === "existing" ? (
          <Select label="Compte existant" value={bankAccountId} onChange={setBankAccountId} allowDeselect={false}
            data={meta.unlinked.map((o) => ({ ...o, label: o.value === String(account.proposed_id) ? `${o.label} (même IBAN)` : o.label }))} />
        ) : (
          <>
            <TextInput label="Libellé du nouveau compte" value={label} onChange={(e) => setLabel(e.currentTarget.value)} />
            <Select label="Compte comptable" data={meta.gl_accounts} value={glAccountId} onChange={setGlAccountId} searchable />
          </>
        )}
        <DateInput label="Synchroniser à partir du" valueFormat="DD/MM/YYYY" value={syncFrom} onChange={setSyncFrom} />
      </Group>
      <Group justify="flex-end"><Button loading={link.isPending} disabled={!syncFrom} onClick={() => link.mutate(undefined)}>Rattacher</Button></Group>
    </Stack>
  );
}

export default function QontoAccountsPage() {
  const { data, isPending } = useQuery({ queryKey: KEY, queryFn: () => api.get<Response>("/api/v1/qonto/accounts") });
  return (
    <>
      <PageHeader title="Comptes Qonto" description="Rattachez chaque compte Qonto à un compte bancaire : seuls les comptes rattachés sont synchronisés. Un compte de même IBAN est proposé d'office."
        actions={<Button variant="default" component={AppLink} href="/bank-accounts/">Retour aux comptes</Button>} />
      {isPending ? <Center h={200}><Loader /></Center> : (
        <Stack>
          {data?.error && <Alert color="brique" role="alert">{data.error}</Alert>}
          {data?.items.map((a) => (
            <Paper key={a.qonto_id} p="md">
              <Group justify="space-between" mb="sm">
                <Stack gap={0}>
                  <Group gap="xs"><Title order={2} size="h3">{a.name}</Title>{a.main && <StatusBadge tone="neutral">Principal</StatusBadge>}
                    {a.closed && <StatusBadge tone="gap">{a.status}</StatusBadge>}</Group>
                  <Text size="sm" c="dimmed" className="lv-num">{a.iban ?? "IBAN inconnu"}</Text>
                </Stack>
                {a.balance_cents !== null && <Text size="sm">Solde Qonto : <MoneyText cents={a.balance_cents} fw={600} /></Text>}
              </Group>
              {a.linked ? (
                <Text size="sm">Rattaché à <Anchor component={AppLink} href={`/bank-accounts/${a.linked.id}/transactions`}>{a.linked.label}</Anchor>,
                  synchronisé à partir du {formatDate(a.linked.qonto?.sync_from)}.</Text>
              ) : <LinkForm account={a} meta={data.meta} />}
            </Paper>
          ))}
          {data && !data.items.length && !data.error && <Text c="dimmed">Aucun compte Qonto.</Text>}
        </Stack>
      )}
    </>
  );
}
