// Action courante qui a besoin d'une intégration désactivée (envoyer un email sans SMTP) : le bouton
// reste visible, le clic ouvre cette fenêtre au lieu de lancer l'action. Même fenêtre si l'API répond
// `integration_required` (état périmé, écran contourné).
import { Anchor, Button, Group, Stack, Text } from "@mantine/core";
import { modals } from "@mantine/modals";
import { useCan, useIntegration } from "../api/session";
import { integrationLabel } from "../features/integrations/catalog";

function RequiredContent({ service, message, close }: { service: string; message: string; close: () => void }) {
  const can = useCan();
  return (
    <Stack>
      <Text size="sm">{message}</Text>
      <Group justify="flex-end">
        {can.instanceAdmin
          ? <Button component="a" href={`/configuration/integrations/${service}`} onClick={close}>Activer l'intégration</Button>
          : <Text size="sm" c="dimmed">Contactez un administrateur de l'instance pour l'activer.</Text>}
        <Anchor component="button" size="sm" onClick={close}>Fermer</Anchor>
      </Group>
    </Stack>
  );
}

export function openIntegrationRequired(service: string, message?: string) {
  const label = integrationLabel(service);
  const id = modals.open({
    title: `Intégration ${label} désactivée`,
    children: <RequiredContent service={service} close={() => modals.close(id)}
      message={message ?? `Cette action nécessite l'intégration ${label}, désactivée.`} />,
  });
}

/** `guard(fn)` : `fn` si l'intégration est activée, sinon la fenêtre « intégration nécessaire ».
 * `enabled` sert à ne griser le bouton (non configurée) que pour une intégration activée. */
export function useIntegrationGuard(service: string, action: string) {
  const enabled = useIntegration(service);
  const guard = <A extends unknown[]>(fn: (...args: A) => void) => (...args: A) => {
    if (enabled) fn(...args);
    else openIntegrationRequired(service, `${action} nécessite l'intégration ${integrationLabel(service)}, désactivée.`);
  };
  return { enabled, guard };
}
