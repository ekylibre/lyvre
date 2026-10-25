// Brevo (lot B1) : choix de la liste des adhérents parmi les listes du compte, et état des attributs
// attendus par la synchronisation, avec leur création explicite. Lus par le serveur (la clé n'arrive
// jamais ici) ; sans clé enregistrée, la liste se saisit par son numéro.
import { Alert, Badge, Button, Group, Paper, Select, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";

interface BrevoList { value: string; label: string; contacts: number }
interface BrevoAttribute { name: string; type: string; label: string; shared: boolean; present: boolean }

const LISTS_KEY = ["brevo", "lists"];
const ATTRIBUTES_KEY = ["brevo", "attributes"];

export function BrevoListField({ label, description, value, onChange, keySaved }: {
  label: React.ReactNode; description?: string; value: string; onChange: (value: string) => void; keySaved: boolean;
}) {
  const lists = useQuery({ queryKey: LISTS_KEY, enabled: keySaved, retry: false,
    queryFn: () => api.get<{ items: BrevoList[] }>("/api/v1/brevo/lists") });
  if (!keySaved || lists.isError) {
    return (
      <Stack gap={4}>
        <TextInput label={label} description={description} placeholder="N° de la liste" value={value}
          classNames={{ input: "lv-num" }} onChange={(e) => onChange(e.currentTarget.value)} />
        {lists.isError && <Text size="xs" c="var(--lv-brique)">{(lists.error as Error).message}</Text>}
      </Stack>
    );
  }
  return (
    <Select label={label} description={description} searchable placeholder={lists.isPending ? "Lecture des listes…" : "Choisir"}
      data={(lists.data?.items ?? []).map((l) => ({ value: l.value, label: `${l.label} (${l.contacts} contacts)` }))}
      value={value || null} onChange={(v) => onChange(v ?? "")} />
  );
}

export function BrevoAttributes({ admin }: { admin: boolean }) {
  const client = useQueryClient();
  const attributes = useQuery({ queryKey: ATTRIBUTES_KEY, retry: false,
    queryFn: () => api.get<{ items: BrevoAttribute[] }>("/api/v1/brevo/attributes") });
  const create = useAction(() => api.post<{ items: BrevoAttribute[]; notices: Notice[] }>("/api/v1/brevo/attributes"));
  const items = attributes.data?.items ?? [];
  const missing = items.filter((a) => !a.present);
  return (
    <Paper p="md" mb="md">
      <Title order={3} mb="sm">Attributs des contacts</Title>
      {attributes.isError ? <Alert color="paille">{(attributes.error as Error).message}</Alert> : (
        <Stack gap="xs">
          <Table verticalSpacing={4}>
            <Table.Tbody>
              {items.map((a) => (
                <Table.Tr key={a.name}>
                  <Table.Td><Text size="sm" className="lv-num">{a.name}</Text><Text size="xs" c="dimmed">{a.label}</Text></Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{a.shared ? "complété s'il est vide" : "tenu par Lyvre"}</Text></Table.Td>
                  <Table.Td ta="right">{a.present ? <Badge size="xs" variant="light" color="lichen">présent</Badge>
                    : <Badge size="xs" variant="light" color="paille">à créer</Badge>}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          {missing.length > 0 && admin && (
            <Group justify="flex-end">
              <Button size="compact-md" variant="default" loading={create.isPending}
                onClick={() => create.mutate(undefined, { onSuccess: (body) => client.setQueryData(ATTRIBUTES_KEY, { items: body.items }) })}>
                Créer les attributs manquants ({missing.length})</Button>
            </Group>
          )}
          <Text size="xs" c="dimmed">Un attribut absent de Brevo n'est pas envoyé. PRENOM et NOM ne remplacent jamais une valeur
            déjà saisie dans Brevo.</Text>
        </Stack>
      )}
    </Paper>
  );
}
