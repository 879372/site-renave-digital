import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDownLeft, ArrowUpRight, Wallet } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Card, Empty, Field, Input, PageHeader, Spinner, Table } from "@/components/ui";
import { api, cursorOf, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, maskMoney, money, parseMoney } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

type Entry = { id: string; kind: string; kind_display: string; amount_cents: number; balance_after_cents: number; description: string; created_at: string };
type TopUp = { id: string; amount_cents: number; status: string; status_display: string; provider_reference: string; pix_copy_paste: string; created_at: string };

const PRESETS = [10000, 25000, 50000, 100000];

export function CarteiraPage() {
  const { organization, can } = useAuth();
  const org = organization?.id;
  const qc = useQueryClient();
  const [amount, setAmount] = useState("250,00");
  const wallet = useQuery({ queryKey: ["wallet", org], queryFn: () => api<{ balance_cents: number }>("/wallet/") });
  const prices = useQuery({ queryKey: ["prices", org], queryFn: () => api<{ code: string; label: string; price_cents: number }[]>("/wallet/prices") });
  const topups = useQuery({ queryKey: ["topups", org], queryFn: () => api<Page<TopUp>>("/wallet/topups") });
  const entries = useInfiniteQuery({
    queryKey: ["ledger", org],
    queryFn: ({ pageParam }) => api<Page<Entry>>("/wallet/entries", { params: { cursor: pageParam } }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (l) => cursorOf(l.next),
  });
  const create = useMutation({
    mutationFn: () => api<TopUp>("/wallet/topups", { body: { amount_cents: parseMoney(amount) } }),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["topups", org] });
      toast.success(`Recarga ${t.provider_reference} solicitada. O saldo é liberado após a confirmação do pagamento.`);
    },
    onError: (e) => handleApiError(e),
  });
  const rows = entries.data?.pages.flatMap((p) => p.results) ?? [];
  const pending = topups.data?.results.filter((t) => t.status === "pending") ?? [];

  return (
    <>
      <PageHeader title="Carteira" description="Créditos pré-pagos usados em consultas, operações RENAVE, comunicações e notas fiscais." />
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          <section className="rounded-2xl bg-navy p-6 text-white">
            <p className="flex items-center gap-2 text-sm text-[#c7d0ed]">
              <Wallet className="size-4" /> Saldo disponível
            </p>
            <p className="mt-2 font-display text-5xl font-bold">{wallet.data ? money(wallet.data.balance_cents) : "…"}</p>
          </section>
          <Card title="Extrato">
            {entries.isLoading ? (
              <Spinner />
            ) : rows.length === 0 ? (
              <Empty title="Nenhuma movimentação" icon={<Wallet />} />
            ) : (
              <>
                <Table head={["Data", "Descrição", "Tipo", "Valor", "Saldo"]}>
                  {rows.map((e) => (
                    <tr key={e.id}>
                      <td className="px-5 py-3 whitespace-nowrap text-muted">{dateTime(e.created_at)}</td>
                      <td className="px-5 py-3">{e.description}</td>
                      <td className="px-5 py-3">
                        <Badge tone={e.amount_cents >= 0 ? "green" : "gray"}>{e.kind_display}</Badge>
                      </td>
                      <td className={clsx("px-5 py-3 font-semibold whitespace-nowrap", e.amount_cents >= 0 ? "text-green" : "text-ink")}>
                        {e.amount_cents >= 0 ? <ArrowDownLeft className="mr-1 inline size-4" /> : <ArrowUpRight className="mr-1 inline size-4" />}
                        {money(Math.abs(e.amount_cents))}
                      </td>
                      <td className="px-5 py-3 text-muted">{money(e.balance_after_cents)}</td>
                    </tr>
                  ))}
                </Table>
                {entries.hasNextPage && (
                  <div className="mt-4 text-center">
                    <Button variant="secondary" size="sm" onClick={() => entries.fetchNextPage()}>
                      Carregar mais
                    </Button>
                  </div>
                )}
              </>
            )}
          </Card>
        </div>
        <div className="space-y-6">
          {can("wallet.manage") && (
            <Card title="Recarregar créditos">
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2">
                  {PRESETS.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setAmount(maskMoney(String(p)))}
                      className={clsx("rounded-lg border py-2 font-semibold", parseMoney(amount) === p ? "border-blue bg-blue-50 text-blue" : "border-line hover:border-blue/50")}
                    >
                      {money(p)}
                    </button>
                  ))}
                </div>
                <Field label="Outro valor (R$)" htmlFor="amount" hint="Mínimo R$ 20,00.">
                  <Input id="amount" inputMode="decimal" placeholder="0,00" value={amount} onChange={(e) => setAmount(maskMoney(e.target.value))} />
                </Field>
                <Button className="w-full" onClick={() => create.mutate()} loading={create.isPending}>
                  Gerar recarga
                </Button>
                {pending.length > 0 && (
                  <div className="rounded-xl bg-yellow-50 p-3 text-sm">
                    <p className="font-semibold">Aguardando pagamento</p>
                    {pending.map((t) => (
                      <p key={t.id} className="text-muted">
                        {t.provider_reference} · {money(t.amount_cents)}
                      </p>
                    ))}
                    <p className="mt-2 text-xs text-muted">Envie o comprovante para a equipe pelo WhatsApp com o código da recarga.</p>
                  </div>
                )}
              </div>
            </Card>
          )}
          <Card title="Tabela de preços">
            <ul className="divide-y divide-line text-sm">
              {prices.data?.map((p) => (
                <li key={p.code} className="flex justify-between gap-3 py-2">
                  <span className="text-muted">{p.label}</span>
                  <strong>{money(p.price_cents)}</strong>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted">Consultas têm preço por produto. Falhas sem cobrança da fonte são estornadas automaticamente.</p>
          </Card>
        </div>
      </div>
    </>
  );
}
