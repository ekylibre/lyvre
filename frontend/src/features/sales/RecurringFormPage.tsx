// Ventes › Facture récurrente (/sales/recurring/new, /sales/recurring/<id>) : libellé, client,
// périodicité, jour d'échéance, terme à échoir ou échu, début et fin, lignes ({periode} est remplacé
// par la période facturée), émission avec Qonto ; arrêt ou suppression.
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Alert, Button, Center, Checkbox, Fieldset, Group, Loader, Select, SimpleGrid, Stack, Text, TextInput } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { showNotices, useAction, type Notice } from "../../api/resources";
import { ConfirmButton } from "../../components/ConfirmButton";
import { PageHeader } from "../../components/PageHeader";
import { writeOnly } from "../../components/ReadOnlyPage";
import { AppLink, useGoTo } from "../../app/navigation";
import { SaleLinesEditor } from "./SaleLinesEditor";
import { EMPTY_SALE_LINE, RECURRENCES_KEY, SALES_KEY, type Recurrence, type SaleFormOptions, type SaleLineRow } from "./types";

const FREQUENCIES = [{ value: "monthly", label: "Mensuelle" }, { value: "quarterly", label: "Trimestrielle" }, { value: "yearly", label: "Annuelle" }];
const today = () => new Date().toISOString().slice(0, 10);

function RecurringFormPage() {
  const id = Number(useParams().rec_id) || null;
  const client = useQueryClient();
  const goTo = useGoTo();
  const options = useQuery({ queryKey: [...SALES_KEY, "form-options"], queryFn: () => api.get<SaleFormOptions>("/api/v1/sales/form-options") });
  const existing = useQuery({ queryKey: [...RECURRENCES_KEY, id], enabled: !!id,
    queryFn: () => api.get<{ item: Recurrence }>(`/api/v1/recurrences/${id}`) });
  const [v, setV] = useState({ label: "", entity_id: "", frequency: "monthly", due_day: "1", start_date: today(), end_date: "",
    in_advance: true, qonto_emit: false, active: true });
  const [rows, setRows] = useState<SaleLineRow[]>([{ ...EMPTY_SALE_LINE, label: "{periode}" }]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/recurrences/${id}`), { invalidate: [RECURRENCES_KEY] });
  useEffect(() => {
    const r = existing.data?.item;
    if (r) {
      setV({ label: r.label, entity_id: String(r.client.id), frequency: r.frequency, due_day: String(r.due_day), start_date: r.start_date,
        end_date: r.end_date ?? "", in_advance: r.in_advance, qonto_emit: r.qonto_emit, active: r.active });
      setRows((r.lines ?? []).map(({ id: _id, ...row }) => row));
    }
  }, [existing.data]);
  if (!options.data || (id && !existing.data)) return <Center h={300}><Loader /></Center>;
  const o = options.data;
  const set = (patch: Partial<typeof v>) => setV((x) => ({ ...x, ...patch }));
  const submit = async () => {
    setSaving(true); setError(null);
    try {
      const body = { ...v, end_date: v.end_date || null, lines: rows };
      const result = id ? await api.patch<{ item: Recurrence; notices: Notice[] }>(`/api/v1/recurrences/${id}`, body)
        : await api.post<{ item: Recurrence; notices: Notice[] }>("/api/v1/recurrences", body);
      showNotices(result.notices);
      void client.invalidateQueries({ queryKey: RECURRENCES_KEY });
      goTo("/sales/recurring");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur inattendue.");
    } finally {
      setSaving(false);
    }
  };
  return (
    <>
      <PageHeader title={id ? v.label || "Facture récurrente" : "Nouvelle facture récurrente"}
        description="Chaque échéance est préparée en brouillon dans « À émettre » ; {periode} dans une désignation devient la période facturée."
        actions={<>
          {id && <ConfirmButton title="Supprimer cette facture récurrente ?" confirmLabel="Supprimer" loading={remove.isPending}
            message="Les factures déjà préparées ou émises restent." onConfirm={() => remove.mutate(undefined, { onSuccess: () => goTo("/sales/recurring") })}>Supprimer</ConfirmButton>}
          <Button variant="default" component={AppLink} href="/sales/recurring">Annuler</Button>
        </>} />
      <form onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <Stack maw={1200}>
          {error && <Alert color="brique" role="alert">{error}</Alert>}
          <Fieldset legend="Échéancier">
            <Stack>
              <SimpleGrid cols={{ base: 1, md: 3 }}>
                <TextInput label="Libellé" required value={v.label} onChange={(e) => set({ label: e.currentTarget.value })} placeholder="Abonnement, maintenance…" />
                <Select label="Client" required searchable data={o.clients} value={v.entity_id || null} onChange={(x) => set({ entity_id: x ?? "" })} />
                <Select label="Périodicité" data={FREQUENCIES} allowDeselect={false} value={v.frequency} onChange={(x) => set({ frequency: x ?? "monthly" })} />
              </SimpleGrid>
              <SimpleGrid cols={{ base: 2, md: 4 }}>
                <TextInput label="Jour d'échéance" inputMode="numeric" value={v.due_day} onChange={(e) => set({ due_day: e.currentTarget.value })} description="1 à 28" />
                <TextInput label="Début" type="date" required value={v.start_date} onChange={(e) => set({ start_date: e.currentTarget.value })} />
                <TextInput label="Fin" type="date" value={v.end_date} onChange={(e) => set({ end_date: e.currentTarget.value })} description="Vide : sans fin" />
                <Select label="Terme" allowDeselect={false} value={v.in_advance ? "1" : "0"} onChange={(x) => set({ in_advance: x === "1" })}
                  data={[{ value: "1", label: "À échoir (période qui commence)" }, { value: "0", label: "Échu (période écoulée)" }]} />
              </SimpleGrid>
              <Group>
                <Checkbox label="Active" checked={v.active} onChange={(e) => set({ active: e.currentTarget.checked })} />
                {o.qonto && <Checkbox label="Émettre avec Qonto" checked={v.qonto_emit} onChange={(e) => set({ qonto_emit: e.currentTarget.checked })} />}
              </Group>
            </Stack>
          </Fieldset>
          <Fieldset legend="Lignes">
            <SaleLinesEditor rows={rows} onChange={setRows} products={o.products} accounts={o.sale_accounts}
              defaultAccount={o.default_account} units={o.units} projects={o.projects} exempt={o.vat_mode === "none"} />
          </Fieldset>
          <Group><Button type="submit" loading={saving}>Enregistrer</Button>
            <Text size="sm" c="dimmed">Modifier les lignes ne change pas les factures déjà préparées.</Text></Group>
        </Stack>
      </form>
    </>
  );
}

export default writeOnly(RecurringFormPage, "Facture récurrente", { href: "/sales/recurring", label: "Factures récurrentes" });
