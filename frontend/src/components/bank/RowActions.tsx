// Actions d'une ligne (lot TX2) : la première action est visible, les autres dans le menu « … ».
import { ActionIcon, Button, Group, Menu } from "@mantine/core";
import { Ellipsis } from "lucide-react";
import { AppLink } from "../../app/navigation";

export interface RowAction {
  key: string;
  label: string;
  title?: string;
  href?: string;
  onClick?: () => void;
  loading?: boolean;
}

export function RowActions({ actions, label }: { actions: RowAction[]; label: string }) {
  if (!actions.length) return null;
  const [primary, ...others] = actions;
  return (
    <Group gap={4} wrap="nowrap" justify="flex-end">
      {primary.href
        ? <Button size="compact-sm" variant="light" component={AppLink} href={primary.href} title={primary.title}>{primary.label}</Button>
        : <Button size="compact-sm" variant="light" onClick={primary.onClick} loading={primary.loading} title={primary.title}>{primary.label}</Button>}
      {others.length > 0 && (
        <Menu position="bottom-end" withinPortal>
          <Menu.Target>
            <ActionIcon variant="subtle" color="gray" aria-label={`Autres actions — ${label}`}><Ellipsis size={16} /></ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            {others.map((a) => a.href
              ? <Menu.Item key={a.key} component={AppLink} href={a.href} title={a.title}>{a.label}</Menu.Item>
              : <Menu.Item key={a.key} onClick={a.onClick} title={a.title}>{a.label}</Menu.Item>)}
          </Menu.Dropdown>
        </Menu>
      )}
    </Group>
  );
}
