import type { ReactNode } from "react";
import { Center, Group, Image, Paper, Stack, Text, Title } from "@mantine/core";
import logo from "../../assets/logo.svg";
import { APP_NAME } from "../../app/theme";

/** Cadre des pages nues (connexion, choix d'instance). */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Center mih="100vh" p="md" bg="var(--mantine-color-body)">
      <Stack w="100%" maw={420} gap="lg">
        <Group gap="sm" justify="center">
          <Image src={logo} w={36} h={36} alt="" />
          <Text fw={700} size="xl">{APP_NAME}</Text>
        </Group>
        <Paper withBorder shadow="sm" p="xl" radius="md">
          <Title order={2} size="h3" mb="md">{title}</Title>
          {children}
        </Paper>
      </Stack>
    </Center>
  );
}
