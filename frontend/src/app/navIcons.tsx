// Icônes Lucide des menus (lot NV1, claudedocs/design_navigation.md § 5.1) : table explicite des noms de
// menu_config, pour n'embarquer que les icônes utilisées. Un nom inconnu n'affiche rien.
import type { LucideIcon } from "lucide-react";
import {
  BookOpen, BookText, Boxes, Briefcase, Building2, Calculator, CalendarClock, CalendarRange, ChartLine, ChartNoAxesColumn,
  FileChartColumn, FileInput, FileUp, FolderKanban, FolderOpen, Gauge, HandCoins, Handshake, Heart, HeartPulse, KeyRound,
  Landmark, LayoutDashboard, Link, ListTree, NotebookPen, Package, PiggyBank, Receipt, ReceiptText, Scale, ScrollText, Send,
  Settings, Settings2, ShoppingCart, Split, Sprout, Store, Tractor, TrendingUp, Users, Wallet, Warehouse, Wheat, Wrench,
} from "lucide-react";

export const NAV_ICONS: Record<string, LucideIcon> = {
  "book-open": BookOpen, "book-text": BookText, boxes: Boxes, briefcase: Briefcase, "building-2": Building2,
  calculator: Calculator, "calendar-clock": CalendarClock, "calendar-range": CalendarRange, "chart-line": ChartLine,
  "chart-no-axes-column": ChartNoAxesColumn, "file-chart-column": FileChartColumn, "file-input": FileInput, "file-up": FileUp,
  "folder-kanban": FolderKanban, "folder-open": FolderOpen, gauge: Gauge, "hand-coins": HandCoins, handshake: Handshake,
  heart: Heart, "heart-pulse": HeartPulse, "key-round": KeyRound, landmark: Landmark, "layout-dashboard": LayoutDashboard,
  link: Link, "list-tree": ListTree, "notebook-pen": NotebookPen, package: Package, "piggy-bank": PiggyBank, receipt: Receipt,
  "receipt-text": ReceiptText, scale: Scale, "scroll-text": ScrollText, send: Send, settings: Settings, "settings-2": Settings2,
  "shopping-cart": ShoppingCart, split: Split, sprout: Sprout, store: Store, tractor: Tractor, "trending-up": TrendingUp,
  users: Users, wallet: Wallet, warehouse: Warehouse, wheat: Wheat, wrench: Wrench,
};

export function NavIcon({ name, size = 18 }: { name?: string; size?: number }) {
  const Icon = name ? NAV_ICONS[name] : undefined;
  return Icon ? <Icon size={size} strokeWidth={1.75} aria-hidden /> : null;
}
