// Saisie (/entries/new, ?bt_id= depuis une transaction) et modification (/entries/:id/edit).
import { useParams, useSearchParams } from "react-router";
import { Alert, Button, Center, Loader, Stack } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { useGoTo } from "../../app/navigation";
import { EntryEditor, type EntryFormData } from "./EntryEditor";
import { ENTRIES_KEY } from "./EntriesPage";

export default function EntryFormPage() {
  const params = useParams();
  const [search] = useSearchParams();
  const goTo = useGoTo();
  const client = useQueryClient();
  const entryId = params.entry_id ? Number(params.entry_id) : null;
  const btId = search.get("bt_id");
  const url = entryId ? `/api/v1/entries/form?entry_id=${entryId}` : `/api/v1/entries/form${btId ? `?bt_id=${btId}` : ""}`;
  const { data, error, isPending } = useQuery({
    queryKey: [...ENTRIES_KEY, "form", url], queryFn: () => api.get<EntryFormData>(url), gcTime: 0, retry: false,
  });
  const back = data?.bank_transaction?.return_url ?? (entryId ? `/entries/${entryId}` : "/entries/");

  if (isPending) return <Center h={300}><Loader /></Center>;
  if (error || !data) {
    return (
      <Stack maw={640}>
        <PageHeader title={entryId ? "Modifier l'écriture" : "Saisir une écriture"} />
        <Alert color="brique" role="alert">{error instanceof ApiError ? error.message : "Le formulaire n'a pas pu être préparé."}</Alert>
        <Button variant="default" w="fit-content" onClick={() => goTo(entryId ? `/entries/${entryId}` : "/entries/")}>Revenir</Button>
      </Stack>
    );
  }
  return (
    <>
      <PageHeader title={data.mode === "edit" ? `Modifier l'écriture ${data.reference ?? ""}` : "Saisir une écriture"}
        description="Débit = crédit : l'écriture s'enregistre quand elle est équilibrée." />
      <EntryEditor data={data} onCancel={() => goTo(back)}
        onSaved={(entry, after) => {
          void client.invalidateQueries({ queryKey: [...ENTRIES_KEY, "list"] });
          void client.invalidateQueries({ queryKey: [...ENTRIES_KEY, entry.id] });
          void client.invalidateQueries({ queryKey: ["dashboard"] });
          if (after === "continue" && data.mode === "create" && !data.bank_transaction) return;
          goTo(data.bank_transaction?.return_url ?? `/entries/${entry.id}`);
        }} />
    </>
  );
}
