import type { ReactNode } from "react";
import { Group, Stack, Text, Title } from "@mantine/core";
import { useNavEntry } from "../api/session";
import { IconTile } from "./IconTile";

/** Titre d'écran, sous-titre et actions (boutons à droite) ; `icon` à gauche du titre (logo).
 * Sans `icon`, la pastille de l'entrée de menu de la page (lot NV4) ; `icon={null}` n'en met aucune. */
export function PageHeader({ title, description, actions, icon }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; icon?: ReactNode;
}) {
  const entry = useNavEntry();
  const shown = icon !== undefined ? icon
    : entry ? <IconTile icon={entry.icon} pictogram={entry.pictogram} /> : null;
  const heading = (
    <Stack gap={2}>
      <Title order={1}>{title}</Title>
      {description && <Text c="dimmed" size="sm" component={typeof description === "string" ? "p" : "div"}>{description}</Text>}
    </Stack>
  );
  return (
    <Group justify="space-between" align="flex-start" mb="md" gap="sm">
      {shown ? <Group gap="sm" align="center" wrap="nowrap">{shown}{heading}</Group> : heading}
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  );
}
