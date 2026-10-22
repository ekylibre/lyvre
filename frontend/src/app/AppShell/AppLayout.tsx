// Mise en page de l'application : en-tête (instance, thème, utilisateur) et menus de
// menu_config (reçus avec la session, filtrés par plan comptable et droits).
import type { ReactNode } from "react";
import { useLocation } from "react-router";
import {
  ActionIcon, AppShell, Burger, Divider, Group, Image, Kbd, Menu, NavLink, ScrollArea, Text,
  Tooltip, UnstyledButton, useComputedColorScheme, useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { spotlight } from "@mantine/spotlight";
import {
  IconChevronDown, IconLogout, IconMoon, IconSearch, IconSun, IconSwitchHorizontal,
} from "@tabler/icons-react";
import logo from "../../assets/logo.svg";
import {
  useCurrentSession, useLogout, usePreferences, useSelectInstance, type NavMenu,
} from "../../api/session";
import { AppLink } from "../navigation";
import { APP_NAME } from "../theme";

/** L'URL du menu correspond-elle à la page affichée ? */
function isActive(url: string, pathname: string): boolean {
  const path = new URL(url, window.location.origin).pathname;
  return path === "/" ? pathname === "/" : pathname.startsWith(path.replace(/\/$/, ""));
}

function NavMenus({ menus, onNavigate }: { menus: NavMenu[]; onNavigate: () => void }) {
  const { pathname } = useLocation();
  return (
    <>
      {menus.map((menu) => {
        if (menu.url) {
          return (
            <NavLink key={menu.key} component={AppLink} href={menu.url} label={menu.label}
              active={isActive(menu.url, pathname)} onClick={onNavigate} />
          );
        }
        const items = menu.items ?? [];
        const opened = items.some((i) => "url" in i && isActive(i.url, pathname));
        return (
          <NavLink key={menu.key} label={menu.label} defaultOpened={opened} childrenOffset="md">
            {items.map((item, index) =>
              "divider" in item ? (
                <Divider key={`d${index}`} my={4} />
              ) : (
                <NavLink key={item.key} component={AppLink} href={item.url} label={item.label}
                  active={isActive(item.url, pathname)} onClick={onNavigate} />
              ))}
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
    <Tooltip label={next === "dark" ? "Thème sombre" : "Thème clair"}>
      <ActionIcon variant="default" size="lg" aria-label="Changer de thème"
        onClick={() => {
          setColorScheme(next);
          updatePreferences({ color_scheme: next });
        }}>
        {computed === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}

function InstanceMenu() {
  const session = useCurrentSession();
  const select = useSelectInstance();
  if (!session.instance) return null;
  const others = session.instances.filter((i) => i.id !== session.instance!.id);
  if (!others.length) return <Text fw={500}>{session.instance.label}</Text>;
  return (
    <Menu position="bottom-start">
      <Menu.Target>
        <UnstyledButton aria-label="Changer d'instance">
          <Group gap={4}>
            <Text fw={500}>{session.instance.label}</Text>
            <IconChevronDown size={14} />
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
    <Menu position="bottom-end" width={220}>
      <Menu.Target>
        <UnstyledButton aria-label="Menu utilisateur">
          <Group gap={4}>
            <Text size="sm" visibleFrom="sm">{session.user?.email}</Text>
            <IconChevronDown size={14} />
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item component={AppLink} href="/select-instance" leftSection={<IconSwitchHorizontal size={16} />}>
          Changer d'instance
        </Menu.Item>
        {session.admin_links.length > 0 && <Menu.Divider />}
        {session.admin_links.map((link) => (
          <Menu.Item key={link.url} component={AppLink} href={link.url}>{link.label}</Menu.Item>
        ))}
        <Menu.Divider />
        <Menu.Item leftSection={<IconLogout size={16} />}
          onClick={() => logout.mutate(undefined, { onSuccess: () => window.location.assign("/login") })}>
          Déconnexion
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

export function AppLayout({ children }: { children: ReactNode }) {
  const [opened, { toggle, close }] = useDisclosure();
  const session = useCurrentSession();
  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 250, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Menu" />
            <AppLink href="/" aria-label="Accueil">
              <Image src={logo} w={28} h={28} alt="" />
            </AppLink>
            <Text fw={700} visibleFrom="sm">{APP_NAME}</Text>
            <InstanceMenu />
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Tooltip label={<>Rechercher <Kbd size="xs">Ctrl</Kbd> + <Kbd size="xs">K</Kbd></>}>
              <ActionIcon variant="default" size="lg" aria-label="Rechercher" onClick={() => spotlight.open()}>
                <IconSearch size={18} />
              </ActionIcon>
            </Tooltip>
            <ColorSchemeToggle />
            <UserMenu />
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        <ScrollArea>
          <NavMenus menus={session.nav} onNavigate={close} />
        </ScrollArea>
      </AppShell.Navbar>
      <AppShell.Main>{children}</AppShell.Main>
    </AppShell>
  );
}
