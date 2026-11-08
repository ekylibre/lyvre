// Mise en page de l'application (charte Lyvre, composant Navigation) : barre latérale
// sombre de 240 px avec la marque et les menus de menu_config (reçus avec la session),
// en-tête avec instance, recherche, notifications, thème et utilisateur ; contenu limité à 1200 px.
import type { ReactNode } from "react";
import { useLocation } from "react-router";
import {
  ActionIcon, Anchor, AppShell, Badge, Box, Burger, Divider, Group, Image, Indicator, Kbd, Menu, NavLink, ScrollArea, Stack,
  Text, Tooltip, UnstyledButton, useComputedColorScheme, useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure, useMediaQuery } from "@mantine/hooks";
import { spotlight } from "@mantine/spotlight";
import {
  ArrowLeftRight, Bot, ChevronDown, Eye, KeyRound, LogOut, Moon, PanelLeftClose, PanelLeftOpen, Search, Sparkles, Sun,
} from "lucide-react";
import symbolInverse from "../../assets/lyvre-symbole-inverse.svg";
import {
  activeUrl, useCan, useCurrentSession, useLogout, usePreferences, useSelectInstance, type NavItem, type NavMenu,
} from "../../api/session";
import { NavIcon } from "../navIcons";
import { AppLink } from "../navigation";
import { useChangelogUnseen } from "../../features/changelog/useChangelog";
import { AssistantButton } from "../../features/assistant/AssistantDrawer";
import { NotificationBell } from "./NotificationBell";
import { Wordmark } from "./Wordmark";

export { activeUrl } from "../../api/session";

/** Un sous-menu contient-il l'adresse active (pour l'ouvrir d'office) ? */
function contains(items: NavItem[], url: string | null): boolean {
  return !!url && items.some((i) => ("items" in i ? contains(i.items, url) : "url" in i && i.url === url));
}

function NavItems({ items, current, onNavigate }: { items: NavItem[]; current: string | null; onNavigate: () => void }) {
  return (
    <>
      {items.map((item, index) => {
        if ("divider" in item) return <Divider key={`d${index}`} my={4} />;
        if ("items" in item) {
          return (
            <NavLink key={item.key} label={item.label} leftSection={<NavIcon name={item.icon} />}
              defaultOpened={contains(item.items, current)} childrenOffset="sm">
              <NavItems items={item.items} current={current} onNavigate={onNavigate} />
            </NavLink>
          );
        }
        const active = item.url === current;
        return (
          <NavLink key={item.key} component={AppLink} href={item.url} label={item.label} leftSection={<NavIcon name={item.icon} />}
            active={active} aria-current={active ? "page" : undefined} onClick={onNavigate} />
        );
      })}
    </>
  );
}

function NavMenus({ menus, onNavigate }: { menus: NavMenu[]; onNavigate: () => void }) {
  const { pathname } = useLocation();
  const current = activeUrl(menus, pathname);
  return (
    <>
      {menus.map((menu) => {
        if (menu.url) {
          const active = menu.url === current;
          return (
            <NavLink key={menu.key} component={AppLink} href={menu.url} label={menu.label} leftSection={<NavIcon name={menu.icon} />}
              active={active} aria-current={active ? "page" : undefined} onClick={onNavigate} />
          );
        }
        const items = menu.items ?? [];
        return (
          <NavLink key={menu.key} label={menu.label} leftSection={<NavIcon name={menu.icon} />}
            defaultOpened={contains(items, current)} childrenOffset="sm">
            <NavItems items={items} current={current} onNavigate={onNavigate} />
          </NavLink>
        );
      })}
    </>
  );
}

/** Entrées d'un sous-menu en menu flottant (rail) : les sous-menus de 3e niveau deviennent des sections. */
function RailItems({ items, current }: { items: NavItem[]; current: string | null }) {
  return (
    <>
      {items.map((item, index) => {
        if ("divider" in item) return <Menu.Divider key={`d${index}`} />;
        if ("items" in item) {
          return (
            <div key={item.key}>
              <Menu.Label>{item.label}</Menu.Label>
              <RailItems items={item.items} current={current} />
            </div>
          );
        }
        const active = item.url === current;
        return (
          <Menu.Item key={item.key} component={AppLink} href={item.url} leftSection={<NavIcon name={item.icon} size={16} />}
            aria-current={active ? "page" : undefined} fw={active ? 600 : undefined}>
            {item.label}
          </Menu.Item>
        );
      })}
    </>
  );
}

/** Menu replié en rail (lot NV4, § 5.3) : une icône par menu, libellé en info-bulle, sous-menus flottants. */
function NavRail({ menus }: { menus: NavMenu[] }) {
  const { pathname } = useLocation();
  const current = activeUrl(menus, pathname);
  return (
    <Stack gap={4} align="center">
      {menus.map((menu) => {
        if (menu.url) {
          const active = menu.url === current;
          return (
            <Tooltip key={menu.key} label={menu.label} position="right">
              <ActionIcon component={AppLink} href={menu.url} variant="subtle" className="lv-rail-btn" aria-label={menu.label}
                data-active={active || undefined} aria-current={active ? "page" : undefined}>
                <NavIcon name={menu.icon} size={20} />
              </ActionIcon>
            </Tooltip>
          );
        }
        const items = menu.items ?? [];
        const active = contains(items, current);
        return (
          <Menu key={menu.key} position="right-start" offset={12} width={260} withinPortal>
            <Tooltip label={menu.label} position="right">
              <Menu.Target>
                <ActionIcon variant="subtle" className="lv-rail-btn" aria-label={menu.label} data-active={active || undefined}>
                  <NavIcon name={menu.icon} size={20} />
                </ActionIcon>
              </Menu.Target>
            </Tooltip>
            <Menu.Dropdown>
              <Menu.Label>{menu.label}</Menu.Label>
              <RailItems items={items} current={current} />
            </Menu.Dropdown>
          </Menu>
        );
      })}
    </Stack>
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

/** Expert-comptable : rappel permanent que l'accès est en lecture seule. */
function ReadOnlyBadge() {
  const can = useCan();
  if (can.write || !can.role) return null;
  return (
    <Tooltip label="Accès expert-comptable : vous consultez les comptes sans pouvoir les modifier.">
      <Badge variant="light" color="ardoise" leftSection={<Eye size={12} />} tt="none">Lecture seule</Badge>
    </Tooltip>
  );
}

function UserMenu() {
  const session = useCurrentSession();
  const logout = useLogout();
  const unseen = useChangelogUnseen();
  const app = session.app;
  return (
    <Menu position="bottom-end" width={240}>
      <Menu.Target>
        <UnstyledButton aria-label={unseen ? "Menu utilisateur (nouveautés)" : "Menu utilisateur"} mih={44}>
          <Indicator disabled={!unseen} color="lichen" size={8} offset={2}>
            <Group gap={4}>
              <Text size="sm" visibleFrom="sm">{session.user?.email}</Text>
              <ChevronDown size={16} />
            </Group>
          </Indicator>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item component={AppLink} href="/select-instance" leftSection={<ArrowLeftRight size={16} />}>
          Changer d'instance
        </Menu.Item>
        <Menu.Item component={AppLink} href="/password" leftSection={<KeyRound size={16} />}>
          Changer mon mot de passe
        </Menu.Item>
        <Menu.Item component={AppLink} href="/me/api-keys" leftSection={<Bot size={16} />}>
          Mes clés d'API
        </Menu.Item>
        <Menu.Item component={AppLink} href="/changelog" leftSection={<Sparkles size={16} />}
          rightSection={unseen ? <Badge size="xs" color="lichen" variant="filled">nouveau</Badge> : undefined}>
          Nouveautés
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
        {app && (
          <Menu.Label ta="center" fw={400}>
            Lyvre {app.version}{app.commit && ` · ${app.commit.slice(0, 7)}`}
          </Menu.Label>
        )}
      </Menu.Dropdown>
    </Menu>
  );
}

export function AppLayout({ children }: { children: ReactNode }) {
  const [opened, { toggle, close }] = useDisclosure();
  const session = useCurrentSession();
  const [preferences, updatePreferences] = usePreferences();
  // Rail (lot NV4) : choix mémorisé ; sur mobile, le tiroir reste en pleine largeur.
  const desktop = useMediaQuery("(min-width: 48em)", true);
  const rail = !!preferences.nav_rail && !!desktop;
  const toggleRail = () => updatePreferences({ nav_rail: !rail });
  return (
    <AppShell header={{ height: 64 }} navbar={{ width: rail ? 72 : 240, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding={0} layout="alt">
      <AppShell.Header bg="var(--lv-paper)" withBorder>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Menu" />
            <InstanceMenu />
            <ReadOnlyBadge />
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Tooltip label={<>Rechercher <Kbd size="xs">Ctrl</Kbd> + <Kbd size="xs">K</Kbd></>}>
              <ActionIcon variant="default" size={44} aria-label="Rechercher" onClick={() => spotlight.open()}>
                <Search />
              </ActionIcon>
            </Tooltip>
            {session.instance && <AssistantButton />}
            {session.instance && <NotificationBell />}
            <ColorSchemeToggle />
            <UserMenu />
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar className="lv-nav" p={rail ? "xs" : "md"}>
        <AppShell.Section>
          <Group gap="sm" px={rail ? 0 : 8} pb="lg" wrap="nowrap" justify={rail ? "center" : undefined}>
            <AppLink href="/" aria-label="Lyvre, tableau de bord">
              <Image src={symbolInverse} w={36} h={36} alt="" />
            </AppLink>
            {!rail && <Wordmark onDark />}
            <Burger opened={opened} onClick={close} hiddenFrom="sm" size="sm" color="var(--lv-on-night)"
              aria-label="Fermer le menu" ml="auto" />
          </Group>
        </AppShell.Section>
        <AppShell.Section grow component={ScrollArea}>
          {rail ? <NavRail menus={session.nav} /> : <NavMenus menus={session.nav} onNavigate={close} />}
        </AppShell.Section>
        <AppShell.Section pt="md" px={rail ? 0 : 8}>
          <Group justify={rail ? "center" : "flex-end"} mb={rail ? 0 : 4}>
            <Tooltip label={rail ? "Déplier le menu" : "Replier le menu"} position="right">
              <ActionIcon variant="subtle" className="lv-rail-btn" visibleFrom="sm" onClick={toggleRail}
                aria-label={rail ? "Déplier le menu" : "Replier le menu"} aria-pressed={rail}>
                {rail ? <PanelLeftOpen size={20} aria-hidden /> : <PanelLeftClose size={20} aria-hidden />}
              </ActionIcon>
            </Tooltip>
          </Group>
          {!rail && <Anchor href="/about" className="lv-nav-foot" underline="never" c="inherit">À PROPOS · LOGICIEL LIBRE · AGPL-3.0</Anchor>}
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main bg="var(--lv-paper)">
        <Box maw={1200} mx="auto" px={{ base: "md", md: 48 }} py={{ base: "md", md: "lg" }}>{children}</Box>
      </AppShell.Main>
    </AppShell>
  );
}
