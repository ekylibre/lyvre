// Ventes › Nouvelle facture (/sales/new) et modification d'un brouillon (/sales/<id>/edit) : client
// (ou nouveau client), dates, nature de l'opération, lignes du catalogue, conditions. Un brouillon
// n'a ni numéro ni écriture ; l'émission se fait depuis sa fiche.
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Alert, Button, Center, Fieldset, Group, Loader, Select, SimpleGrid, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { showNotices, type Notice } from "../../api/resources";
import { PageHeader } from "../../components/PageHeader";
import { writeOnly } from "../../components/ReadOnlyPage";
import { AppLink, useGoTo } from "../../app/navigation";
import { SaleLinesEditor } from "./SaleLinesEditor";
import { EMPTY_SALE_LINE, SALES_KEY, VAT_MODE_LABELS, type SaleDetail, type SaleFormOptions, type SaleLineRow } from "./types";

const NEW_CLIENT = "__new__";
type Header = { entity_id: string; new_client_name: string; issue_date: string; due_date: string; service_start: string;
  service_end: string; operation_type: string; purchase_order: string; header: string; terms: string; footer: string };
const today = () => new Date().toISOString().slice(0, 10);
const EMPTY: Header = { entity_id: "", new_client_name: "", issue_date: today(), due_date: "", service_start: "", service_end: "",
  operation_type: "services", purchase_order: "", header: "", terms: "", footer: "" };

function SaleFormPage() {
  const editId = Number(useParams().sale_id) || null;
  const client = useQueryClient();
  const goTo = useGoTo();
  const options = useQuery({ queryKey: [...SALES_KEY, "form-options"],
    queryFn: () => api.get<SaleFormOptions>("/api/v1/sales/form-options") });
  const existing = useQuery({ queryKey: [...SALES_KEY, editId], enabled: !!editId,
    queryFn: () => api.get<{ item: SaleDetail }>(`/api/v1/sales/${editId}`) });
  const [header, setHeader] = useState<Header>(EMPTY);
  const [rows, setRows] = useState<SaleLineRow[]>([EMPTY_SALE_LINE]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const item = existing.data?.item;
    if (item) {
      setHeader({ entity_id: String(item.client.id), new_client_name: "", issue_date: item.issue_date ?? today(),
        due_date: item.due_date ?? "", service_start: item.service_start ?? "", service_end: item.service_end ?? "",
        operation_type: item.operation_type, purchase_order: item.purchase_order, header: item.header, terms: item.terms,
        footer: item.footer });
      setRows(item.lines.map(({ id: _id, untaxed_cents: _u, vat_cents: _v, total_cents: _t, ...row }) => row));
    }
  }, [existing.data]);
  useEffect(() => {  // compte de vente par défaut sur la première ligne d'une nouvelle facture
    if (!editId && options.data?.default_account) setRows((r) => r.map((row) => ({ ...row, account_code: row.account_code || options.data!.default_account })));
  }, [editId, options.data]);

  if (!options.data || (editId && !existing.data)) return <Center h={300}><Loader /></Center>;
  const o = options.data;
  const item = existing.data?.item;
  if (item && item.status !== "draft") {
    return <Alert color="paille" mt="md">Pièce émise : elle ne se modifie plus. <AppLink href={`/sales/${item.id}`}>Retour à la pièce</AppLink></Alert>;
  }
  const set = (patch: Partial<Header>) => setHeader((h) => ({ ...h, ...patch }));
  const exempt = (item?.vat_mode ?? o.vat_mode) === "none";
  const isCredit = item?.kind === "credit_note";

  const submit = async () => {
    setSaving(true); setError(null);
    const body = { ...header, entity_id: header.entity_id === NEW_CLIENT ? "" : header.entity_id, lines: rows };
    try {
      const result = editId
        ? await api.patch<{ item: SaleDetail; notices: Notice[] }>(`/api/v1/sales/${editId}`, body)
        : await api.post<{ item: SaleDetail; notices: Notice[] }>("/api/v1/sales", body);
      showNotices(result.notices);
      void client.invalidateQueries({ queryKey: SALES_KEY });
      goTo(`/sales/${result.item.id}`);
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : "Erreur inattendue.");
    } finally {
      setSaving(false);
    }
  };

  const date = (name: keyof Header, label: string, props: Record<string, unknown> = {}) => (
    <TextInput type="date" label={label} value={header[name]} onChange={(e) => set({ [name]: e.currentTarget.value })} {...props} />
  );
  return (
    <>
      <PageHeader title={editId ? `${isCredit ? "Avoir" : "Facture"} brouillon` : "Nouvelle facture"}
        description={VAT_MODE_LABELS[item?.vat_mode ?? o.vat_mode]}
        actions={<Button variant="default" component={AppLink} href={editId ? `/sales/${editId}` : "/sales/"}>Annuler</Button>} />
      <form onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <Stack maw={1200}>
          {error && <Alert color="brique" role="alert">{error}</Alert>}
          <Fieldset legend="Client et dates">
            <Stack>
              <SimpleGrid cols={{ base: 1, md: 3 }}>
                <Select label="Client" required searchable disabled={isCredit} value={header.entity_id || null}
                  data={[{ value: NEW_CLIENT, label: "+ Nouveau client…" }, ...o.clients]}
                  onChange={(v) => set({ entity_id: v ?? "" })} />
                {header.entity_id === NEW_CLIENT && <TextInput label="Nom du nouveau client" required value={header.new_client_name}
                  description="Complétez ensuite son adresse sur sa fiche (Tiers) : elle figure sur la facture."
                  onChange={(e) => set({ new_client_name: e.currentTarget.value })} />}
                <Select label="Nature de l'opération" data={o.operation_types} value={header.operation_type} allowDeselect={false}
                  onChange={(v) => set({ operation_type: v ?? "services" })} />
              </SimpleGrid>
              <SimpleGrid cols={{ base: 2, md: 5 }}>
                {date("issue_date", "Date", { required: true })}
                {!isCredit && date("due_date", "Échéance", { description: `Vide : ${o.payment_terms_days} jours` })}
                {date("service_start", "Début de prestation")}
                {date("service_end", "Fin de prestation")}
                <TextInput label="Référence client" value={header.purchase_order} onChange={(e) => set({ purchase_order: e.currentTarget.value })} />
              </SimpleGrid>
            </Stack>
          </Fieldset>
          <Fieldset legend="Lignes">
            <SaleLinesEditor rows={rows} onChange={setRows} products={o.products} accounts={o.sale_accounts}
              defaultAccount={o.default_account} units={o.units} projects={o.projects} exempt={exempt} />
          </Fieldset>
          <Fieldset legend="Textes">
            <SimpleGrid cols={{ base: 1, md: 3 }}>
              <Textarea label="Introduction" autosize minRows={2} value={header.header} onChange={(e) => set({ header: e.currentTarget.value })} />
              <Textarea label="Conditions particulières" autosize minRows={2} value={header.terms} onChange={(e) => set({ terms: e.currentTarget.value })} />
              <Textarea label="Pied de facture" autosize minRows={2} value={header.footer} onChange={(e) => set({ footer: e.currentTarget.value })} />
            </SimpleGrid>
          </Fieldset>
          <Group>
            <Button type="submit" loading={saving}>Enregistrer le brouillon</Button>
            <Text size="sm" c="dimmed">Le numéro et l'écriture comptable sont attribués à l'émission.</Text>
          </Group>
        </Stack>
      </form>
    </>
  );
}

export default writeOnly(SaleFormPage, "Facture de vente", { href: "/sales/", label: "Ventes" });
