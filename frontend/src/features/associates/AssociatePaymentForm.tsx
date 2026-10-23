// Facture d'achat réglée par le compte courant d'un associé : écriture 401 / 455 au journal AS.
// Rien n'est écrit dans Qonto.
import { useState } from "react";
import { Select, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { formatEuros } from "../../lib/format";
import type { Option } from "../purchases/types";

export function AssociatePaymentForm({ purchaseId, totalCents, associates, invalidate, onDone }: {
  purchaseId: number; totalCents: number; associates: Option[]; invalidate: unknown[][]; onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: {
    associate_id: associates.length === 1 ? associates[0].value : null as string | null,
    paid_on: new Date().toISOString().slice(0, 10),
  } });
  const pay = useAction((values: typeof form.values) =>
    api.post<{ notices: Notice[] }>(`/api/v1/purchases/${purchaseId}/associate-payment`, values), { invalidate, silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => pay.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel="Enregistrer le règlement" onCancel={onDone} loading={pay.isPending}>
        <Text size="sm">
          L'associé a payé {formatEuros(totalCents)} pour la société : la somme est portée au crédit de son compte courant
          (la société la lui doit). Rien n'est modifié dans Qonto.
        </Text>
        <Select label="Associé" required searchable data-autofocus data={associates} {...form.getInputProps("associate_id")} />
        <TextInput label="Date du paiement" type="date" required w={200} {...form.getInputProps("paid_on")} />
      </FormBody>
    </form>
  );
}
