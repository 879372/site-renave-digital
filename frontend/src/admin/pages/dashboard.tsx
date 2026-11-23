import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, KeyRound, Wallet, XCircle } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "wouter";

import { Badge, Card, PageHeader, Spinner, Stat } from "@/components/ui";
import { money } from "@/lib/format";

import { adminApi } from "../api";

// Paleta validada (scripts/validate_palette.js): contraste ≥ 3:1 e separação para daltonismo.
const SERIES = { revenue: "#1d44d8", cost: "#c45f00" };
const GRID = "#e6e9f0";
const AXIS = "#4d5a73";

type Stats = {
  period_days: number;
  organizations: { total: number; active: number; new: number };
  users: { total: number; new: number };
  consultas: { total: number; success: number; failed: number; revenue: number; cost: number; today: number };
  revenue: { consultas: number; renave: number; nfe: number; comunicacao: number; total: number };
  topups: { paid_cents: number; paid_count: number; pending_count: number; pending_cents: number };
  wallets_balance_cents: number;
  renave: { in_stock: number; operations: number; failed: number };
  nfe: { authorized: number; rejected: number };
  certificates_expiring: number;
  series: { date: string; consultas: number; revenue_cents: number; cost_cents: number; new_organizations: number }[];
  providers: { provider: string; label: string; calls_24h: number; success_rate: number | null; avg_ms: number | null; last_error: string | null }[];
  top_products: { product__name: string; n: number; revenue: number; cost: number | null }[];
};

const shortDate = (iso: string) => iso.slice(8, 10) + "/" + iso.slice(5, 7);
const compactMoney = (cents: number) => {
  const v = cents / 100;
  return v >= 1000 ? `R$ ${(v / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil` : `R$ ${v.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}`;
};

function ChartTooltip({ active, payload, label, money: isMoney }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 text-sm shadow-lg">
      <p className="mb-1 font-semibold">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-ink">
          <span className="inline-block size-2.5 rounded-full" style={{ background: p.color }} aria-hidden />
          {p.name}: <strong>{isMoney ? money(p.value) : p.value.toLocaleString("pt-BR")}</strong>
        </p>
      ))}
    </div>
  );
}

function Legend({ items }: { items: [string, string][] }) {
  return (
    <div className="flex flex-wrap gap-4 text-sm text-muted">
      {items.map(([label, color]) => (
        <span key={label} className="flex items-center gap-2">
          <span className="inline-block h-0.5 w-4 rounded" style={{ background: color }} aria-hidden />
          {label}
        </span>
      ))}
    </div>
  );
}

export function AdminDashboard() {
  const [days, setDays] = useState(30);
  const [showTable, setShowTable] = useState(false);
  const { data: s, isLoading } = useQuery({ queryKey: ["admin", "stats", days], queryFn: () => adminApi<Stats>("/stats", { params: { days } }) });

  if (isLoading || !s) return <Spinner />;
  const margin = s.consultas.revenue - s.consultas.cost;
  const series = s.series.map((d) => ({ ...d, label: shortDate(d.date) }));
  const alerts = [
    s.topups.pending_count > 0 && { href: "/recargas", icon: Wallet, text: `${s.topups.pending_count} recarga(s) aguardando confirmação · ${money(s.topups.pending_cents)}` },
    s.certificates_expiring > 0 && { href: "/certificados", icon: KeyRound, text: `${s.certificates_expiring} certificado(s) vencem em até 30 dias` },
    ...s.providers.filter((p) => p.success_rate !== null && p.success_rate < 90).map((p) => ({ href: "/integracoes", icon: AlertTriangle, text: `${p.label}: ${p.success_rate}% de sucesso nas últimas 24h` })),
  ].filter(Boolean) as { href: string; icon: typeof Wallet; text: string }[];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Visão geral da plataforma."
        action={
          <div className="flex gap-1 rounded-xl bg-white p-1 ring-1 ring-line" role="group" aria-label="Período">
            {[7, 30, 90].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                aria-pressed={days === d}
                className={clsx("rounded-lg px-3 py-1.5 text-sm font-semibold", days === d ? "bg-graphite text-white" : "text-muted hover:text-ink")}
              >
                {d} dias
              </button>
            ))}
          </div>
        }
      />

      {alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map((a) => (
            <Link key={a.text} href={a.href} className="flex items-center gap-3 rounded-xl border border-warn/40 bg-warn-50 px-4 py-3 text-sm hover:border-warn">
              <a.icon className="size-4 text-[#8a6500]" aria-hidden /> {a.text}
            </Link>
          ))}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label={`Receita (${days} dias)`} value={money(s.revenue.total)} hint={`Consultas ${money(s.revenue.consultas)} · RENAVE ${money(s.revenue.renave)}`} />
        <Stat label="Margem das consultas" value={money(margin)} hint={s.consultas.revenue ? `${Math.round((margin * 100) / s.consultas.revenue)}% sobre a receita` : "Sem receita no período"} />
        <Stat label="Recargas pagas" value={money(s.topups.paid_cents)} hint={`${s.topups.paid_count} recarga(s) · saldo em carteiras ${money(s.wallets_balance_cents)}`} />
        <Stat label="Empresas" value={s.organizations.active.toLocaleString("pt-BR")} hint={`+${s.organizations.new} no período · ${s.users.total} usuários`} />
        <Stat label="Consultas" value={s.consultas.total.toLocaleString("pt-BR")} hint={`${s.consultas.today} hoje · ${s.consultas.failed} falharam`} />
        <Stat label="Veículos em estoque" value={s.renave.in_stock.toLocaleString("pt-BR")} hint={`${s.renave.operations} operações · ${s.renave.failed} recusadas`} />
        <Stat label="NF-e autorizadas" value={s.nfe.authorized.toLocaleString("pt-BR")} hint={`${s.nfe.rejected} rejeitadas no período`} />
        <Stat label="Comunicações de venda" value={money(s.revenue.comunicacao)} hint="Receita no período" />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Receita e custo das consultas" description="Por dia" action={<Legend items={[["Receita", SERIES.revenue], ["Custo", SERIES.cost]]} />}>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="label" tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={24} />
                <YAxis tickFormatter={compactMoney} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={false} width={84} />
                <Tooltip content={<ChartTooltip money />} cursor={{ stroke: AXIS, strokeWidth: 1 }} />
                <Line type="monotone" dataKey="revenue_cents" name="Receita" stroke={SERIES.revenue} strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: "#fff", strokeWidth: 2 }} />
                <Line type="monotone" dataKey="cost_cents" name="Custo" stroke={SERIES.cost} strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: "#fff", strokeWidth: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Consultas por dia" action={<button className="text-sm font-semibold text-brand" onClick={() => setShowTable((v) => !v)}>{showTable ? "Ver gráfico" : "Ver tabela"}</button>}>
          {showTable ? (
            <div className="h-64 overflow-y-auto text-sm">
              <table className="w-full">
                <thead className="sticky top-0 bg-white text-left text-xs text-muted uppercase">
                  <tr>
                    <th className="py-1">Dia</th>
                    <th>Consultas</th>
                    <th>Receita</th>
                    <th>Custo</th>
                    <th>Novas empresas</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {[...series].reverse().map((d) => (
                    <tr key={d.date}>
                      <td className="py-1">{d.label}</td>
                      <td>{d.consultas}</td>
                      <td>{money(d.revenue_cents)}</td>
                      <td>{money(d.cost_cents)}</td>
                      <td>{d.new_organizations}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap={2}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={24} />
                  <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={false} width={40} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(29,68,216,0.06)" }} />
                  <Bar dataKey="consultas" name="Consultas" fill={SERIES.revenue} radius={[4, 4, 0, 0]} maxBarSize={24} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Saúde das integrações" description="Últimas 24 horas">
          <ul className="divide-y divide-line">
            {s.providers.map((p) => {
              const ok = p.success_rate === null || p.success_rate >= 95;
              return (
                <li key={p.provider} className="flex items-center justify-between gap-4 py-3">
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 font-semibold">
                      {ok ? <CheckCircle2 className="size-4 text-green" aria-hidden /> : <XCircle className="size-4 text-red" aria-hidden />}
                      {p.label}
                    </p>
                    {p.last_error && <p className="truncate text-xs text-muted">Último erro: {p.last_error}</p>}
                  </div>
                  <div className="text-right text-sm">
                    {p.calls_24h ? (
                      <>
                        <Badge tone={ok ? "green" : "red"}>{p.success_rate}% sucesso</Badge>
                        <p className="mt-1 text-xs text-muted">
                          {p.calls_24h} chamadas · {p.avg_ms} ms em média
                        </p>
                      </>
                    ) : (
                      <span className="text-muted">Sem chamadas</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
        <Card title="Produtos que mais faturam" description={`Últimos ${days} dias`}>
          {s.top_products.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted">Nenhuma consulta cobrada no período.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted uppercase">
                <tr>
                  <th className="pb-2">Produto</th>
                  <th className="pb-2 text-right">Qtd.</th>
                  <th className="pb-2 text-right">Receita</th>
                  <th className="pb-2 text-right">Margem</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {s.top_products.map((p) => (
                  <tr key={p.product__name}>
                    <td className="py-2 font-semibold">{p.product__name}</td>
                    <td className="py-2 text-right">{p.n}</td>
                    <td className="py-2 text-right">{money(p.revenue)}</td>
                    <td className="py-2 text-right">{money(p.revenue - (p.cost ?? 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  );
}
