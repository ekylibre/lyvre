// Lignes « utilisateur + rôle » d'une instance à créer : compte existant ou nouveau compte avec
// mot de passe initial (à changer à la première connexion). Erreurs serveur `members.<i>.<champ>`.
import { Alert, Anchor, Button, Group, Paper, PasswordInput, SegmentedControl, Select, Stack, Text, TextInput } from "@mantine/core";
import type { UseFormReturnType } from "@mantine/form";
import { Plus } from "lucide-react";
import { knownAccount, lacksAdmin, newRow, ROLE_HELP, userChoices, type MemberRow, type RoleOption, type UserOption } from "./members";

type WithMembers = { members: MemberRow[] };

export function MembersEditor<T extends WithMembers>({ form, users, roles }: {
  form: UseFormReturnType<T>; users: UserOption[]; roles: RoleOption[];
}) {
  const rows = form.getValues().members;
  // Mantine form : chemins de liste typés de façon lâche, d'où ces petites aides.
  const path = (i: number, field: keyof MemberRow) => `members.${i}.${field}`;
  const set = (i: number, field: keyof MemberRow, value: unknown) => form.setFieldValue(path(i, field) as never, value as never);
  const choices = userChoices(users);
  return (
    <Stack gap="xs">
      <div>
        <Text size="sm" fw={500}>Utilisateurs et rôles</Text>
        <Text size="xs" c="dimmed">
          Facultatif : sans ligne, seuls les administrateurs globaux accèdent à l'instance. Un nouveau compte reçoit un mot de
          passe initial que vous lui transmettez ; il le changera à sa première connexion.
        </Text>
      </div>
      {rows.map((row, i) => {
        const taken = new Set(rows.filter((r, j) => j !== i && r.kind === "existing" && r.user_id).map((r) => r.user_id));
        const known = row.kind === "new" ? knownAccount(users, row.email) : undefined;
        return (
          <Paper key={i} p="sm" withBorder>
            <Stack gap="xs">
              <Group justify="space-between" wrap="nowrap">
                <SegmentedControl size="xs" value={row.kind} aria-label={`Ligne ${i + 1} : type de compte`}
                  data={[{ value: "existing", label: "Compte existant" }, { value: "new", label: "Nouveau compte" }]}
                  onChange={(kind) => set(i, "kind", kind)} />
                <Button variant="subtle" color="brique" size="compact-sm" aria-label={`Retirer la ligne ${i + 1}`}
                  onClick={() => form.removeListItem("members" as never, i)}>Retirer</Button>
              </Group>
              {row.kind === "existing" ? (
                <Select label="Utilisateur" placeholder="Nom ou email" searchable nothingFoundMessage="Aucun compte"
                  data={choices.filter((c) => !taken.has(c.value))} {...form.getInputProps(path(i, "user_id"))} />
              ) : (
                <>
                  <Group grow align="flex-start">
                    <TextInput label="Email" type="email" required {...form.getInputProps(path(i, "email"))} />
                    <TextInput label="Nom" {...form.getInputProps(path(i, "full_name"))} />
                  </Group>
                  {known && (
                    <Text size="xs" c="dimmed">
                      Un compte existe avec cet email.{" "}
                      <Anchor component="button" type="button" size="xs" onClick={() => {
                        set(i, "kind", "existing"); set(i, "user_id", String(known.id));
                      }}>Utiliser ce compte</Anchor>
                    </Text>
                  )}
                  <PasswordInput label="Mot de passe initial" required autoComplete="new-password"
                    description="8 caractères au moins, à transmettre à la personne." {...form.getInputProps(path(i, "password"))} />
                </>
              )}
              <Select label="Rôle" data={roles} allowDeselect={false} description={ROLE_HELP[row.role]}
                {...form.getInputProps(path(i, "role"))} />
            </Stack>
          </Paper>
        );
      })}
      {lacksAdmin(rows) && (
        <Alert color="paille" variant="light">
          Aucun administrateur parmi ces utilisateurs : seuls les administrateurs globaux pourront gérer les accès de l'instance.
        </Alert>
      )}
      <Group>
        <Button variant="default" size="compact-sm" leftSection={<Plus size={14} />}
          onClick={() => form.insertListItem("members" as never, newRow(rows.length) as never)}>Ajouter un utilisateur</Button>
      </Group>
    </Stack>
  );
}
