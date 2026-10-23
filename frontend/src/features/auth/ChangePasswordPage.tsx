// Choix du mot de passe : obligatoire après un mot de passe initial ou fixé par un administrateur
// (`must_change_password`, garde serveur), possible à tout moment depuis le menu utilisateur.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Alert, Anchor, Button, Center, Loader, PasswordInput, Stack, Text } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useQueryClient } from "@tanstack/react-query";
import { api, safeNext } from "../../api/client";
import { applyApiError } from "../../components/ApiForm";
import { SESSION_KEY, useLogout, useSession, type Session } from "../../api/session";
import { useGoTo } from "../../app/navigation";
import { AuthCard } from "./AuthCard";

export const MIN_PASSWORD = 8;

export default function ChangePasswordPage() {
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const goTo = useGoTo();
  const client = useQueryClient();
  const { data: session, isPending } = useSession();
  const logout = useLogout();
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const form = useForm({
    initialValues: { current_password: "", new_password: "", confirm: "" },
    validate: {
      current_password: (v) => (v ? null : "Mot de passe actuel obligatoire."),
      new_password: (v) => (v.length >= MIN_PASSWORD ? null : `${MIN_PASSWORD} caractères au moins.`),
      confirm: (v, values) => (v === values.new_password ? null : "Les deux saisies diffèrent."),
    },
  });

  useEffect(() => {
    if (!isPending && !session?.user) goTo(`/login?next=${encodeURIComponent("/password")}`, { replace: true });
  }, [isPending, session, goTo]);

  if (isPending || !session?.user) return <Center h="100vh"><Loader /></Center>;
  const required = session.user.must_change_password;

  const submit = form.onSubmit(async ({ current_password, new_password }) => {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.post<Session>("/api/v1/me/password", { current_password, new_password }, { redirect: false });
      client.setQueryData(SESSION_KEY, updated);
      goTo(next, { replace: true });
    } catch (e) {
      setError(applyApiError(form, e));
    } finally {
      setSaving(false);
    }
  });

  return (
    <AuthCard title="Choisissez votre mot de passe">
      <form onSubmit={submit}>
        <Stack>
          <Text size="sm" c="dimmed">
            {required
              ? `Connecté en tant que ${session.user.email} avec un mot de passe transmis par un administrateur : choisissez le vôtre pour continuer.`
              : `Compte ${session.user.email}.`}
          </Text>
          {error && <Alert color="red" role="alert">{error}</Alert>}
          <PasswordInput label="Mot de passe actuel" autoComplete="current-password" required data-autofocus
            {...form.getInputProps("current_password")} />
          <PasswordInput label="Nouveau mot de passe" autoComplete="new-password" required
            description={`${MIN_PASSWORD} caractères au moins, différent de l'actuel.`} {...form.getInputProps("new_password")} />
          <PasswordInput label="Confirmation" autoComplete="new-password" required {...form.getInputProps("confirm")} />
          <Button type="submit" loading={saving}>Enregistrer le mot de passe</Button>
          {required
            ? <Anchor component="button" type="button" size="sm"
              onClick={() => logout.mutate(undefined, { onSuccess: () => goTo("/login", { replace: true }) })}>
              Se déconnecter
            </Anchor>
            : <Anchor component="button" type="button" size="sm" onClick={() => goTo(next, { replace: true })}>Annuler</Anchor>}
        </Stack>
      </form>
    </AuthCard>
  );
}
