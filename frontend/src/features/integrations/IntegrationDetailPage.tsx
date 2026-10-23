// Configuration › Intégration (admin) : configuration (secret jamais réaffiché : vide = conservé,
// « Effacer » le supprime), activation, test de connexion, dernière synchronisation.
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import {
  Alert, Anchor, Button, Center, Checkbox, Grid, Group, Loader, Paper, PasswordInput, Stack, Text, TextInput, Textarea, Title, Tooltip,
} from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { SESSION_KEY } from "../../api/session";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { AppLink } from "../../app/navigation";
import { IntegrationLogo } from "./IntegrationLogo";
import { INTEGRATIONS_KEY, STATUS_TONES, checkSummary, localDateTime, type Field, type IntegrationDetail } from "./types";

const SYNC_LABELS: Record<string, string> = { done: "Terminée", failed: "En échec", running: "En cours" };

function placeholder(f: Field) {
  if (f.secret && f.source !== "none") return "•••••••• (enregistré)";
  return f.env_value ?? f.help;
}

function hint(f: Field) {
  if (f.secret && f.source === "db") return "Laisser vide pour garder la valeur enregistrée.";
  if (f.secret && f.source === "env") return "Repli .env actif : laisser vide pour le garder.";
  if (f.env_value) return "Valeur du .env utilisée tant que ce champ est vide.";
  return f.help && f.input !== "textarea" && !f.secret && f.source !== "none" ? f.help : undefined;
}

export default function IntegrationDetailPage() {
  const service = useParams().service ?? "";
  const client = useQueryClient();
  const key = [...INTEGRATIONS_KEY, service];
  const { data, error } = useQuery({ queryKey: key, retry: false,
    queryFn: () => api.get<IntegrationDetail>(`/api/v1/integrations/${service}`) });
  const [values, setValues] = useState<Record<string, string>>({});
  const [clear, setClear] = useState<string[]>([]);
  useEffect(() => {
    if (data) { setValues(Object.fromEntries(data.fields.map((f) => [f.key, f.value]))); setClear([]); }
  }, [data]);
  // Les actions renvoient la fiche à jour : elle remplace le cache (pas de second appel).
  const refresh = (body: IntegrationDetail) => { client.setQueryData(key, body); void client.invalidateQueries({ queryKey: INTEGRATIONS_KEY, exact: true }); };
  // Activer ou désactiver change les menus et ce que montrent les écrans (session).
  const toggled = (body: IntegrationDetail) => { refresh(body); void client.invalidateQueries({ queryKey: SESSION_KEY }); };
  const save = useAction(() => api.put<IntegrationDetail & { notices: Notice[] }>(`/api/v1/integrations/${service}`, { values, clear }));
  const toggle = useAction((enabled: boolean) => api.post<IntegrationDetail & { notices: Notice[] }>(`/api/v1/integrations/${service}/enabled`, { enabled }));
  const check = useAction(() => api.post<IntegrationDetail & { notices: Notice[] }>(`/api/v1/integrations/${service}/check`));
  const saveScopes = useAction((scopes: string[]) => api.post<IntegrationDetail & { notices: Notice[] }>(`/api/v1/integrations/${service}/scopes`, { scopes }));
  const [scopes, setScopes] = useState<string[] | null>(null);

  if (error) return <Alert color="brique" mt="md">{(error as Error).message}</Alert>;
  if (!data) return <Center h={300}><Loader /></Center>;
  const v = data.item;
  const canCheck = v.enabled && v.configured;
  const s = v.last_sync;
  return (
    <>
      <PageHeader title={v.label} description={v.description} icon={<IntegrationLogo slug={v.slug} size={48} />}
        actions={<><StatusBadge tone={STATUS_TONES[v.status]}>{v.status_label}</StatusBadge>
          <Button variant="default" component={AppLink} href="/configuration/integrations/">Intégrations</Button></>} />
      {v.recommended && !v.enabled && (
        <Alert color="lichen" mb="md" title={`${v.label} est recommandée pour votre structure.`}>
          <Group justify="space-between">
            <Text size="sm">Activez-la, puis renseignez sa configuration et testez-la.</Text>
            <Button size="compact-md" loading={toggle.isPending} onClick={() => toggle.mutate(true, { onSuccess: toggled })}>Activer</Button>
          </Group>
        </Alert>
      )}
      <Grid>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Paper p="md">
            <Title order={3} mb="sm">Configuration</Title>
            <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined, { onSuccess: refresh }); }} autoComplete="off">
              <Stack>
                {data.fields.map((f) => {
                  const common = {
                    label: <>{f.label}{f.source === "db" && <Text span size="xs" c="var(--lv-lichen)"> (en base)</Text>}
                      {f.source === "env" && <Text span size="xs" c="dimmed"> (repli .env)</Text>}</>,
                    withAsterisk: f.required, placeholder: placeholder(f), description: hint(f),
                    value: values[f.key] ?? "", disabled: clear.includes(f.key),
                    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setValues({ ...values, [f.key]: e.currentTarget.value }),
                  };
                  return (
                    <div key={f.key}>
                      {f.input === "textarea" ? <Textarea {...common} autosize minRows={4} classNames={{ input: "lv-num" }} />
                        : f.input === "password" ? <PasswordInput {...common} autoComplete="new-password" />
                        : <TextInput {...common} />}
                      {f.secret && f.source === "db" && <Checkbox mt={4} size="xs" label="Effacer la valeur enregistrée" checked={clear.includes(f.key)}
                        onChange={(e) => setClear(e.currentTarget.checked ? [...clear, f.key] : clear.filter((k) => k !== f.key))} />}
                    </div>
                  );
                })}
                <Group justify="space-between">
                  <Text size="xs" c="dimmed">Vider un champ supprime sa valeur en base (le repli .env reprend).</Text>
                  <Button type="submit" loading={save.isPending}>{v.enabled ? "Enregistrer et tester" : "Enregistrer"}</Button>
                </Group>
              </Stack>
            </form>
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Paper p="md" mb="md">
            <Title order={3} mb="sm">État</Title>
            <Group justify="space-between" mb="sm">
              <Text>Intégration <b>{v.enabled ? "activée" : "désactivée"}</b></Text>
              <Button size="compact-md" variant="default" loading={toggle.isPending}
                onClick={() => toggle.mutate(!v.enabled, { onSuccess: toggled })}>{v.enabled ? "Désactiver" : "Activer"}</Button>
            </Group>
            {v.last_check ? (
              <>
                <Text size="sm" c="dimmed">Dernier test : {checkSummary(v.last_check)}{v.check_outdated && " — configuration modifiée depuis"}</Text>
                <Text size="sm" mb="sm" c={v.last_check.ok ? "var(--lv-lichen)" : "var(--lv-brique)"}>
                  {v.last_check.ok ? "✓" : "✗"} {v.last_check.message}</Text>
              </>
            ) : <Text size="sm" c="dimmed" mb="sm">Jamais testée.</Text>}
            <Group justify="flex-end">
              <Tooltip label={v.enabled ? "Configuration incomplète" : "Intégration désactivée"} disabled={canCheck}>
                <Button size="compact-md" variant="default" disabled={!canCheck} loading={check.isPending}
                  onClick={() => check.mutate(undefined, { onSuccess: refresh })}>Tester maintenant</Button>
              </Tooltip>
            </Group>
          </Paper>
          {!!v.scopes?.length && (
            <Paper p="md" mb="md">
              <Title order={3} mb="sm">Périmètre</Title>
              <Checkbox.Group value={scopes ?? v.scopes.filter((x) => x.checked).map((x) => x.value)} onChange={setScopes}
                description="Seules les parties cochées sont utilisées (synchronisation, envois, boutons) ; les autres n'apparaissent pas.">
                <Stack gap={6} mt={6}>{v.scopes.map((x) => <Checkbox key={x.value} value={x.value} label={x.label} />)}</Stack>
              </Checkbox.Group>
              <Group justify="flex-end" mt="sm">
                <Button size="compact-md" variant="default" disabled={scopes === null} loading={saveScopes.isPending}
                  onClick={() => scopes && saveScopes.mutate(scopes, { onSuccess: (body) => { toggled(body); setScopes(null); } })}>
                  Enregistrer le périmètre</Button>
              </Group>
            </Paper>
          )}
          <Paper p="md">
            <Title order={3} mb="sm">Dernière synchronisation</Title>
            {!v.sync_tracked ? <Text size="sm" c="dimmed">Non suivie pour cette intégration.</Text>
              : !s ? <Text size="sm" c="dimmed">Aucune synchronisation lancée.</Text>
              : (
                <Stack gap={4}>
                  <Group gap="xs">
                    <StatusBadge tone={s.status === "done" ? "ok" : s.status === "failed" ? "gap" : "info"}>{SYNC_LABELS[s.status] ?? s.status}</StatusBadge>
                    <Text size="sm" c="dimmed">{localDateTime(s.finished_at ?? s.started_at)}</Text>
                  </Group>
                  {s.imported !== null && <Text size="sm">{s.imported} élément(s) importé(s).</Text>}
                  {s.message && <Text size="sm">{s.message}</Text>}
                  {s.errors.map((e) => <Text key={e} size="sm" c="var(--lv-brique)">{e}</Text>)}
                  <Anchor component={AppLink} href={s.url} size="sm">{s.link_label}</Anchor>
                </Stack>
              )}
          </Paper>
        </Grid.Col>
      </Grid>
    </>
  );
}
