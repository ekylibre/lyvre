// Membres d'une instance et leur rôle : page Accès (instance courante, /api/v1/access/members) et
// fiche instance de l'administrateur global (/api/v1/instances/<id>/members). Mêmes règles côté
// serveur (app/services/instance_access.py).
import { useState } from "react";
import { Alert, Badge, Button, Group, PasswordInput, SegmentedControl, Select, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { StatusBadge } from "../../components/StatusBadge";
import { knownAccount, ROLE_HELP, userChoices, type Member, type MembersMeta, type RoleOption, type UserOption } from "./members";

/** Ajout d'un membre : compte existant (liste si `users` est fourni, sinon par email) ou nouveau compte. */
function AddForm({ endpoint, invalidate, roles, users, members, onDone }: {
  endpoint: string; invalidate: unknown[][]; roles: RoleOption[]; users?: UserOption[]; members: Member[]; onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { kind: users ? "existing" : "email", user_id: null as string | null, email: "",
    role: "accountant", full_name: "", password: "" } });
  const add = useAction((values: typeof form.values) => {
    const body = values.kind === "existing"
      ? { user_id: Number(values.user_id), role: values.role }
      : { email: values.email, role: values.role, full_name: values.full_name, password: values.password };
    return api.post<{ notices: Notice[] }>(endpoint, body);
  }, { invalidate, silent: true });
  const already = new Set(members.map((m) => String(m.user_id)));
  const known = users && form.values.kind === "new" ? knownAccount(users, form.values.email) : undefined;
  return (
    <form onSubmit={form.onSubmit((values) => {
      if (values.kind === "existing" && !values.user_id) return form.setFieldError("user_id", "Choisissez un utilisateur.");
      add.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) });
    })}>
      <FormBody error={error} submitLabel="Donner l'accès" onCancel={onDone} loading={add.isPending}>
        {users ? (
          <>
            <SegmentedControl data={[{ value: "existing", label: "Compte existant" }, { value: "new", label: "Nouveau compte" }]}
              {...form.getInputProps("kind")} />
            {form.values.kind === "existing" ? (
              <Select label="Utilisateur" placeholder="Nom ou email" searchable data-autofocus nothingFoundMessage="Aucun compte"
                data={userChoices(users).filter((c) => !already.has(c.value))} {...form.getInputProps("user_id")} />
            ) : (
              <>
                <TextInput label="Email" type="email" required {...form.getInputProps("email")} />
                {known && (
                  <Text size="xs" c="dimmed">Un compte existe avec cet email : choisissez « Compte existant ».</Text>
                )}
                <TextInput label="Nom" {...form.getInputProps("full_name")} />
                <PasswordInput label="Mot de passe initial" required autoComplete="new-password"
                  description="8 caractères au moins, à transmettre à la personne ; elle le changera à sa première connexion."
                  {...form.getInputProps("password")} />
              </>
            )}
          </>
        ) : (
          <>
            <TextInput label="Email" type="email" required data-autofocus {...form.getInputProps("email")} />
            <Text size="sm" c="dimmed">Si personne n'a encore de compte avec cet email, renseignez un mot de passe initial : le
              compte est créé, vous transmettez ce mot de passe à la personne, qui le changera à sa première connexion.</Text>
            <TextInput label="Nom (nouveau compte)" {...form.getInputProps("full_name")} />
            <PasswordInput label="Mot de passe initial (nouveau compte)" autoComplete="new-password" {...form.getInputProps("password")} />
          </>
        )}
        <Select label="Rôle" data={roles} allowDeselect={false} description={ROLE_HELP[form.values.role]} {...form.getInputProps("role")} />
      </FormBody>
    </form>
  );
}

export function MembersManager({ id, endpoint, queryKey, users, actions }: {
  /** Identifiant de la grille (colonnes mémorisées). */
  id: string;
  endpoint: string;
  queryKey: unknown[];
  /** Comptes proposés à l'ajout (administrateur global) ; sinon ajout par email. */
  users?: UserOption[];
  actions?: (open: () => void) => React.ReactNode;
}) {
  const [adding, setAdding] = useState(false);
  const { data, isFetching, error } = useList<Member, MembersMeta>(queryKey, endpoint);
  const roles = data?.meta?.roles ?? [];
  const invalidate = [queryKey, ["users"]];
  const setRole = useAction(({ m, role }: { m: Member; role: string }) =>
    api.patch<{ notices: Notice[] }>(`${endpoint}/${m.user_id}`, { role }), { invalidate });
  const remove = useAction((m: Member) => api.delete<{ notices: Notice[] }>(`${endpoint}/${m.user_id}`), { invalidate });
  const open = () => setAdding(true);

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
      {actions?.(open)}
      {error && <Alert color="brique" mb="sm">{(error as Error).message}</Alert>}
      <Group gap="lg" mb="sm">
        {roles.map((r) => <Text key={r.value} size="xs" c="dimmed"><b>{r.label}</b> : {ROLE_HELP[r.value]}</Text>)}
      </Group>
      <DataGrid id={id} records={data?.items} columns={columns} fetching={isFetching} idAccessor="user_id" emptyText="Aucun membre." />
      <FormModal opened={adding} onClose={() => setAdding(false)} title="Donner un accès">
        <AddForm endpoint={endpoint} invalidate={invalidate} roles={roles} users={users} members={data?.items ?? []}
          onDone={() => setAdding(false)} />
      </FormModal>
    </>
  );
}
