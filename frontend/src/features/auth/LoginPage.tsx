// Connexion (FM5) : POST /api/v1/session/login, puis instance ou page demandée (`next`).
import { useEffect } from "react";
import { useSearchParams } from "react-router";
import { Alert, Anchor, Button, PasswordInput, Stack, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { safeNext } from "../../api/client";
import { useLogin, useSession, type Session } from "../../api/session";
import { useGoTo } from "../../app/navigation";
import { AuthCard } from "./AuthCard";

/** Après connexion : choisir l'instance s'il n'y en a pas, sinon la page demandée. */
export function afterLogin(session: Session, next: string): string {
  if (!session.instance) return `/select-instance?next=${encodeURIComponent(next)}`;
  return next;
}

export default function LoginPage() {
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const goTo = useGoTo();
  const { data: session } = useSession();
  const login = useLogin();
  const form = useForm({
    mode: "uncontrolled",
    initialValues: { email: "", password: "" },
    validate: {
      email: (v) => (v.trim() ? null : "Email obligatoire."),
      password: (v) => (v ? null : "Mot de passe obligatoire."),
    },
  });

  // Déjà connecté : la page de connexion ne sert à rien.
  useEffect(() => {
    if (session?.user && !login.isPending) goTo(afterLogin(session, next), { replace: true });
  }, [session, next, goTo, login.isPending]);

  return (
    <AuthCard title="Connexion">
      <form onSubmit={form.onSubmit((values) => login.mutate(values, {
        onSuccess: (s) => goTo(afterLogin(s, next), { replace: true }),
      }))}>
        <Stack>
          {login.error && <Alert color="red" role="alert">{login.error.message}</Alert>}
          <TextInput label="Email" type="email" autoComplete="username" autoFocus required
            key={form.key("email")} {...form.getInputProps("email")} />
          <PasswordInput label="Mot de passe" autoComplete="current-password" required
            key={form.key("password")} {...form.getInputProps("password")} />
          <Button type="submit" loading={login.isPending}>Se connecter</Button>
          <Anchor href="/about" size="sm" ta="center">Découvrir Lyvre et ses fonctionnalités</Anchor>
        </Stack>
      </form>
    </AuthCard>
  );
}
