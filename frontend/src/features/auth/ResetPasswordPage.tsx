// Nouveau mot de passe depuis le lien reçu par e-mail (`?token=`) : lien vérifié d'abord (expiré ou déjà
// utilisé : en demander un autre), puis connexion avec le nouveau mot de passe.
import { useState } from "react";
import { useSearchParams } from "react-router";
import { Alert, Anchor, Button, Center, Loader, PasswordInput, Stack, Text } from "@mantine/core";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { AppLink, useGoTo } from "../../app/navigation";
import { AuthCard } from "./AuthCard";

const MIN = 8;

export default function ResetPasswordPage() {
  const token = useSearchParams()[0].get("token") ?? "";
  const goTo = useGoTo();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const check = useQuery({ queryKey: ["password-reset", token], retry: false, staleTime: Infinity,
    queryFn: () => api.post<{ valid: boolean; email: string | null }>("/api/v1/session/password-reset/check", { token }, { redirect: false }) });
  const save = useMutation<unknown, ApiError>({
    mutationFn: () => api.post("/api/v1/session/password-reset", { token, password }, { redirect: false }),
    meta: { silent: true },
    onSuccess: () => goTo("/login?reset=1", { replace: true }),
    onError: (e) => setError(e.message),
  });
  const submit = () => {
    if (password.length < MIN) setError(`${MIN} caractères au moins.`);
    else if (password !== confirm) setError("Les deux saisies ne sont pas identiques.");
    else { setError(null); save.mutate(); }
  };
  if (check.isLoading) return <Center h={300}><Loader /></Center>;
  if (!check.data?.valid) {
    return (
      <AuthCard title="Lien expiré">
        <Stack>
          <Text size="sm">Ce lien est invalide, expiré ou a déjà servi. Demandez-en un nouveau.</Text>
          <Button component={AppLink} href="/password/forgot">Recevoir un nouveau lien</Button>
          <Anchor component={AppLink} href="/login" size="sm" ta="center">Retour à la connexion</Anchor>
        </Stack>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Nouveau mot de passe">
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Stack>
          <Text size="sm">Compte : <b>{check.data.email}</b></Text>
          {error && <Alert color="red" role="alert">{error}</Alert>}
          <PasswordInput label="Nouveau mot de passe" description={`${MIN} caractères au moins`} autoComplete="new-password"
            autoFocus required value={password} onChange={(e) => setPassword(e.currentTarget.value)} />
          <PasswordInput label="Confirmation" autoComplete="new-password" required value={confirm}
            onChange={(e) => setConfirm(e.currentTarget.value)} />
          <Button type="submit" loading={save.isPending}>Enregistrer le mot de passe</Button>
        </Stack>
      </form>
    </AuthCard>
  );
}
