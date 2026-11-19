import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Car, FileText, Search, ShieldAlert, Wallet } from "lucide-react";
import { Link } from "wouter";

import { Button, Card, Empty, PageHeader, Spinner, Stat } from "@/components/ui";
import { api, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, money, plate } from "@/lib/format";

import { StatusBadge, type Consulta } from "./consultas";

export function DashboardPage() {
  const { user, organization } = useAuth();
  const org = organization?.id;

  const wallet = useQuery({ queryKey: ["wallet", org], queryFn: () => api<{ balance_cents: number }>("/wallet/") });
  const summary = useQuery({ queryKey: ["consultas-summary", org], queryFn: () => api("/consultas/summary") });
  const recent = useQuery({ queryKey: ["consultas", org, "recent"], queryFn: () => api<Page<Consulta>>("/consultas/", { params: { page_size: 6 } }) });
  const stock = useQuery({ queryKey: ["stock", org, "count"], queryFn: () => api<Page<unknown>>("/renave/stock", { params: { state: "CONFIRMADO", page_size: 1 } }) });
  const certs = useQuery({ queryKey: ["certificates", org], queryFn: () => api<{ results: any[] }>("/vault/certificates") });

  const ownCert = certs.data?.results.find((c) => !c.client_id);
  const first = user?.full_name.split(" ")[0];

  return (
    <div className="space-y-6">
      <PageHeader title={`Olá, ${first}`} description={`Resumo de ${organization?.name ?? "sua empresa"}.`} />

      {certs.data && !ownCert && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-yellow/40 bg-yellow-50 p-4">
          <p className="flex items-center gap-2 text-sm">
            <ShieldAlert className="size-5 text-[#8a6500]" aria-hidden />
            Envie o certificado digital A1 da empresa para operar o RENAVE e emitir notas fiscais.
          </p>
          <Link href="/empresa?aba=certificados">
            <Button size="sm" variant="secondary">
              Enviar certificado
            </Button>
          </Link>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Saldo disponível" value={wallet.data ? money(wallet.data.balance_cents) : "…"} icon={<Wallet className="size-5" />} hint={<Link href="/carteira" className="font-semibold text-blue">Recarregar</Link>} />
        <Stat label="Consultas (30 dias)" value={summary.data?.last_30_days.total ?? "…"} icon={<Search className="size-5" />} hint={summary.data ? `${money(summary.data.last_30_days.spent)} investidos` : undefined} />
        <Stat label="Veículos em estoque" value={stock.data?.count ?? "…"} icon={<Car className="size-5" />} hint={<Link href="/estoque" className="font-semibold text-blue">Ver estoque</Link>} />
        <Stat label="Notas fiscais" value={<FileText className="size-8 text-blue" />} hint={<Link href="/notas" className="font-semibold text-blue">Emitir NF-e</Link>} />
      </div>

      <Card
        title="Consultas recentes"
        action={
          <Link href="/consultas" className="inline-flex items-center gap-1 text-sm font-semibold text-blue">
            Ver todas <ArrowRight className="size-4" />
          </Link>
        }
      >
        {recent.isLoading ? (
          <Spinner />
        ) : !recent.data?.results.length ? (
          <Empty title="Nenhuma consulta ainda" icon={<Search />}>
            <Link href="/consultas" className="font-semibold text-blue">
              Fazer a primeira consulta
            </Link>
          </Empty>
        ) : (
          <ul className="divide-y divide-line">
            {recent.data.results.map((c) => (
              <li key={c.id}>
                <Link href={`/consultas/${c.id}`} className="-mx-2 flex items-center justify-between gap-4 rounded-lg px-2 py-3 hover:bg-pale">
                  <div className="min-w-0">
                    <p className="font-mono font-semibold">{c.input_type === "PLACA" ? plate(c.input_value) : c.input_value}</p>
                    <p className="truncate text-sm text-muted">
                      {c.product_name} · {dateTime(c.created_at)}
                    </p>
                  </div>
                  <StatusBadge status={c.status} label={c.status_display} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
