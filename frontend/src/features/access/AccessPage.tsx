// Configuration › Accès (administrateur de l'instance) : qui accède à cette instance, avec quel
// rôle. Administrateur : tout ; trésorier : saisie, rapprochement, clôture provisoire ;
// expert-comptable : lecture de toute la comptabilité et export FEC, sans modification.
import { useState } from "react";
import { Alert, Badge, Button, Group, PasswordInput, Select, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useCan, useCurrentSession } from "../../api/session";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";

export interface Member {
  user_id: number; email: string; full_name: string | null; role: "admin" | "treasurer" | "accountant";
  role_label: string; global_admin: boolean; is_active: boolean; is_me: boolean;
}
type Meta = { roles: { value: string; label: string }[] };

const KEY = ["access-members"];
export const ROLE_HELP: Record<string, string> = {
  admin: "Tout, dont les accès, les intégrations et la clôture définitive.",
  treasurer: "Saisie, rapprochement, imports, clôture provisoire.",
  accountant: "Consulte toute la comptabilité et exporte le FEC, sans rien modifier.",
};

function AddForm({ roles, onDone }: { roles: Meta["roles"]; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { email: "", role: "accountant", full_name: "", password: "" } });
  const add = useAction((values: typeof form.values) => api.post<{ notices: Notice[] }>("/api/v1/access/members", values),
    { invalidate: [KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => add.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel="Donner l'accès" onCancel={onDone} loading={add.isPending}>
        <TextInput label="Email" type="email" required data-autofocus {...form.getInputProps("email")} />
        <Select label="Rôle" data={roles} allowDeselect={false} description={ROLE_HELP[form.values.role]} {...form.getInputProps("role")} />
        <Text size="sm" c="dimmed">Si personne n'a encore de compte avec cet email, renseignez un mot de passe initial : le
          compte est créé et vous transmettez ce mot de passe à la personne.</Text>
        <TextInput label="Nom (nouveau compte)" {...form.getInputProps("full_name")} />
        <PasswordInput label="Mot de passe initial (nouveau compte)" autoComplete="new-password" {...form.getInputProps("password")} />
      </FormBody>
    </form>
  );
}

export default function AccessPage() {
  const session = useCurrentSession();
  const can = useCan();
  const [adding, setAdding] = useState(false);
  const { data, isFetching, error } = useList<Member, Meta>(KEY, "/api/v1/access/members", { enabled: can.instanceAdmin });
  const roles = data?.meta?.roles ?? [];
  const opts = { invalidate: [KEY] };
  const setRole = useAction(({ m, role }: { m: Member; role: string }) =>
    api.patch<{ notices: Notice[] }>(`/api/v1/access/members/${m.user_id}`, { role }), opts);
  const remove = useAction((m: Member) => api.delete<{ notices: Notice[] }>(`/api/v1/access/members/${m.user_id}`), opts);

  if (!can.instanceAdmin) {
    return <><PageHeader title="Accès" /><Alert color="ardoise">Réservé à l'administrateur de l'instance.</Alert></>;
  }
  const columns: GridColumn<Member>[] = [
    { accessor: "email", title: "Personne", hideable: false, sortable: true, render: (m) => (
      <div>
        <Text size="sm" fw={500}>{m.full_name ?? m.email}{m.is_me && <Text span c="dimmed" size="sm"> (vous)</Text>}</Text>
        {m.full_name && <Text size="xs" c="dimmed">{m.email}</Text>}
      </div>
    ) },
    { accessor: "role", title: "Rôle", render: (m) => m.global_admin
      ? <Group gap={6}><StatusBadge tone="info">Administrateur</StatusBadge><Badge size="xs" variant="outline" color="gray">toutes les instances</Badge></Group>
      : <Select aria-label={`Rôle de ${m.email}`} data={roles} value={m.role} allowDeselect={false} w={190} size="xs"
          onChange={(role) => role && role !== m.role && setRole.mutate({ m, role })} /> },
    { accessor: "is_active", title: "Compte", render: (m) => <StatusBadge tone={m.is_active ? "ok" : "neutral"}>{m.is_active ? "Actif" : "Désactivé"}</StatusBadge> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right", render: (m) => !m.global_admin && (
      <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
        title: `Retirer l'accès de ${m.email} ?`, message: "Son compte est conservé ; il n'accède plus à cette instance.",
        confirmLabel: "Retirer", onConfirm: () => remove.mutate(m) })}>Retirer</Button>
    ) },
  ];
  return (
    <>
      <PageHeader title="Accès" description={`Personnes qui accèdent à ${session.instance?.label ?? "cette instance"}, et leur rôle.`}
        actions={<Button onClick={() => setAdding(true)}>Donner un accès</Button>} />
      {error && <Alert color="brique" mb="sm">{(error as Error).message}</Alert>}
      <Group gap="lg" mb="sm">
        {roles.map((r) => <Text key={r.value} size="xs" c="dimmed"><b>{r.label}</b> : {ROLE_HELP[r.value]}</Text>)}
      </Group>
      <DataGrid id="access-members" records={data?.items} columns={columns} fetching={isFetching} idAccessor="user_id"
        emptyText="Aucun membre." />
      <FormModal opened={adding} onClose={() => setAdding(false)} title="Donner un accès">
        <AddForm roles={roles} onDone={() => setAdding(false)} />
      </FormModal>
    </>
  );
}
