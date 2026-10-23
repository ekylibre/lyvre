// Associé : création (tiers existant ou nouveau, compte courant 4551… proposé) et modification
// (compte tant qu'il n'a pas d'écriture, taux d'intérêt, notes). Réservé à l'administrateur.
import { useState } from "react";
import { SegmentedControl, Select, Textarea, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { ASSOCIATES_KEY, type Associate, type AssociatesMeta } from "./types";

export function AssociateForm({ associate, meta, accountLocked = false, onDone }: {
  associate: Associate | null; meta: AssociatesMeta | undefined; accountLocked?: boolean; onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: {
    kind: (meta?.entities.length ?? 0) > 0 ? "existing" : "new", entity_id: null as string | null, new_name: "",
    account_code: associate?.account_code ?? "", interest_rate: associate?.interest_rate ?? "", notes: associate?.notes ?? "",
  } });
  const save = useAction(({ kind, entity_id, new_name, ...values }: typeof form.values) => associate
    ? api.patch<{ notices: Notice[] }>(`/api/v1/associates/${associate.id}`, values)
    : api.post<{ notices: Notice[] }>("/api/v1/associates", kind === "existing" ? { entity_id, ...values } : { new_name, ...values }),
  { invalidate: [ASSOCIATES_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={associate ? "Enregistrer" : "Ajouter l'associé"} onCancel={onDone} loading={save.isPending}>
        {!associate && (
          <>
            <SegmentedControl data={[{ value: "existing", label: "Tiers existant" }, { value: "new", label: "Nouveau tiers" }]}
              {...form.getInputProps("kind")} />
            {form.values.kind === "existing" ? (
              <Select label="Tiers" placeholder="Nom" searchable required data-autofocus data={meta?.entities ?? []}
                nothingFoundMessage="Aucun tiers" {...form.getInputProps("entity_id")} />
            ) : (
              <TextInput label="Nom" required data-autofocus description="Personne ou société ; le tiers est créé."
                {...form.getInputProps("new_name")} />
            )}
          </>
        )}
        <TextInput label="Compte courant" classNames={{ input: "lv-num" }} disabled={accountLocked}
          placeholder={associate ? undefined : meta?.next_account_code ?? "455…"}
          description={accountLocked ? "Le compte a des écritures : il ne change plus."
            : "Sous-compte 455 ; vide : le prochain 4551… libre. Un 455 existant peut être repris."}
          {...form.getInputProps("account_code")} />
        <TextInput label="Taux d'intérêt du compte courant (%)" w={260} inputMode="decimal"
          placeholder="Taux de la structure" description="Vide : taux par défaut de la structure (Configuration › Structure)."
          {...form.getInputProps("interest_rate")} />
        <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
      </FormBody>
    </form>
  );
}
