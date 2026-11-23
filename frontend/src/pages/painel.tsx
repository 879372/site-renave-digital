import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Car, Handshake, Plus, ShieldAlert } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "wouter";

import { Money } from "@/components/kit";
import { Button, Card, Empty, PageHeader, Spinner, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBilling } from "@/lib/billing";
import { money, plate } from "@/lib/format";

const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

export function PainelPage() {
  const { user, organization, can } = useAuth();
  const { has } = useBilling();
  const d = useQuery({ queryKey: ["dashboard", organization?.id], queryFn: () => api<any>("/painel/dashboard") });
  const certs = useQuery({ queryKey: ["certificates", organization?.id], queryFn: () => api<{ results: any[] }>("/vault/certificates") });
  const first = user?.full_name.split(" ")[0];
  if (d.isLoading) return <Spinner />;
  const s = d.data;
  const chart = (s?.chart ?? []).map((m: any) => ({ mes: MONTHS[Number(m.month.slice(5, 7)) - 1], Vendas: m.units, Lucro: m.profit_cents / 100 }));
  const ownCert = certs.data?.results.find((c) => !c.client_id);
  return (
    <div className="space-y-6">
      <PageHeader
        title={`Olá, ${first}`}
        description={`Resumo de ${organization?.name ?? "sua loja"}.`}
        action={
          <div className="flex gap-2">
            {can("estoque.manage") && <Link href="/veiculos"><Button variant="secondary"><Plus className="size-4" /> Veículo</Button></Link>}
            {can("vendas.operate") && <Link href="/vendas/nova"><Button><Plus className="size-4" /> Venda</Button></Link>}
          </div>
        }
      />
      {certs.data && !ownCert && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warn/40 bg-warn-50 p-4">
          <p className="flex items-center gap-2 text-sm"><ShieldAlert className="size-5 text-[#8a6500]" aria-hidden /> Envie o certificado digital A1 da empresa para operar o RENAVE e emitir notas fiscais.</p>
          <Link href="/empresa?aba=certificados"><Button size="sm" variant="secondary">Enviar certificado</Button></Link>
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Veículos em estoque" value={s.stock.count} icon={<Car className="size-5" />} hint={`${s.stock.available} disponíveis · ${s.stock.preparing} em preparação`} />
        <Stat label="Valor do estoque" value={money(s.stock.value_cents)} hint={`Custo: ${money(s.stock.cost_cents)}`} />
        <Stat label="Vendas no mês" value={s.sales_month.units} icon={<Handshake className="size-5" />} hint={money(s.sales_month.revenue_cents)} />
        <Stat label="Lucro no mês" value={<span className={s.sales_month.profit_cents >= 0 ? "text-green" : "text-red"}>{money(s.sales_month.profit_cents)}</span>} hint={`Idade média do estoque: ${s.stock.avg_age_days} dias`} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Card title="Vendas e lucro (6 meses)">
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={chart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" vertical={false} />
                <XAxis dataKey="mes" tick={{ fontSize: 12 }} />
                <YAxis yAxisId="l" tick={{ fontSize: 11 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
                <YAxis yAxisId="u" orientation="right" allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v: number, n: string) => (n === "Lucro" ? money(Math.round(v * 100)) : v)} />
                <Bar yAxisId="l" dataKey="Lucro" fill="#047857" radius={[3, 3, 0, 0]} />
                <Bar yAxisId="u" dataKey="Vendas" fill="#a1a1aa" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <div className="space-y-4">
          {has("financeiro") && s.finance && (
            <Card title="Financeiro">
              <div className="space-y-1.5 text-sm">
                <p className="flex justify-between"><span className="text-muted">Saldo em caixa</span><Money cents={s.finance.saldo_cents} /></p>
                <p className="flex justify-between"><span className="text-muted">A pagar em 7 dias</span><Money cents={s.finance.pagar_7d_cents} /></p>
                <p className="flex justify-between"><span className="text-muted">A receber em 7 dias</span><Money cents={s.finance.receber_7d_cents} /></p>
                {(s.finance.pagar_vencido_cents > 0 || s.finance.receber_vencido_cents > 0) && <p className="flex items-center gap-1 text-red"><AlertTriangle className="size-4" /> Há contas vencidas</p>}
              </div>
              <Link href="/financeiro" className="mt-3 block text-sm font-medium text-brand">Abrir financeiro →</Link>
            </Card>
          )}
          {has("crm") && s.leads && (
            <Card title="Leads">
              <div className="flex gap-6 text-sm">
                <p><span className="block text-2xl font-semibold">{s.leads.new}</span><span className="text-muted">novos</span></p>
                <p><span className="block text-2xl font-semibold">{s.leads.open}</span><span className="text-muted">em aberto</span></p>
                <p><span className="block text-2xl font-semibold">{s.leads.tasks_today}</span><span className="text-muted">retornos hoje</span></p>
              </div>
              <Link href="/leads" className="mt-3 block text-sm font-medium text-brand">Abrir funil →</Link>
            </Card>
          )}
          <Card title="Atenção">
            <ul className="space-y-1.5 text-sm">
              <li className="flex justify-between"><span>Parados há mais de 60 dias</span><strong className={s.stock.stale_60 ? "text-warn" : ""}>{s.stock.stale_60}</strong></li>
              <li className="flex justify-between"><span>Parados há mais de 90 dias</span><strong className={s.stock.stale_90 ? "text-red" : ""}>{s.stock.stale_90}</strong></li>
              <li className="flex justify-between"><span>Sem fotos</span><strong>{s.stock.no_photos}</strong></li>
              <li className="flex justify-between"><span>Propostas em aberto</span><strong>{s.open_proposals}</strong></li>
            </ul>
          </Card>
        </div>
      </div>
      <Card title="Carros parados há mais tempo" action={<Link href="/veiculos" className="text-sm font-medium text-brand">Ver estoque →</Link>}>
        {!s.stale.length ? <Empty title="Nenhum carro parado há mais de 60 dias" icon={<Car />} /> : (
          <ul className="divide-y divide-line text-sm">
            {s.stale.map((v: any) => (
              <li key={v.id}><Link href={`/veiculos/${v.id}`} className="flex justify-between py-2 hover:text-brand"><span>{v.title} <span className="text-muted">{plate(v.placa)}</span></span><span><strong className={v.days > 90 ? "text-red" : "text-warn"}>{v.days} dias</strong> · {money(v.price_cents)}</span></Link></li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
