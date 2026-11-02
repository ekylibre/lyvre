// Banque › Comptes bancaires et caisses : liste (soldes comptable et bancaire), création, modification,
// suppression ; transactions, import OFX et rattachement Qonto (banque) ; mouvements (caisse).
import { useState } from "react";
import { Alert, Anchor, Button, Group, SegmentedControl, Select, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useCan, useIntegration } from "../../api/session";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { AppLink } from "../../app/navigation";
import { useRouteModal } from "../../app/useRouteModal";
import { formatDate } from "../../lib/format";
import { OpeningBalanceForm } from "./OpeningBalanceForm";
import { BANK_ACCOUNTS_KEY, type BankAccount, type Option } from "./types";

interface Meta { gl_accounts: Option[]; cash_accounts: Option[]; qonto: { available: boolean; message: string | null } }

function BankAccountForm({ bankAccount, meta, onDone }: { bankAccount: BankAccount | null; meta: Meta | undefined; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const banks = meta?.gl_accounts ?? [];
  const tills = meta?.cash_accounts ?? [];
  const form = useForm({
    initialValues: { label: bankAccount?.label ?? "", iban: bankAccount?.iban ?? "", kind: bankAccount?.kind ?? "bank",
      account_id: bankAccount ? String(bankAccount.account.id) : banks.find((a) => a.label.startsWith("512"))?.value ?? "" },
  });
  const cash = form.values.kind === "cash";
  const glAccounts = cash ? tills : banks;
  const save = useAction((values: typeof form.values) => bankAccount
    ? api.patch<{ notices: Notice[] }>(`/api/v1/bank-accounts/${bankAccount.id}`, values)
    : api.post<{ notices: Notice[] }>("/api/v1/bank-accounts", values), { invalidate: [BANK_ACCOUNTS_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel={bankAccount ? "Enregistrer" : "Créer le compte"} onCancel={onDone} loading={save.isPending}>
        {!bankAccount && (
          <Stack gap={4}>
            <Text size="sm" fw={500}>Nature</Text>
            <SegmentedControl data={[{ value: "bank", label: "Compte bancaire" }, { value: "cash", label: "Caisse (espèces)" }]}
              {...form.getInputProps("kind")} onChange={(kind) => {
                form.setFieldValue("kind", kind);
                const list = kind === "cash" ? tills : banks;
                form.setFieldValue("account_id", list.find((a) => a.label.startsWith(kind === "cash" ? "53" : "512"))?.value ?? "");
              }} />
          </Stack>
        )}
        <TextInput label="Libellé" required data-autofocus placeholder={cash ? "Caisse buvette" : "CIC Compte courant"} {...form.getInputProps("label")} />
        {!cash && <TextInput label="IBAN" description="Facultatif ; les espaces sont retirés." classNames={{ input: "lv-num" }}
          placeholder="FR76 3000 6000 0112 3456 7890 189" {...form.getInputProps("iban")} />}
        {glAccounts.length ? (
          <Select label="Compte comptable" required searchable data={glAccounts} {...form.getInputProps("account_id")} />
        ) : (
          <Alert color="paille">Aucun compte {cash ? "53…" : "51…"} dans le plan : <Anchor component={AppLink} href="/accounts/new">créer un compte {cash ? "530xxx" : "512xxx"}</Anchor>.</Alert>
        )}
      </FormBody>
    </form>
  );
}

export default function BankAccountsPage() {
  const modal = useRouteModal("/bank-accounts/", "ba_id");
  const can = useCan();
  const qonto = useIntegration("qonto", "transactions");
  const { data, isFetching } = useList<BankAccount, Meta>(BANK_ACCOUNTS_KEY, "/api/v1/bank-accounts");
  const [opening, setOpening] = useState<BankAccount | null>(null);
  const editing = modal.mode === "edit" ? data?.items.find((b) => b.id === modal.id) ?? null : null;
  const remove = useAction((b: BankAccount) => api.delete<{ notices: Notice[] }>(`/api/v1/bank-accounts/${b.id}`),
    { invalidate: [BANK_ACCOUNTS_KEY] });

  const columns: GridColumn<BankAccount>[] = [
    { accessor: "label", title: "Libellé", hideable: false,
      render: (b) => <Group gap="xs"><Anchor component={AppLink} href={b.kind === "cash" ? `/bank-accounts/${b.id}/cash` : `/bank-accounts/${b.id}/transactions`} fw={600}>{b.label}</Anchor>
        {b.qonto && <StatusBadge tone="info">Qonto</StatusBadge>}{b.kind === "cash" && <StatusBadge tone="neutral">Caisse</StatusBadge>}</Group> },
    { accessor: "iban", title: "IBAN", render: (b) => <Text size="sm" className="lv-num" c="dimmed">{b.iban ?? "—"}</Text> },
    { accessor: "account", title: "Compte", render: (b) => <Text size="sm"><span className="lv-num">{b.account.code}</span> {b.account.label}</Text> },
    { accessor: "balance_cents", title: "Solde comptable", textAlign: "right",
      render: (b) => <MoneyText cents={b.balance_cents ?? 0} anomaly={(b.balance_cents ?? 0) < 0} size="sm" /> },
    { accessor: "bank_balance", title: "Solde bancaire", textAlign: "right",
      render: (b) => {
        const bal = b.bank_balance;
        if (!bal) return <Text size="sm" c="dimmed">—</Text>;
        const amount = <MoneyText cents={bal.balance_cents} anomaly={bal.balance_cents < 0} size="sm" />;
        return bal.opening_missing ? (
          <Stack gap={2} align="flex-end">
            <Tooltip label={`Somme des transactions de l'exercice ${bal.fiscal_year ?? ""} au ${formatDate(bal.at)}, sans solde d'ouverture`} withArrow openDelay={150}>
              <Text component="span" c="dimmed">{amount}</Text>
            </Tooltip>
            {can.write
              ? <Anchor component="button" size="xs" onClick={() => setOpening(b)}><StatusBadge tone="todo">Solde d'ouverture à saisir</StatusBadge></Anchor>
              : <StatusBadge tone="todo">Solde d'ouverture manquant</StatusBadge>}
          </Stack>
        ) : (
          <Tooltip label={`Au ${formatDate(bal.at)} : solde d'ouverture et transactions importées${can.write ? " (cliquer pour modifier le solde d'ouverture)" : ""}`} withArrow openDelay={150}>
            {can.write ? <Anchor component="button" onClick={() => setOpening(b)}>{amount}</Anchor> : <span>{amount}</span>}
          </Tooltip>
        );
      } },
    { accessor: "transactions", title: "Transactions", textAlign: "right",
      render: (b) => b.kind === "cash" ? <Text size="sm" c="dimmed">—</Text> : <span className="lv-num">{b.transactions}</span> },
    { accessor: "unreconciled", title: "À rapprocher", textAlign: "right",
      render: (b) => b.kind === "cash" ? <Text size="sm" c="dimmed">—</Text> : b.unreconciled
        ? <Anchor component={AppLink} href={`/reconciliation/?bank_account_id=${b.id}`}><StatusBadge tone="todo">{String(b.unreconciled)}</StatusBadge></Anchor>
        : <StatusBadge tone="ok">0</StatusBadge> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (b) => (
        <Group gap={4} justify="flex-end" wrap="nowrap">
          {b.kind === "cash"
            ? <Button variant="subtle" size="compact-sm" component={AppLink} href={`/bank-accounts/${b.id}/cash`}>Mouvements</Button>
            : !b.qonto && <Button variant="subtle" size="compact-sm" component={AppLink} href={`/imports/ofx?bank_account_id=${b.id}`}>Importer un OFX</Button>}
          <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(b.id)}>Modifier</Button>
          <Button variant="subtle" size="compact-sm" color="brique"
            onClick={() => confirmAction({ title: `Supprimer « ${b.label} » ?`, confirmLabel: "Supprimer",
              message: b.transactions ? `${b.transactions} transaction(s) : la suppression sera refusée.` : undefined,
              onConfirm: () => remove.mutate(b) })}>Supprimer</Button>
        </Group>
      ) },
  ];

  return (
    <>
      <PageHeader title="Comptes bancaires et caisses" description="Chaque compte bancaire est lié à un compte 512, chaque caisse à un compte 53 du plan comptable."
        actions={<>
          {can.instanceAdmin && qonto && <Button variant="default" component={AppLink} href="/bank-accounts/qonto">Comptes Qonto</Button>}
          <Can><Button onClick={modal.openNew}>Créer un compte</Button></Can>
        </>} />
      <DataGrid id="bank-accounts" records={data?.items} columns={columns} fetching={isFetching}
        emptyText="Aucun compte bancaire : créez le premier." />
      <FormModal opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? `Modifier « ${editing.label} »` : "Créer un compte bancaire ou une caisse"}>
        <BankAccountForm key={editing?.id ?? "new"} bankAccount={editing} meta={data?.meta} onDone={modal.close} />
      </FormModal>
      <FormModal opened={!!opening} onClose={() => setOpening(null)} title={`Solde bancaire d'ouverture — ${opening?.label ?? ""}`}>
        {opening && <OpeningBalanceForm key={opening.id} bankAccount={opening} onDone={() => setOpening(null)} />}
      </FormModal>
    </>
  );
}
