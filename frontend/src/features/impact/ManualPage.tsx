// Indicateurs › Saisie manuelle : chiffres mensuels sans API (Vinted, groupe Facebook, collectés / donnés).
import { useEffect, useState } from "react";
import { Button, Center, Loader, NumberInput, Select, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useUrlParams } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { IMPACT_KEY } from "./types";
import { writeOnly } from "../../components/ReadOnlyPage";

interface Field { key: string; label: string; unit: string; in_euros: boolean; value: number | null }
interface Manual { month: string; fields: Field[]; meta: { months: { value: string; label: string }[] } }

function ManualPage() {
  const [params, setParams] = useUrlParams({ month: "" });
  const key = [...IMPACT_KEY, "manual", params.month];
  const { data } = useQuery({ queryKey: key, placeholderData: (prev) => prev,
    queryFn: () => api.get<Manual>(`/api/v1/impact/manual${params.month ? `?month=${params.month}` : ""}`) });
  const [values, setValues] = useState<Record<string, string | number>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (data) setValues(Object.fromEntries(data.fields.map((f) => [f.key, f.value ?? ""])));
  }, [data]);
  const save = useAction(() => api.put<{ notices: Notice[] }>("/api/v1/impact/manual", { month: data?.month, values }),
    { invalidate: [IMPACT_KEY], silent: true });
  if (!data) return <Center h={300}><Loader /></Center>;
  return (
    <>
      <PageHeader title="Saisie manuelle" description="Chiffres sans API : Vinted, groupe Facebook, articles collectés et donnés."
        actions={<Button variant="default" component={AppLink} href="/impact/">Tableau de bord</Button>} />
      <form onSubmit={(e) => {
        e.preventDefault(); setErrors({});
        save.mutate(undefined, { onError: (err) => setErrors(err instanceof ApiError ? err.fields : {}) });
      }}>
        <Stack maw={520}>
          <Select label="Mois" data={data.meta.months} value={data.month} allowDeselect={false} searchable
            onChange={(month) => setParams({ month: month ?? "" })} />
          {data.fields.map((f) => (
            <NumberInput key={f.key} label={f.label} description={<Text span size="xs" className="lv-num">{f.key}</Text>}
              placeholder="vide : valeur inchangée" min={0} decimalSeparator="," decimalScale={f.in_euros ? 2 : undefined}
              rightSection={<Text size="sm" c="dimmed">{f.unit}</Text>} rightSectionWidth={70}
              value={values[f.key] ?? ""} error={errors[f.key]} onChange={(v) => setValues({ ...values, [f.key]: v })} />
          ))}
          <div><Button type="submit" loading={save.isPending}>Enregistrer le mois</Button></div>
        </Stack>
      </form>
    </>
  );
}

export default writeOnly(ManualPage, "Saisie manuelle", { href: "/impact/", label: "Voir le tableau de bord." });
