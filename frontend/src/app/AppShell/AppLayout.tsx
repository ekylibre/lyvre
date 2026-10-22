// Mise en page de l'application (charte Lyvre, composant Navigation) : barre latérale
// sombre de 240 px avec la marque et les menus de menu_config (reçus avec la session),
// en-tête avec instance, recherche, notifications, thème et utilisateur ; contenu limité à 1200 px.
import type { ReactNode } from "react";
import { useLocation } from "react-router";
import {
  ActionIcon, AppShell, Box, Burger, Divider, Group, Image, Kbd, Menu, NavLink, ScrollArea, Text,
  Tooltip, UnstyledButton, useComputedColorScheme, useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { spotlight } from "@mantine/spotlight";
import { ArrowLeftRight, ChevronDown, LogOut, Moon, Search, Sun } from "lucide-react";
import symbolInverse from "../../assets/lyvre-symbole-inverse.svg";
import {
  useCurrentSession, useLogout, usePreferences, useSelectInstance, type NavMenu,
} from "../../api/session";
import { AppLink } from "../navigation";
import { NotificationBell } from "./NotificationBell";
import { Wordmark } from "./Wordmark";

const pathOf = (url: string) => new URL(url, window.location.origin).pathname.replace(/\/$/, "") || "/";

/** URL du menu qui correspond le mieux à la page (préfixe le plus long : /entities/members
 * l'emporte sur /entities/ pour la page des adhérents). */
export function activeUrl(menus: NavMenu[], pathname: string): string | null {
  const urls = menus.flatMap((m) => [m.url, ...(m.items ?? []).map((i) => ("url" in i ? i.url : undefined))])
    .filter((u): u is string => !!u);
  const current = pathname.replace(/\/$/, "") || "/";
  const matches = urls.filter((u) => {
    const path = pathOf(u);
    return path === "/" ? current === "/" : current === path || current.startsWith(`${path}/`);
  });
  return matches.sort((a, b) => pathOf(b).length - pathOf(a).length)[0] ?? null;
}

function NavMenus({ menus, onNavigate }: { menus: NavMenu[]; onNavigate: () => void }) {
  const { pathname } = useLocation();
  const current = activeUrl(menus, pathname);
  const isActive = (url: string) => url === current;
  return (
    <>
      {menus.map((menu) => {
        if (menu.url) {
          const active = isActive(menu.url);
          return (
            <NavLink key={menu.key} component={AppLink} href={menu.url} label={menu.label}
              active={active} aria-current={active ? "page" : undefined} onClick={onNavigate} />
          );
        }
        const items = menu.items ?? [];
        const opened = items.some((i) => "url" in i && isActive(i.url));
        return (
          <NavLink key={menu.key} label={menu.label} defaultOpened={opened} childrenOffset="sm">
            {items.map((item, index) => {
              if ("divider" in item) return <Divider key={`d${index}`} my={4} />;
              const active = isActive(item.url);
              return (
                <NavLink key={item.key} component={AppLink} href={item.url} label={item.label}
                  active={active} aria-current={active ? "page" : undefined} onClick={onNavigate} />
              );
            })}
          </NavLink>
        );
      })}
    </>
  );
}

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme("light");
  const [, updatePreferences] = usePreferences();
  const next = computed === "dark" ? "light" : "dark";
  return (
    <Tooltip label={next === "dark" ? "Passer en thème sombre" : "Passer en thème clair"}>
      <ActionIcon variant="default" size={44} aria-label="Changer de thème"
        onClick={() => {
          setColorScheme(next);
          updatePreferences({ color_scheme: next });
        }}>
        {computed === "dark" ? <Sun /> : <Moon />}
      </ActionIcon>
    </Tooltip>
  );
}

function InstanceMenu() {
  const session = useCurrentSession();
  const select = useSelectInstance();
  if (!session.instance) return null;
  const others = session.instances.filter((i) => i.id !== session.instance!.id);
  if (!others.length) return <Text fw={600}>{session.instance.label}</Text>;
  return (
    <Menu position="bottom-start">
      <Menu.Target>
        <UnstyledButton aria-label="Changer d'instance" mih={44}>
          <Group gap={4}>
            <Text fw={600}>{session.instance.label}</Text>
            <ChevronDown size={16} />
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Changer d'instance</Menu.Label>
        {others.map((inst) => (
          <Menu.Item key={inst.id}
            onClick={() => select.mutate(inst.id, { onSuccess: () => window.location.assign("/") })}>
            {inst.label}
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}

function UserMenu() {
  const session = useCurrentSession();
  const logout = useLogout();
  return (
    <Menu position="bottom-end" width={240}>
      <Menu.Target>
        <UnstyledButton aria-label="Menu utilisateur" mih={44}>
          <Group gap={4}>
            <Text size="sm" visibleFrom="sm">{session.user?.email}</Text>
            <ChevronDown size={16} />
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item component={AppLink} href="/select-instance" leftSection={<ArrowLeftRight size={16} />}>
          Changer d'instance
        </Menu.Item>
        {session.admin_links.length > 0 && <Menu.Divider />}
        {session.admin_links.map((link) => (
          <Menu.Item key={link.url} component={AppLink} href={link.url}>{link.label}</Menu.Item>
        ))}
        <Menu.Divider />
        <Menu.Item leftSection={<LogOut size={16} />}
          onClick={() => logout.mutate(undefined, { onSuccess: () => window.location.assign("/login") })}>
          Se déconnecter
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

export function AppLayout({ children }: { children: ReactNode }) {
  const [opened, { toggle, close }] = useDisclosure();
  const session = useCurrentSession();
  return (
    <AppShell header={{ height: 64 }} navbar={{ width: 240, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding={0} layout="alt">
      <AppShell.Header bg="var(--lv-paper)" withBorder>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Menu" />
            <InstanceMenu />
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Tooltip label={<>Rechercher <Kbd size="xs">Ctrl</Kbd> + <Kbd size="xs">K</Kbd></>}>
              <ActionIcon variant="default" size={44} aria-label="Rechercher" onClick={() => spotlight.open()}>
                <Search />
              </ActionIcon>
            </Tooltip>
            {session.instance && <NotificationBell />}
            <ColorSchemeToggle />
            <UserMenu />
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar className="lv-nav" p="md">
        <AppShell.Section>
          <Group gap="sm" px={8} pb="lg" wrap="nowrap">
            <AppLink href="/" aria-label="Lyvre, tableau de bord">
              <Image src={symbolInverse} w={36} h={36} alt="" />
            </AppLink>
            <Wordmark onDark />
            <Burger opened={opened} onClick={close} hiddenFrom="sm" size="sm" color="var(--lv-on-night)"
              aria-label="Fermer le menu" ml="auto" />
          </Group>
        </AppShell.Section>
        <AppShell.Section grow component={ScrollArea}>
          <NavMenus menus={session.nav} onNavigate={close} />
        </AppShell.Section>
        <AppShell.Section pt="md" px={8}>
          <Text className="lv-nav-foot">LOGICIEL LIBRE · AGPL-3.0 · AUTO-HÉBERGÉ</Text>
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main bg="var(--lv-paper)">
        <Box maw={1200} mx="auto" px={{ base: "md", md: 48 }} py={{ base: "md", md: "lg" }}>{children}</Box>
      </AppShell.Main>
    </AppShell>
  );
}
