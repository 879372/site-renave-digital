import { Lock } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "wouter";

import { FEATURE_PLAN, useBilling } from "@/lib/billing";

import { buttonClass } from "./ui";

/** Mostra o conteúdo só se o plano incluir o recurso; senão, explica e leva para a tela de planos. */
export function PlanGate({ feature, title, children }: { feature: string; title: string; children: ReactNode }) {
  const { has } = useBilling();
  if (has(feature)) return <>{children}</>;
  return <LockedPanel feature={feature} title={title} />;
}

export function LockedPanel({ feature, title }: { feature: string; title: string }) {
  const plan = FEATURE_PLAN[feature] ?? "superior";
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-line bg-white px-6 py-12 text-center">
      <span className="grid size-12 place-items-center rounded-full bg-warn-50 text-[#8a6500]">
        <Lock className="size-5" aria-hidden />
      </span>
      <p className="font-display text-lg font-semibold">{title} faz parte do plano {plan}</p>
      <p className="max-w-md text-sm text-muted">Seus dados continuam guardados. Mude de plano para liberar este recurso.</p>
      <Link href="/planos" className={buttonClass("primary", "md", "mt-2")}>
        Ver planos
      </Link>
    </div>
  );
}
