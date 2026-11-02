// Solde bancaire d'ouverture d'un compte bancaire (colonne « Solde bancaire ») et, si rien n'est encore
// passé au 512 avant sa date, écriture d'apport initial contre les fonds propres de la structure.
import { useState } from "react";
import { Alert, Button, Checkbox, Group, Loader, Select, Stack, Text } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyInput } from "../../components/Money";
import { formatDate } from "../../lib/format";
import { BANK_ACCOUNTS_KEY, type BankAccount, type OpeningBalance, type Option } from "./types";

interface OpeningResponse { item: OpeningBalance; meta: { counterparts: Option[] } }

export function OpeningBalanceForm({ bankAccount, onDone }: { bankAccount: BankAccount; onDone: () => void }) {
  const url = `/api/v1/bank-accounts/${bankAccount.id}/opening`;
  const { data } = useQuery({ queryKey: [...BANK_ACCOUNTS_KEY, "opening", bankAccount.id], queryFn: () => api.get<OpeningResponse>(url) });
  if (!data) return <Group justify="center" p="md"><Loader size="sm" /></Group>;
  return <Form url={url} opening={data.item} counterparts={data.meta.counterparts} onDone={onDone} />;
}

function Form({ url, opening, counterparts, onDone }: { url: string; opening: OpeningBalance; counterparts: Option[]; onDone: () => void }) {
  const [amount, setAmount] = useState<number | null>(opening.amount_cents);
  const [when, setWhen] = useState<string | null>(opening.date ?? opening.proposed_date);
  const canPost = opening.entry_allowed || !!opening.entry;
  const [postEntry, setPostEntry] = useState(canPost);
  const [counterpart, setCounterpart] = useState<string | null>(counterparts[0]?.value ?? null);
  const [error, setError] = useState<string | null>(null);
  const save = useAction((body: object) => api.put<{ notices: Notice[] }>(url, body), { invalidate: [BANK_ACCOUNTS_KEY], silent: true });
  const submit = (body: object) => save.mutate(body, {
    onSuccess: onDone, onError: (e) => setError(e instanceof Error ? e.message : "Enregistrement impossible."),
  });
  const withEntry = postEntry && canPost && amount !== 0;
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Solde du relevé bancaire au début de la journée choisie. Le solde bancaire affiché y ajoute les transactions
        importées (OFX, Qonto) à partir de cette date.
      </Text>
      {error && <Alert color="brique">{error}</Alert>}
      <Group grow>
        <DateInput label="Date" required valueFormat="DD/MM/YYYY" value={when} onChange={setWhen} />
        <MoneyInput label="Solde d'ouverture" required allowNegative value={amount} onChange={setAmount} data-autofocus />
      </Group>
      {opening.entry && (
        <Alert color="ardoise">
          Écriture d'apport initial {opening.entry.reference} ({opening.entry.counterpart}) : elle sera remplacée,
          ou supprimée si vous décochez la case.
        </Alert>
      )}
      {canPost ? (
        <>
          <Checkbox label="Passer l'écriture d'apport initial (banque contre fonds propres)" checked={postEntry}
            onChange={(e) => setPostEntry(e.currentTarget.checked)} />
          {withEntry && (
            <Select label="Compte de contrepartie" required data={counterparts} value={counterpart} onChange={setCounterpart}
              description="Association : 102 si l'apport est définitif, 103 avec droit de reprise. Société : 101 (capital) ; entreprise individuelle : 108 (compte de l'exploitant). Un compte « à créer » n'existe pas encore dans le plan." />
          )}
        </>
      ) : (
        <Text size="sm" c="dimmed">
          Le compte comptable a déjà des écritures avant le {formatDate(opening.proposed_date)} ou des à-nouveaux :
          son solde est déjà repris en comptabilité, aucune écriture d'apport n'est passée.
        </Text>
      )}
      <Group justify="space-between">
        <div>
          {opening.date && <Button variant="subtle" color="brique" loading={save.isPending}
            onClick={() => submit({ amount_cents: null })}>Retirer le solde d'ouverture</Button>}
        </div>
        <Group>
          <Button variant="default" onClick={onDone}>Annuler</Button>
          <Button loading={save.isPending} disabled={!when || amount === null || (withEntry && !counterpart)}
            onClick={() => submit({ amount_cents: amount, date: when, post_entry: withEntry, counterpart })}>Enregistrer</Button>
        </Group>
      </Group>
    </Stack>
  );
}
