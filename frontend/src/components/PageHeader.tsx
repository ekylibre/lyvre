import type { ReactNode } from "react";
import { Group, Stack, Text, Title } from "@mantine/core";

/** Titre d'écran, sous-titre et actions (boutons à droite) ; `icon` à gauche du titre (logo). */
export function PageHeader({ title, description, actions, icon }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; icon?: ReactNode;
}) {
  const heading = (
    <Stack gap={2}>
      <Title order={1}>{title}</Title>
      {description && <Text c="dimmed" size="sm">{description}</Text>}
    </Stack>
  );
  return (
    <Group justify="space-between" align="flex-start" mb="md" gap="sm">
      {icon ? <Group gap="sm" align="center" wrap="nowrap">{icon}{heading}</Group> : heading}
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  );
}
