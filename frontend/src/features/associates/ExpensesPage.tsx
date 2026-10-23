// Associés › Notes de frais : dépenses avancées par un associé sans facture fournisseur. Chaque
// note passe une écriture au journal AS (charge et TVA déductible / compte courant de l'associé).
import { useState } from "react";
import { Anchor, Button, Center, FileInput, Loader, Select, SimpleGrid, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { showNotices, useAction, useList, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { upload } from "../../api/upload";
import { AppLink } from "../../app/navigation";
import { useRouteModal } from "../../app/useRouteModal";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import type { Option } from "../purchases/types";
import { ASSOCIATES_KEY } from "./types";

interface Expense {
  id: number; associate_id: number; associate: string; expense_date: string; label: string; account_code: string;
  account_label: string; untaxed_cents: number; vat_cents: number; vat_rate: string; total_cents: number;
  attachment: { name: string; url: string } | null; entry: { id: number; reference: string } | null;
}
interface Meta { associates: Option[]; charge_accounts: Option[] }

const KEY = [...ASSOCIATES_KEY, "expenses"];

function ExpenseForm({ meta, onDone }: { meta: Meta; onDone: () => void }) {
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sending, setSending] = useState(false);
  const form = useForm({ initialValues: {
    associate_id: meta.associates.length === 1 ? meta.associates[0].value : null as string | null,
    expense_date: new Date().toISOString().slice(0, 10), label: "", account_code: null as string | null,
    untaxed: "", vat_rate: "", vat: "",
  } });
  const json = useAction((values: typeof form.values) => api.post<{ notices: Notice[] }>("/api/v1/associate-expenses", values),
    { invalidate: [ASSOCIATES_KEY], silent: true });
  const submit = async (values: typeof form.values) => {
    setError(null);
    if (!file) {
      json.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) });
      return;
    }
    const data = new FormData();
    data.append("payload", JSON.stringify(values));
    data.append("attachment", file);
    setSending(true);
    try {
      const body = await upload<{ notices: Notice[] }>("/api/v1/associate-expenses", data);
      showNotices(body.notices);
      void client.invalidateQueries({ queryKey: ASSOCIATES_KEY });
      onDone();
    } catch (e) {
      setError(applyApiError(form, e));
    } finally {
      setSending(false);
    }
  };
  return (
    <form onSubmit={form.onSubmit((values) => void submit(values))}>
      <FormBody error={error} submitLabel="Enregistrer la note de frais" onCancel={onDone} loading={json.isPending || sending}>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Associé" required searchable data-autofocus data={meta.associates} {...form.getInputProps("associate_id")} />
          <TextInput label="Date" type="date" required {...form.getInputProps("expense_date")} />
        </SimpleGrid>
        <TextInput label="Libellé" required placeholder="Ampoules, frais de déplacement…" {...form.getInputProps("label")} />
        <Select label="Compte de charge" required searchable data={meta.charge_accounts} nothingFoundMessage="Aucun compte 6…"
          {...form.getInputProps("account_code")} />
        <SimpleGrid cols={3}>
          <TextInput label="HT (€)" required inputMode="decimal" classNames={{ input: "lv-num" }} {...form.getInputProps("untaxed")} />
          <TextInput label="Taux de TVA (%)" inputMode="decimal" placeholder="0" {...form.getInputProps("vat_rate")} />
          <TextInput label="TVA (€)" inputMode="decimal" placeholder="calculée" classNames={{ input: "lv-num" }} {...form.getInputProps("vat")} />
        </SimpleGrid>
        <FileInput label="Justificatif" placeholder="PDF, JPEG ou PNG" clearable value={file} onChange={setFile}
          accept="application/pdf,image/jpeg,image/png" error={form.errors.attachment} />
      </FormBody>
    </form>
  );
}

export default function ExpensesPage() {
  const can = useCan();
  const modal = useRouteModal("/associate-expenses/");
  const { data, isFetching } = useList<Expense, Meta>(KEY, "/api/v1/associate-expenses");
  const remove = useAction((e: Expense) => api.delete<{ notices: Notice[] }>(`/api/v1/associate-expenses/${e.id}`),
    { invalidate: [ASSOCIATES_KEY] });
  const columns: GridColumn<Expense>[] = [
    { accessor: "expense_date", title: "Date", sortable: true, render: (e) => formatDate(e.expense_date) },
    { accessor: "associate", title: "Associé", sortable: true,
      render: (e) => <AppLink href={`/associates/${e.associate_id}`}>{e.associate}</AppLink> },
    { accessor: "label", title: "Libellé", hideable: false },
    { accessor: "account_code", title: "Compte", render: (e) => <span className="lv-num" title={e.account_label}>{e.account_code}</span> },
    { accessor: "untaxed_cents", title: "HT", textAlign: "right", render: (e) => <MoneyText cents={e.untaxed_cents} size="sm" /> },
    { accessor: "vat_cents", title: "TVA", textAlign: "right", render: (e) => <MoneyText cents={e.vat_cents} size="sm" /> },
    { accessor: "total_cents", title: "TTC", textAlign: "right", sortable: true, render: (e) => <MoneyText cents={e.total_cents} size="sm" /> },
    { accessor: "attachment", title: "Pièce", render: (e) => e.attachment
      ? <Anchor href={e.attachment.url} target="_blank" rel="noreferrer" size="sm">{e.attachment.name}</Anchor> : "" },
    { accessor: "entry", title: "Écriture", render: (e) => e.entry
      ? <AppLink href={`/entries/${e.entry.id}`}>{e.entry.reference}</AppLink> : "" },
    { accessor: "actions", title: "", hideable: false, textAlign: "right", render: (e) => can.write && (
      <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
        title: `Supprimer la note de frais « ${e.label} » ?`, message: "Son écriture est supprimée aussi.", confirmLabel: "Supprimer",
        onConfirm: () => remove.mutate(e) })}>Supprimer</Button>
    ) },
  ];
  return (
    <>
      <PageHeader title="Notes de frais" description="Dépenses avancées par un associé sans facture : portées au crédit de son compte courant."
        actions={can.write && <Button onClick={modal.openNew}>Nouvelle note de frais</Button>} />
      <DataGrid id="associate-expenses" records={data?.items} columns={columns} fetching={isFetching}
        defaultSort={{ column: "expense_date", direction: "desc" }} emptyText="Aucune note de frais." />
      <FormModal opened={modal.mode === "new"} onClose={modal.close} title="Nouvelle note de frais" size="lg">
        {data?.meta ? <ExpenseForm meta={data.meta} onDone={modal.close} /> : <Center h={120}><Loader /></Center>}
      </FormModal>
    </>
  );
}
