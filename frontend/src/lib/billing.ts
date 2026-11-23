import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import { useAuth } from "./auth";

export type Plan = {
  code: string;
  name: string;
  monthly_price_cents: number;
  annual_price_cents: number;
  vehicle_limit: number | null;
  user_limit: number | null;
  plate_queries_included: number;
  features: string[];
  feature_labels: string[];
  postpaid: boolean;
  extra_store_price_cents: number;
};

export type InvoiceItem = { kind: string; description: string; quantity: number; total_cents: number };

export type Invoice = {
  id: string;
  kind: string;
  kind_display: string;
  status: "open" | "paid" | "overdue" | "canceled";
  status_display: string;
  total_cents: number;
  due_date: string;
  target_plan: string | null;
  target_cycle: string;
  payment_url: string;
  paid_at: string | null;
  created_at: string;
  items: InvoiceItem[];
};

export type Subscription = {
  plan: Plan;
  status: "trialing" | "active" | "past_due" | "suspended";
  status_display: string;
  cycle: "monthly" | "annual";
  trial_ends_at: string | null;
  paid_through: string | null;
  next_billing_date: string | null;
  scheduled_plan: string | null;
  scheduled_cycle: string;
};

export type BillingMe =
  | { applies: false; features: string[] }
  | {
      applies: true;
      subscription: Subscription;
      effective_plan: string;
      features: string[];
      limits: { vehicles: number | null; users: number | null; plate_queries: number };
      usage: { users: number };
      postpaid: { credit_limit_cents: number; owed_cents: number };
      open_invoice: Invoice | null;
    };

/** Plano e recursos da loja ativa. */
export function useBilling() {
  const { organization } = useAuth();
  const query = useQuery({
    queryKey: ["billing", organization?.id],
    queryFn: () => api<BillingMe>("/billing/me"),
    enabled: !!organization,
    staleTime: 60_000,
  });
  const data = query.data;
  return {
    ...query,
    applies: data?.applies ?? false,
    /** Enquanto carrega, não bloqueia (o backend sempre confere). */
    has: (feature: string) => !data || data.features.includes(feature),
  };
}

export function daysUntil(iso: string | null | undefined) {
  if (!iso) return 0;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000));
}

export const FEATURE_PLAN: Record<string, string> = {
  fiscal: "Essencial",
  financeiro: "Essencial",
  custos: "Essencial",
  contratos: "Essencial",
  avaliacao: "Essencial",
  crm: "Profissional",
  comissoes: "Profissional",
  consignacao: "Profissional",
  vitrine: "Profissional",
  assinatura: "Profissional",
  financiamento: "Premium",
  conciliacao: "Premium",
  multiloja: "Premium",
  relatorios: "Premium",
  posvenda: "Premium",
};
