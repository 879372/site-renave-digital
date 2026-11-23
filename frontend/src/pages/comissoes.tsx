import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trophy } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Money, MoneyInput, useMembers } from "@/components/kit";
import { PlanGate } from "@/components/PlanGate";
import { Button, Card, Empty, Field, Input, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { handleApiError } from "@/lib/forms";
import { ask } from "@/components/confirm";

type Row = { seller_id: string | null; seller_name: string; units: number; revenue_cents: number; profit_cents: number; commission_cents: number; commission_pending_cents: number; goal_units: number | null; goal_revenue_cents: number | null };

export function ComissoesPage() {
  const { organization, can } = useAuth();
  const qc = useQueryClient();
  const members = useMembers();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const rel = useQuery({ queryKey: ["comissoes", organization?.id, month], queryFn: () => api<{ rows: Row[] }>("/vendas/comissoes", { params: { month: `${month}-01` } }) });
  const rule = useQuery({ queryKey: ["regra-comissao", organization?.id], queryFn: () => api<{ mode: string; value: number; min_cents: number }>("/vendas/comissoes/regra") });
  const metas = useQuery({ queryKey: ["metas", organization?.id, month], queryFn: () => api<any[]>("/vendas/metas", { params: { month: `${month}-01` } }) });
  const [r, setR] = useState({ mode: "sobra", value: 1000, min_cents: 0 });
  const [meta, setMeta] = useState({ seller: "", units: 0, revenue_cents: 0 });
  useEffect(() => { if (rule.data) setR(rule.data); }, [rule.data]);
  const manage = can("financeiro.manage");
  const saveRule = useMutation({ mutationFn: () => api("/vendas/comissoes/regra", { method: "PUT", body: r }), onSuccess: () => toast.success("Regra salva"), onError: (e) => handleApiError(e) });
  const pay = useMutation({
    mutationFn: () => api<{ sellers: number }>("/vendas/comissoes", { body: { month: `${month}-01` } }),
    onSuccess: (x) => { toast.success(`Comissões fechadas para ${x.sellers} vendedor(es). Contas a pagar criadas.`); qc.invalidateQueries({ queryKey: ["comissoes"] }); },
    onError: (e) => handleApiError(e),
  });
  const addMeta = useMutation({
    mutationFn: () => api("/vendas/metas", { body: { ...meta, month: `${month}-01` } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["metas"] }); qc.invalidateQueries({ queryKey: ["comissoes"] }); toast.success("Meta salva"); },
    onError: (e) => handleApiError(e),
  });
  const pending = rel.data?.rows.reduce((s, x) => s + x.commission_pending_cents, 0) ?? 0;
  const pct = r.mode === "fixo" ? null : (r.value / 100).toString().replace(".", ",");
  return (
    <>
      <PageHeader title="Vendedores e comissões" description="Ranking do mês, metas e fechamento das comissões." action={<Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="h-9 w-44" />} />
      <PlanGate feature="comissoes" title="Vendedores e comissões">
        <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
          <Card title="Ranking do mês" action={manage && pending > 0 && <Button size="sm" onClick={() => void ask("Gerar as contas a pagar das comissões pendentes do mês?").then((ok) => ok && pay.mutate())} loading={pay.isPending}>Fechar comissões</Button>}>
            {rel.isLoading ? <Spinner /> : !rel.data?.rows.length ? <Empty title="Nenhuma venda fechada no mês" icon={<Trophy />} /> : (
              <Table head={["#", "Vendedor", "Vendas", "Faturamento", "Lucro", "Comissão", "Meta"]}>
                {rel.data.rows.map((x, i) => (
                  <tr key={x.seller_id ?? i}>
                    <td className="px-5 py-3 font-semibold">{i + 1}º</td>
                    <td className="px-5 py-3">{x.seller_name}</td>
                    <td className="px-5 py-3 tabular">{x.units}</td>
                    <td className="px-5 py-3"><Money cents={x.revenue_cents} /></td>
                    <td className="px-5 py-3"><Money cents={x.profit_cents} /></td>
                    <td className="px-5 py-3"><Money cents={x.commission_cents} />{x.commission_pending_cents > 0 && <span className="block text-xs text-warn">pendente</span>}</td>
                    <td className="px-5 py-3 text-sm">{x.goal_units ? `${x.units}/${x.goal_units} (${Math.round((x.units * 100) / x.goal_units)}%)` : "—"}</td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          <div className="space-y-6">
            <Card title="Regra de comissão">
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); saveRule.mutate(); }}>
                <Field label="Base" htmlFor="cr-m"><Select id="cr-m" disabled={!manage} value={r.mode} onChange={(e) => setR({ ...r, mode: e.target.value })}><option value="sobra">% sobre o lucro (sobra)</option><option value="preco">% sobre o valor da venda</option><option value="fixo">Valor fixo por carro</option></Select></Field>
                {r.mode === "fixo" ? (
                  <Field label="Valor por carro"><MoneyInput value={r.value} disabled={!manage} onChange={(c) => setR({ ...r, value: c })} /></Field>
                ) : (
                  <Field label="Percentual (%)" htmlFor="cr-v"><Input id="cr-v" disabled={!manage} inputMode="decimal" value={pct ?? ""} onChange={(e) => setR({ ...r, value: Math.round(Number(e.target.value.replace(",", ".") || 0) * 100) })} /></Field>
                )}
                <Field label="Comissão mínima por carro"><MoneyInput value={r.min_cents} disabled={!manage} onChange={(c) => setR({ ...r, min_cents: c })} /></Field>
                {manage && <Button type="submit" variant="secondary" className="w-full" loading={saveRule.isPending}>Salvar regra</Button>}
                <p className="text-xs text-muted">Vale para vendas fechadas daqui em diante.</p>
              </form>
            </Card>
            <Card title="Metas do mês">
              <ul className="mb-3 space-y-1 text-sm">{metas.data?.map((m) => <li key={m.id} className="flex justify-between"><span>{m.seller_name}</span><span>{m.units} carros · <Money cents={m.revenue_cents} /></span></li>)}</ul>
              {manage && (
                <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); addMeta.mutate(); }}>
                  <Select required value={meta.seller} onChange={(e) => setMeta({ ...meta, seller: e.target.value })}><option value="">Vendedor</option>{members.data?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</Select>
                  <div className="grid grid-cols-2 gap-2">
                    <Input inputMode="numeric" placeholder="Carros" value={meta.units || ""} onChange={(e) => setMeta({ ...meta, units: Number(e.target.value.replace(/\D/g, "") || 0) })} />
                    <MoneyInput value={meta.revenue_cents} onChange={(c) => setMeta({ ...meta, revenue_cents: c })} placeholder="Faturamento" />
                  </div>
                  <Button type="submit" size="sm" variant="secondary" className="w-full">Definir meta</Button>
                </form>
              )}
            </Card>
          </div>
        </div>
      </PlanGate>
    </>
  );
}
