import type { ReactNode } from "react";
import { Group, Stack, Text, Title } from "@mantine/core";

/** Titre d'écran, sous-titre et actions (boutons à droite). */
export function PageHeader({ title, description, actions }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode;
}) {
  return (
    <Group justify="space-between" align="flex-start" mb="md" gap="sm">
      <Stack gap={2}>
        <Title order={1} size="h2">{title}</Title>
        {description && <Text c="dimmed" size="sm">{description}</Text>}
      </Stack>
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  );
}
