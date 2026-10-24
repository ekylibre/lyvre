// Pages de la SPA : app/spa_routes.json (partagé avec Flask) → composants chargés à la demande.
import type { ComponentType } from "react";
import routesFile from "../../../app/spa_routes.json";

export interface SpaRoute {
  rule: string;
  endpoint: string;
  public?: boolean;
}

export const SPA_ROUTES: SpaRoute[] = routesFile.routes;

type PageModule = { default: ComponentType };

/** Plusieurs endpoints servis par la même page (liste, création, modification). */
function pages(endpoints: string[], load: () => Promise<PageModule>): Record<string, () => Promise<PageModule>> {
  return Object.fromEntries(endpoints.map((endpoint) => [endpoint, load]));
}

/** Une page par endpoint de spa_routes.json (vérifié par routes.test.ts). */
export const PAGES: Record<string, () => Promise<PageModule>> = {
  "auth.login": () => import("../features/auth/LoginPage"),
  "auth.select_instance": () => import("../features/auth/SelectInstancePage"),
  "auth.change_password": () => import("../features/auth/ChangePasswordPage"),
  ...pages(["journals.index", "journals.new"], () => import("../features/journals/JournalsPage")),
  ...pages(["fiscal_years.index", "fiscal_years.new"], () => import("../features/fiscal-years/FiscalYearsPage")),
  "fiscal_years.closing": () => import("../features/fiscal-years/ClosingPage"),
  ...pages(["accounts.index", "accounts.new", "accounts.edit"], () => import("../features/accounts/AccountsPage")),
  ...pages(["products.index", "products.new", "products.edit"], () => import("../features/products/ProductsPage")),
  ...pages(["associates.index", "associates.new"], () => import("../features/associates/AssociatesPage")),
  "associates.detail": () => import("../features/associates/AssociateDetailPage"),
  "associates.import_csv": () => import("../features/associates/ImportAssociatesPage"),
  ...pages(["associate_expenses.index", "associate_expenses.new"], () => import("../features/associates/ExpensesPage")),
  ...pages(["share_movements.index", "share_movements.new", "share_movements.edit"],
    () => import("../features/associates/RegisterPage")),
  ...pages(["projects.index", "projects.new", "projects.edit"], () => import("../features/projects/ProjectsPage")),
  "budgets.index": () => import("../features/budget/BudgetPage"),
  "cash_forecast.index": () => import("../features/cash-forecast/CashForecastPage"),
  "about.index": () => import("../features/about/AboutPage"),
  "receipts.settings": () => import("../features/receipts/ReceiptSettingsPage"),
  "simple_categories.index": () => import("../features/simple/CategoriesPage"),
  "simple_operations.index": () => import("../features/simple/OperationsPage"),
  "simple_reports.index": () => import("../features/simple/SimpleReportsPage"),
  "receipts.index": () => import("../features/receipts/ReceiptsPage"),
  "budgets.tracking": () => import("../features/budget/BudgetTrackingPage"),
  "projects.statement": () => import("../features/projects/ProjectStatementPage"),
  ...pages(["rules.index", "rules.new", "rules.edit"], () => import("../features/rules/RulesPage")),
  ...pages(["work_times.task_types", "work_times.task_type_new", "work_times.task_type_edit"],
    () => import("../features/task-types/TaskTypesPage")),
  ...pages(["users.index", "users.new", "users.edit"], () => import("../features/users/UsersPage")),
  ...pages(["entities.index", "entities.new", "entities.edit"], () => import("../features/entities/EntitiesPage")),
  "entities.detail": () => import("../features/entities/EntityDetailPage"),
  "entities.members": () => import("../features/members/MembersPage"),
  "entities.members_reminders": () => import("../features/members/RemindersPage"),
  "entities.reminder_template": () => import("../features/members/ReminderTemplatePage"),
  ...pages(["work_times.index", "work_times.new", "work_times.edit"], () => import("../features/work-times/WorkTimesPage")),
  "work_times.import_view": () => import("../features/work-times/WorkTimesImportPage"),
  "dashboard.index": () => import("../features/dashboard/DashboardPage"),
  "entries.index": () => import("../features/entries/EntriesPage"),
  ...pages(["entries.new", "entries.edit"], () => import("../features/entries/EntryFormPage")),
  "entries.detail": () => import("../features/entries/EntryDetailPage"),
  "reports.balance": () => import("../features/reports/BalancePage"),
  "reports.grand_livre": () => import("../features/reports/GeneralLedgerPage"),
  "reports.bilan": () => import("../features/reports/BilanPage"),
  "reports.compte_resultat": () => import("../features/reports/CompteResultatPage"),
  ...pages(["bank_accounts.index", "bank_accounts.new", "bank_accounts.edit"], () => import("../features/bank-accounts/BankAccountsPage")),
  "bank_accounts.transactions": () => import("../features/bank-accounts/TransactionsPage"),
  "bank_accounts.cash": () => import("../features/bank-accounts/CashPage"),
  "bank_accounts.counterparties_view": () => import("../features/bank-accounts/CounterpartiesPage"),
  "bank_accounts.qonto_accounts": () => import("../features/bank-accounts/QontoAccountsPage"),
  "reconciliation.index": () => import("../features/reconciliation/ReconcilePage"),
  "payouts.index": () => import("../features/payouts/PayoutsPage"),
  "payouts.detail": () => import("../features/payouts/PayoutDetailPage"),
  "imports.ofx": () => import("../features/imports/ImportOfxPage"),
  "imports.reprise": () => import("../features/imports/ImportHistoryPage"),
  "purchases.index": () => import("../features/purchases/PurchasesPage"),
  ...pages(["purchases.new", "purchases.edit"], () => import("../features/purchases/PurchaseFormPage")),
  "purchases.detail": () => import("../features/purchases/PurchaseDetailPage"),
  "purchases.settlements": () => import("../features/purchases/SettlementsPage"),
  "purchases.suppliers": () => import("../features/purchases/SuppliersPage"),
  "subscriptions.index": () => import("../features/subscriptions/SubscriptionsPage"),
  "lettering.index": () => import("../features/lettering/LetteringPage"),
  "assets.index": () => import("../features/assets/AssetsPage"),
  "assets.detail": () => import("../features/assets/AssetDetailPage"),
  "account_roles.index": () => import("../features/lettering/AccountRolesPage"),
  "subscriptions.detail": () => import("../features/subscriptions/SubscriptionDetailPage"),
  "sales.index": () => import("../features/sales/SalesPage"),
  ...pages(["sales.new", "sales.edit"], () => import("../features/sales/SaleFormPage")),
  "sales.detail": () => import("../features/sales/SaleDetailPage"),
  "sales.due": () => import("../features/sales/DueSalesPage"),
  "sales.recurring": () => import("../features/sales/RecurringPage"),
  ...pages(["sales.recurring_new", "sales.recurring_edit"], () => import("../features/sales/RecurringFormPage")),
  "leases.index": () => import("../features/sales/LeasesPage"),
  "leases.detail": () => import("../features/sales/LeaseDetailPage"),
  ...pages(["leases.new", "leases.edit"], () => import("../features/sales/LeaseWizardPage")),
  "orders.index": () => import("../features/odoo/OrdersPage"),
  "orders.detail": () => import("../features/odoo/OrderDetailPage"),
  "customer_invoices.index": () => import("../features/odoo/CustomerInvoicesPage"),
  "customer_invoices.detail": () => import("../features/odoo/CustomerInvoiceDetailPage"),
  "imports.odoo": () => import("../features/odoo/OdooImportPage"),
  "imports.odoo_batch": () => import("../features/odoo/OdooBatchPage"),
  "impact.index": () => import("../features/impact/ImpactPage"),
  "impact.report": () => import("../features/impact/ImpactReportPage"),
  "impact.factors": () => import("../features/impact/FactorsPage"),
  "impact.manual": () => import("../features/impact/ManualPage"),
  "activity_report.index": () => import("../features/activity-report/ReportPage"),
  "activity_report.edit": () => import("../features/activity-report/TextsPage"),
  "activity_report.eco": () => import("../features/activity-report/EcoPage"),
  "activity_report.photos": () => import("../features/activity-report/PhotosPage"),
  "activity_report.archives": () => import("../features/activity-report/ArchivesPage"),
  "integrations.index": () => import("../features/integrations/IntegrationsPage"),
  "integrations.detail": () => import("../features/integrations/IntegrationDetailPage"),
  "access.index": () => import("../features/access/AccessPage"),
  "organization.index": () => import("../features/organization/OrganizationPage"),
  ...pages(["instances.index", "instances.new", "instances.edit"], () => import("../features/instances/InstancesPage")),
  ...pages(["instances.detail", "instances.restore"], () => import("../features/instances/InstanceDetailPage")),
  "instances.import_upload": () => import("../features/instances/ImportInstancePage"),
};

/** Pages sans la mise en page de l'application (en-tête, menus). */
export const BARE_PAGES = new Set(["auth.login", "auth.select_instance", "auth.change_password", "about.index"]);

/** Règle Flask → chemin react-router (« /purchases/<int:purchase_id> » → « /purchases/:purchase_id »). */
export function toRouterPath(rule: string): string {
  const path = rule.replace(/<(?:[a-z]+:)?(\w+)>/g, ":$1");
  return path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
}

const MATCHERS = SPA_ROUTES.map((route) => {
  const pattern = toRouterPath(route.rule)
    .split("/")
    .map((part) => (part.startsWith(":") ? "[^/]+" : part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
    .join("/");
  return new RegExp(`^${pattern}/?$`);
});

/** Le chemin est-il une page de la SPA (sinon : ancienne page, navigation complète) ? */
export function isSpaPath(url: string): boolean {
  const path = new URL(url, window.location.origin).pathname;
  return MATCHERS.some((re) => re.test(path));
}
