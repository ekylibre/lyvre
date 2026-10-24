// Mot de passe oublié : l'adresse du compte reçoit un lien de réinitialisation (valable une heure).
// La réponse est la même que le compte existe ou non.
import { useState } from "react";
import { Alert, Anchor, Button, Stack, Text, TextInput } from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { AppLink } from "../../app/navigation";
import { AuthCard } from "./AuthCard";

type Notices = { notices: { level: string; message: string }[] };

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const send = useMutation<Notices, ApiError, string>({
    mutationFn: (value) => api.post<Notices>("/api/v1/session/password-forgot", { email: value }, { redirect: false }),
    meta: { silent: true },
  });
  return (
    <AuthCard title="Mot de passe oublié">
      {send.isSuccess ? (
        <Stack>
          <Alert color="lichen" role="status">{send.data.notices[0]?.message}</Alert>
          <Anchor component={AppLink} href="/login" size="sm" ta="center">Retour à la connexion</Anchor>
        </Stack>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); if (email.trim()) send.mutate(email.trim()); }}>
          <Stack>
            <Text size="sm">Indiquez l'adresse e-mail de votre compte : vous recevrez un lien pour choisir un nouveau
              mot de passe.</Text>
            {send.error && <Alert color="red" role="alert">{send.error.message}</Alert>}
            <TextInput label="Email" type="email" autoComplete="username" autoFocus required value={email}
              onChange={(e) => setEmail(e.currentTarget.value)} />
            <Button type="submit" loading={send.isPending}>Recevoir le lien</Button>
            <Anchor component={AppLink} href="/login" size="sm" ta="center">Retour à la connexion</Anchor>
          </Stack>
        </form>
      )}
    </AuthCard>
  );
}
