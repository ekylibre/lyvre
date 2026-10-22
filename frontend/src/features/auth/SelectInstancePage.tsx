// Choix de l'instance (base comptable) : POST /api/v1/session/instance, puis page demandée.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Alert, Anchor, Button, Center, Loader, Radio, Stack, Text } from "@mantine/core";
import { safeNext } from "../../api/client";
import { useLogout, useSelectInstance, useSession } from "../../api/session";
import { useGoTo } from "../../app/navigation";
import { AuthCard } from "./AuthCard";

export default function SelectInstancePage() {
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const goTo = useGoTo();
  const { data: session, isPending } = useSession();
  const select = useSelectInstance();
  const logout = useLogout();
  const [choice, setChoice] = useState<string | null>(null);

  useEffect(() => {
    if (!isPending && !session?.user) {
      goTo(`/login?next=${encodeURIComponent(`/select-instance?next=${next}`)}`, { replace: true });
    }
  }, [isPending, session, next, goTo]);

  const current = session?.instance ? String(session.instance.id) : null;
  const value = choice ?? current;

  if (isPending || !session?.user) return <Center h="100vh"><Loader /></Center>;
  return (
    <AuthCard title="Choisir une instance">
      <form onSubmit={(event) => {
        event.preventDefault();
        if (value) select.mutate(Number(value), { onSuccess: () => goTo(next, { replace: true }) });
      }}>
        <Stack>
          <Text size="sm" c="dimmed">Connecté en tant que {session.user.email}.</Text>
          {session.instances.length === 0 ? (
            <Alert color="yellow">
              Aucune instance disponible. Contactez un administrateur pour en créer une.
            </Alert>
          ) : (
            <Radio.Group value={value} onChange={setChoice} name="instance_id" label="Instance">
              <Stack gap="xs" mt="xs">
                {session.instances.map((inst) => (
                  <Radio key={inst.id} value={String(inst.id)} label={inst.label} />
                ))}
              </Stack>
            </Radio.Group>
          )}
          <Button type="submit" disabled={!value} loading={select.isPending}>Continuer</Button>
          <Anchor component="button" type="button" size="sm"
            onClick={() => logout.mutate(undefined, { onSuccess: () => goTo("/login", { replace: true }) })}>
            Se déconnecter
          </Anchor>
        </Stack>
      </form>
    </AuthCard>
  );
}
