// Administration › Utilisateurs (administrateurs seulement).
import { useState } from "react";
import { Button, Group, PasswordInput, Select, Stack, Switch, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { useRouteModal } from "../../app/useRouteModal";

export interface Membership { instance_id: number; instance: string; role: string; role_label: string }
export interface User {
  id: number; email: string; full_name: string | null; is_admin: boolean; is_active: boolean;
  last_login_at: string | null; is_me: boolean; memberships: Membership[];
}
type Option = { value: string; label: string };
type UsersMeta = { instances: Option[]; roles: Option[] };

/** Rôle par instance (« » = aucun accès) ↔ liste envoyée à l'API. */
function toMemberships(roles: Record<string, string>) {
  return Object.entries(roles).filter(([, role]) => role).map(([id, role]) => ({ instance_id: Number(id), role }));
}

const KEY = ["users"];

function UserForm({ user, meta, onDone }: { user: User | null; meta: UsersMeta | undefined; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      email: user?.email ?? "", full_name: user?.full_name ?? "", password: "",
      is_admin: user?.is_admin ?? false, is_active: user?.is_active ?? true,
      roles: Object.fromEntries((user?.memberships ?? []).map((m) => [String(m.instance_id), m.role])) as Record<string, string>,
    },
  });
  const save = useAction(({ roles, ...values }: typeof form.values) => {
    const body = { ...values, memberships: toMemberships(roles) };
    return user ? api.patch<{ notices: Notice[] }>(`/api/v1/users/${user.id}`, body)
      : api.post<{ notices: Notice[] }>("/api/v1/users", body);
  }, { invalidate: [KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={user ? "Enregistrer" : "Créer l'utilisateur"} onCancel={onDone}
        loading={save.isPending}>
        <TextInput label="Email" type="email" required data-autofocus {...form.getInputProps("email")} />
        <TextInput label="Nom" {...form.getInputProps("full_name")} />
        <PasswordInput label="Mot de passe" required={!user} autoComplete="new-password"
          description={user ? "Laisser vide pour garder le mot de passe actuel." : undefined}
          {...form.getInputProps("password")} />
        <Switch label="Administrateur" description="Gère les utilisateurs, les instances et les intégrations."
          disabled={user?.is_me} {...form.getInputProps("is_admin", { type: "checkbox" })} />
        <Switch label="Compte actif" disabled={user?.is_me} {...form.getInputProps("is_active", { type: "checkbox" })} />
        <Stack gap={6}>
          <Text size="sm" fw={500}>Accès aux instances</Text>
          {form.values.is_admin ? <Text size="sm" c="dimmed">Administrateur : accès à toutes les instances.</Text>
            : (meta?.instances ?? []).map((inst) => (
              <Select key={inst.value} label={inst.label} size="xs" allowDeselect={false}
                data={[{ value: "", label: "Aucun accès" }, ...(meta?.roles ?? [])]}
                value={form.values.roles[inst.value] ?? ""}
                onChange={(role) => form.setFieldValue("roles", { ...form.values.roles, [inst.value]: role ?? "" })} />
            ))}
        </Stack>
      </FormBody>
    </form>
  );
}

export default function UsersPage() {
  const modal = useRouteModal("/users/", "user_id");
  const { data, isFetching } = useList<User, UsersMeta>(KEY, "/api/v1/users");
  const editing = modal.mode === "edit" ? data?.items.find((u) => u.id === modal.id) ?? null : null;
  const toggle = useAction((u: User) => api.patch<{ notices: Notice[] }>(`/api/v1/users/${u.id}`, { is_active: !u.is_active }),
    { invalidate: [KEY] });
  const remove = useAction((u: User) => api.delete<{ notices: Notice[] }>(`/api/v1/users/${u.id}`), { invalidate: [KEY] });

  const columns: GridColumn<User>[] = [
    { accessor: "email", title: "Email", sortable: true, hideable: false,
      render: (u) => <>{u.email}{u.is_me && <Text span c="dimmed" size="sm"> (vous)</Text>}</> },
    { accessor: "full_name", title: "Nom", sortable: true, render: (u) => u.full_name ?? "—" },
    { accessor: "is_admin", title: "Rôle",
      render: (u) => <StatusBadge tone={u.is_admin ? "info" : "neutral"}>{u.is_admin ? "Administrateur" : "Utilisateur"}</StatusBadge> },
    { accessor: "memberships", title: "Accès", render: (u) => u.is_admin
      ? <Text size="sm" c="dimmed">Toutes les instances</Text>
      : <Text size="sm">{u.memberships.map((m) => `${m.instance} (${m.role_label})`).join(", ") || "Aucun"}</Text> },
    { accessor: "is_active", title: "Statut",
      render: (u) => <StatusBadge tone={u.is_active ? "ok" : "neutral"}>{u.is_active ? "Actif" : "Désactivé"}</StatusBadge> },
    { accessor: "last_login_at", title: "Dernière connexion", sortable: true,
      render: (u) => <span className="lv-num">{formatDate(u.last_login_at)}</span> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (u) => (
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(u.id)}>Modifier</Button>
          {!u.is_me && <>
            <Button variant="subtle" size="compact-sm" onClick={() => toggle.mutate(u)}>
              {u.is_active ? "Désactiver" : "Réactiver"}
            </Button>
            <Button variant="subtle" size="compact-sm" color="brique"
              onClick={() => confirmAction({ title: `Supprimer l'utilisateur ${u.email} ?`,
                message: "Il ne pourra plus se connecter. Désactiver le compte suffit pour une absence.",
                confirmLabel: "Supprimer", onConfirm: () => remove.mutate(u) })}>Supprimer</Button>
          </>}
        </Group>
      ) },
  ];

  return (
    <>
      <PageHeader title="Utilisateurs" description="Les personnes qui peuvent se connecter, toutes instances confondues."
        actions={<Button onClick={modal.openNew}>Créer un utilisateur</Button>} />
      <DataGrid id="users" records={data?.items} columns={columns} fetching={isFetching}
        defaultSort={{ column: "email", direction: "asc" }} />
      <FormModal opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? `Modifier ${editing.email}` : "Créer un utilisateur"}>
        <UserForm key={editing?.id ?? "new"} user={editing} meta={data?.meta} onDone={modal.close} />
      </FormModal>
    </>
  );
}
