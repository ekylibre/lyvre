import type { ReactNode } from "react";
import { Center, Group, Image, Paper, Stack, Text, Title, useComputedColorScheme } from "@mantine/core";
import symbol from "../../assets/lyvre-symbole.svg";
import symbolInverse from "../../assets/lyvre-symbole-inverse.svg";
import { Wordmark } from "../../app/AppShell/Wordmark";

/** Cadre des pages nues (connexion, choix d'instance). */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  const dark = useComputedColorScheme("light") === "dark";
  return (
    <Center mih="100vh" p="md" bg="var(--lv-paper)">
      <Stack w="100%" maw={420} gap="lg">
        <Group gap="sm" justify="center">
          <Image src={dark ? symbolInverse : symbol} w={56} h={56} alt="" />
          <Wordmark />
        </Group>
        <Text ta="center" c="dimmed" size="sm" mt={-12}>La compta libre, sobre et souveraine.</Text>
        <Paper p="lg">
          <Title order={1} size="h2" mb="md">{title}</Title>
          {children}
        </Paper>
      </Stack>
    </Center>
  );
}
