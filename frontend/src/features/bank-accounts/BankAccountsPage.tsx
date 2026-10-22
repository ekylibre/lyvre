// Banque › Comptes bancaires : liste, création, modification, suppression ; accès aux
// transactions, à l'import OFX et au rattachement Qonto.
import { useState } from "react";
import { Alert, Anchor, Button, Group, Select, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { AppLink } from "../../app/navigation";
import { useRouteModal } from "../../app/useRouteModal";
import { BANK_ACCOUNTS_KEY, type BankAccount, type Option } from "./types";

interface Meta { gl_accounts: Option[]; qonto: { available: boolean; message: string | null } }

function BankAccountForm({ bankAccount, glAccounts, onDone }: { bankAccount: BankAccount | null; glAccounts: Option[]; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: { label: bankAccount?.label ?? "", iban: bankAccount?.iban ?? "",
      account_id: bankAccount ? String(bankAccount.account.id) : glAccounts.find((a) => a.label.startsWith("512"))?.value ?? "" },
  });
  const save = useAction((values: typeof form.values) => bankAccount
    ? api.patch<{ notices: Notice[] }>(`/api/v1/bank-accounts/${bankAccount.id}`, values)
    : api.post<{ notices: Notice[] }>("/api/v1/bank-accounts", values), { invalidate: [BANK_ACCOUNTS_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel={bankAccount ? "Enregistrer" : "Créer le compte"} onCancel={onDone} loading={save.isPending}>
        <TextInput label="Libellé" required data-autofocus placeholder="CIC Compte courant" {...form.getInputProps("label")} />
        <TextInput label="IBAN" description="Facultatif ; les espaces sont retirés." classNames={{ input: "lv-num" }}
          placeholder="FR76 3000 6000 0112 3456 7890 189" {...form.getInputProps("iban")} />
        {glAccounts.length ? (
          <Select label="Compte comptable" required searchable data={glAccounts} {...form.getInputProps("account_id")} />
        ) : (
          <Alert color="paille">Aucun compte 51… dans le plan : <Anchor component={AppLink} href="/accounts/new">créer un compte 512xxx</Anchor>.</Alert>
        )}
      </FormBody>
    </form>
  );
}

export default function BankAccountsPage() {
  const modal = useRouteModal("/bank-accounts/", "ba_id");
  const can = useCan();
  const { data, isFetching } = useList<BankAccount, Meta>(BANK_ACCOUNTS_KEY, "/api/v1/bank-accounts");
  const editing = modal.mode === "edit" ? data?.items.find((b) => b.id === modal.id) ?? null : null;
  const remove = useAction((b: BankAccount) => api.delete<{ notices: Notice[] }>(`/api/v1/bank-accounts/${b.id}`),
    { invalidate: [BANK_ACCOUNTS_KEY] });

  const columns: GridColumn<BankAccount>[] = [
    { accessor: "label", title: "Libellé", hideable: false,
      render: (b) => <Group gap="xs"><Anchor component={AppLink} href={`/bank-accounts/${b.id}/transactions`} fw={600}>{b.label}</Anchor>
        {b.qonto && <StatusBadge tone="info">Qonto</StatusBadge>}</Group> },
    { accessor: "iban", title: "IBAN", render: (b) => <Text size="sm" className="lv-num" c="dimmed">{b.iban ?? "—"}</Text> },
    { accessor: "account", title: "Compte", render: (b) => <Text size="sm"><span className="lv-num">{b.account.code}</span> {b.account.label}</Text> },
    { accessor: "transactions", title: "Transactions", textAlign: "right", render: (b) => <span className="lv-num">{b.transactions}</span> },
    { accessor: "unreconciled", title: "À rapprocher", textAlign: "right",
      render: (b) => b.unreconciled
        ? <Anchor component={AppLink} href={`/reconciliation/?bank_account_id=${b.id}`}><StatusBadge tone="todo">{String(b.unreconciled)}</StatusBadge></Anchor>
        : <StatusBadge tone="ok">0</StatusBadge> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (b) => (
        <Group gap={4} justify="flex-end" wrap="nowrap">
          {!b.qonto && <Button variant="subtle" size="compact-sm" component={AppLink} href={`/imports/ofx?bank_account_id=${b.id}`}>Importer un OFX</Button>}
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
      <PageHeader title="Comptes bancaires" description="Chaque compte bancaire est lié à un compte 512 du plan comptable."
        actions={<>
          {can.instanceAdmin && <Button variant="default" component={AppLink} href="/bank-accounts/qonto">Comptes Qonto</Button>}
          <Can><Button onClick={modal.openNew}>Créer un compte</Button></Can>
        </>} />
      <DataGrid id="bank-accounts" records={data?.items} columns={columns} fetching={isFetching}
        emptyText="Aucun compte bancaire : créez le premier." />
      <FormModal opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? `Modifier « ${editing.label} »` : "Créer un compte bancaire"}>
        <BankAccountForm key={editing?.id ?? "new"} bankAccount={editing} glAccounts={data?.meta?.gl_accounts ?? []} onDone={modal.close} />
      </FormModal>
    </>
  );
}
