import type { IntegrationState } from "../../components/IntegrationNotice";

export interface Entity {
  id: number; name: string; entity_type: string; email: string | null; account_code: string | null;
  is_member: boolean; is_benevole: boolean; notes: string | null;
  default_product_id: number | null; default_product: string | null;
  vat_number: string | null; siret: string | null; iban: string | null;
  address_line1: string | null; address_line2: string | null; postal_code: string | null; city: string | null;
  country: string | null; person_kind: "individual" | "company" | null;
  last_helloasso_membership: string | null; last_pos_membership: string | null; transactions: number;
}

export interface Option { value: string; label: string }

export interface EntitiesMeta {
  types: Option[];
  products: Option[];
  integrations: Record<"helloasso" | "odoo" | "smtp", IntegrationState>;
}

export const TIERS_KEY = ["tiers"];
