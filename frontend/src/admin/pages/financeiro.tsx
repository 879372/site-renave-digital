import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Card, Input, PageHeader, Spinner } from "@/components/ui";
import { dateTime, maskMoney, money, parseMoney } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

import { adminApi } from "../api";
import { DATE_FILTERS, OrgCell, ResourceTable } from "../components";

const TOPUP_TONE: Record<string, "yellow" | "green" | "gray" | "red"> = { pending: "yellow", paid: "green", expired: "gray", canceled: "red" };

export function RecargasPage() {
  const qc = useQueryClient();
  const act = useMutation({
    mutationFn: ({ id, path }: { id: string; path: "confirm" | "cancel" }) => adminApi(`/topups/${id}/${path}`, { method: "POST" }),
    onSuccess: (_, v) => {
      toast.success(v.path === "confirm" ? "Pagamento confirmado e saldo creditado." : "Recarga cancelada.");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => handleApiError(e),
  });
  return (
    <>
      <PageHeader title="Recargas" description="Confirme os pagamentos recebidos para liberar o saldo das empresas." />
      <ResourceTable<any>
        endpoint="/topups"
        searchPlaceholder="Código da recarga, empresa ou CNPJ"
        filters={[
          {
            name: "status",
            label: "Status",
            options: [
              ["", "Todas"],
              ["pending", "Aguardando pagamento"],
              ["paid", "Pagas"],
              ["canceled", "Canceladas"],
            ],
          },
          ...DATE_FILTERS,
        ]}
        columns={[
          { header: "Data", cell: (t) => dateTime(t.created_at), className: "whitespace-nowrap" },
          { header: "Código", cell: (t) => <span className="font-mono">{t.provider_reference}</span>, className: "whitespace-nowrap" },
          { header: "Empresa", cell: (t) => <OrgCell org={t.organization} /> },
          { header: "Solicitado por", cell: (t) => t.requested_by ?? "—" },
          { header: "Valor", cell: (t) => <strong>{money(t.amount_cents)}</strong>, className: "text-right whitespace-nowrap" },
          { header: "Status", cell: (t) => <><Badge tone={TOPUP_TONE[t.status]}>{t.status_display}</Badge>{t.paid_at && <span className="block text-xs text-muted">{dateTime(t.paid_at)}</span>}</> },
          {
            header: "",
            cell: (t) =>
              t.status === "pending" && (
                <div className="flex justify-end gap-1">
                  <Button size="sm" onClick={() => confirm(`Confirmar o recebimento de ${money(t.amount_cents)} de ${t.organization?.name}?`) && act.mutate({ id: t.id, path: "confirm" })}>
                    <Check className="size-4" /> Confirmar
                  </Button>
                  <Button size="sm" variant="ghost" aria-label="Cancelar recarga" onClick={() => confirm("Cancelar esta recarga?") && act.mutate({ id: t.id, path: "cancel" })}>
                    <X className="size-4 text-red" />
                  </Button>
                </div>
              ),
          },
        ]}
      />
    </>
  );
}

export function ExtratoPage() {
  return (
    <>
      <PageHeader title="Movimentações" description="Todos os lançamentos das carteiras das empresas." />
      <ResourceTable<any>
        endpoint="/ledger"
        searchPlaceholder="Buscar na descrição"
        filters={[
          {
            name: "kind",
            label: "Tipo",
            options: [
              ["", "Todos"],
              ["topup", "Recargas"],
              ["reserve", "Reservas"],
              ["release", "Estornos"],
              ["capture_adjust", "Ajustes de cobrança"],
              ["adjustment", "Ajustes administrativos"],
            ],
          },
          ...DATE_FILTERS,
        ]}
        columns={[
          { header: "Data", cell: (e) => dateTime(e.created_at), className: "whitespace-nowrap" },
          { header: "Descrição", cell: (e) => e.description },
          { header: "Tipo", cell: (e) => <Badge tone={e.amount_cents >= 0 ? "green" : "gray"}>{e.kind_display}</Badge> },
          { header: "Valor", cell: (e) => <span className={e.amount_cents >= 0 ? "text-green" : ""}>{money(e.amount_cents)}</span>, className: "text-right whitespace-nowrap" },
          { header: "Saldo após", cell: (e) => money(e.balance_after_cents), className: "text-right whitespace-nowrap" },
          { header: "Por", cell: (e) => e.created_by ?? "Sistema" },
        ]}
      />
    </>
  );
}

type Price = { id: number; code: string; label: string; price_cents: number; is_active: boolean };

function PriceRow({ item }: { item: Price }) {
  const qc = useQueryClient();
  const [value, setValue] = useState(maskMoney(String(item.price_cents)));
  const save = useMutation({
    mutationFn: (body: object) => adminApi(`/prices/${item.id}`, { method: "PATCH", body }),
    onSuccess: () => {
      toast.success("Preço atualizado.");
      qc.invalidateQueries({ queryKey: ["admin", "prices"] });
    },
    onError: (e) => handleApiError(e),
  });
  const dirty = parseMoney(value) !== item.price_cents;
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div>
        <p className="font-semibold">{item.label}</p>
        <p className="font-mono text-xs text-muted">{item.code}</p>
      </div>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-blue" checked={item.is_active} onChange={(e) => save.mutate({ is_active: e.target.checked })} /> Cobrar
        </label>
        <span className="text-sm text-muted">R$</span>
        <Input className="h-9 w-28 text-right" inputMode="decimal" placeholder="0,00" value={value} onChange={(e) => setValue(maskMoney(e.target.value))} aria-label={`Preço de ${item.label}`} />
        <Button size="sm" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate({ price_cents: parseMoney(value) })}>
          Salvar
        </Button>
      </div>
    </li>
  );
}

export function PrecosPage() {
  const { data, isLoading } = useQuery({ queryKey: ["admin", "prices"], queryFn: () => adminApi<Price[]>("/prices") });
  return (
    <>
      <PageHeader title="Preços de serviços" description="Tarifas cobradas das empresas por operação. O novo valor vale para as próximas operações." />
      <Card>{isLoading ? <Spinner /> : <ul className="divide-y divide-line">{data?.map((p) => <PriceRow key={p.id} item={p} />)}</ul>}</Card>
    </>
  );
}
