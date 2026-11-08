// Icônes Lucide (lot NV1, claudedocs/design_navigation.md § 5.1) : table explicite des noms de menu_config et des
// catégories de calculettes, pour n'embarquer que les icônes utilisées. Un nom inconnu n'affiche rien.
import type { LucideIcon } from "lucide-react";
import {
  ArchiveRestore, Banknote, BookOpen, BookUser, Boxes, Briefcase, Building, Building2, Calculator, CalendarClock, CalendarRange,
  ChartLine, ChartNoAxesColumn, Clock, Coins, Contact, CreditCard, Droplets, FileChartColumn, FileChartLine, FileClock,
  FileCog, FileHeart, FileInput, FilePenLine, FileText, FileUp, FolderKanban, FolderOpen, Gauge, GitCompareArrows, HandCoins,
  Handshake, Heart, HeartPulse, History, IdCard, KeyRound, Landmark, LayoutDashboard, ListChecks, ListFilter, ListTree,
  Megaphone, NotebookPen, Package, Percent, PiggyBank, Plug, Receipt, ReceiptEuro, ReceiptText, Recycle, Repeat,
  Repeat2, Ruler, Scale, ScrollText, Send, Settings, Settings2, ShieldCheck, ShoppingBag, ShoppingCart, Split, Sprout,
  Store, Tags, Tractor, TrendingUp, Users, Wallet, Warehouse, Wrench, Zap,
} from "lucide-react";

export const NAV_ICONS: Record<string, LucideIcon> = {
  "archive-restore": ArchiveRestore, banknote: Banknote, "book-open": BookOpen, "book-user": BookUser, boxes: Boxes, briefcase: Briefcase,
  building: Building, "building-2": Building2, calculator: Calculator, "calendar-clock": CalendarClock,
  "calendar-range": CalendarRange, "chart-line": ChartLine, "chart-no-axes-column": ChartNoAxesColumn, clock: Clock,
  coins: Coins, contact: Contact, "credit-card": CreditCard, droplets: Droplets, "file-chart-column": FileChartColumn,
  "file-chart-line": FileChartLine, "file-clock": FileClock, "file-cog": FileCog, "file-heart": FileHeart,
  "file-input": FileInput, "file-pen-line": FilePenLine, "file-text": FileText, "file-up": FileUp,
  "folder-kanban": FolderKanban, "folder-open": FolderOpen, gauge: Gauge, "git-compare-arrows": GitCompareArrows, "hand-coins": HandCoins,
  handshake: Handshake, heart: Heart, "heart-pulse": HeartPulse, history: History, "id-card": IdCard,
  "key-round": KeyRound, landmark: Landmark, "layout-dashboard": LayoutDashboard, "list-checks": ListChecks,
  "list-filter": ListFilter, "list-tree": ListTree, megaphone: Megaphone, "notebook-pen": NotebookPen,
  package: Package, percent: Percent, "piggy-bank": PiggyBank, plug: Plug, receipt: Receipt,
  "receipt-euro": ReceiptEuro, "receipt-text": ReceiptText, recycle: Recycle, repeat: Repeat, "repeat-2": Repeat2,
  ruler: Ruler, scale: Scale, "scroll-text": ScrollText, send: Send, settings: Settings, "settings-2": Settings2,
  "shield-check": ShieldCheck, "shopping-bag": ShoppingBag, "shopping-cart": ShoppingCart, split: Split,
  sprout: Sprout, store: Store, tags: Tags, tractor: Tractor, "trending-up": TrendingUp, users: Users, wallet: Wallet,
  warehouse: Warehouse, wrench: Wrench, zap: Zap,
};

export function NavIcon({ name, size = 18 }: { name?: string; size?: number }) {
  const Icon = name ? NAV_ICONS[name] : undefined;
  return Icon ? <Icon size={size} strokeWidth={1.75} aria-hidden /> : null;
}

/** Pastille des catégories de calculettes (lot NV4, § 5.5) : pictogramme agric pour les sujets agricoles. */
export const TOOL_CATEGORY_ICONS: Record<string, { icon?: string; pictogram?: string }> = {
  fiscal: { icon: "landmark" }, social: { icon: "heart-pulse" }, vat: { icon: "percent" },
  management: { icon: "chart-line" }, economics: { icon: "coins" }, measures: { icon: "ruler" },
  equipment: { pictogram: "tractor" }, sowing: { pictogram: "seeding" }, fertilization: { pictogram: "fertilization" },
  spraying: { pictogram: "sprayer" }, irrigation: { icon: "droplets" }, harvest: { pictogram: "harvester" },
  crops: { pictogram: "wheat" }, livestock: { pictogram: "cow" }, energy: { icon: "zap" }, regulatory: { icon: "scale" },
};
