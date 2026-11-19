import { useQuery } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Modal, PageHeader, Spinner } from "@/components/ui";
import { date, dateTime, document, money, plate } from "@/lib/format";

import { adminApi } from "../api";
import { DATE_FILTERS, OrgCell, ResourceTable, type OrgRef } from "../components";

const CONSULTA_TONE: Record<string, "green" | "blue" | "red" | "yellow"> = { success: "green", not_found: "blue", failed: "red", processing: "yellow", pending: "yellow" };

type ConsultaRow = {
  id: string;
  organization: OrgRef;
  product_name: string;
  sku: string;
  input_type: string;
  input_value: string;
  purpose_display: string;
  status: string;
  status_display: string;
  price_cents: number;
  charged_cents: number;
  provider_cost_cents: number;
  provider_consulta_id: string;
  message: string;
  user_name: string | null;
  created_at: string;
};

function ConsultaModal({ id, onClose }: { id: string; onClose: () => void }) {
  const [withResult, setWithResult] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "consulta", id, withResult],
    queryFn: () => adminApi<ConsultaRow & { result?: any }>(`/consultas/${id}`, { params: { with_result: withResult ? 1 : undefined } }),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="Detalhes da consulta" wide>
      {isLoading || !data ? (
        <Spinner />
      ) : (
        <div className="space-y-4 text-sm">
          <dl className="grid gap-3 sm:grid-cols-3">
            {[
              ["Empresa", data.organization?.name],
              ["Usuário", data.user_name],
              ["Data", dateTime(data.created_at)],
              ["Produto", data.product_name],
              ["Código no fornecedor", data.sku],
              ["Identificador", data.input_type === "PLACA" ? plate(data.input_value) : data.input_value],
              ["Finalidade", data.purpose_display],
              ["Status", data.status_display],
              ["ID no fornecedor", data.provider_consulta_id || "—"],
              ["Preço", money(data.price_cents)],
              ["Cobrado do cliente", money(data.charged_cents)],
              ["Custo do fornecedor", money(data.provider_cost_cents)],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs font-semibold text-muted uppercase">{k}</dt>
                <dd className="font-medium break-words">{v || "—"}</dd>
              </div>
            ))}
          </dl>
          {data.message && <p className="rounded-lg bg-pale p-3">{data.message}</p>}
          {data.result ? (
            <pre className="max-h-96 overflow-auto rounded-lg bg-ink p-4 text-xs text-white">{JSON.stringify(data.result, null, 2)}</pre>
          ) : (
            ["success", "not_found"].includes(data.status) && (
              <div className="rounded-lg border border-yellow/40 bg-yellow-50 p-3">
                <p className="mb-2">O resultado contém dados pessoais. A visualização fica registrada na auditoria.</p>
                <Button size="sm" variant="secondary" onClick={() => setWithResult(true)}>
                  <Eye className="size-4" /> Ver resultado
                </Button>
              </div>
            )
          )}
        </div>
      )}
    </Modal>
  );
}

export function ConsultasTable({ organization }: { organization?: string }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <>
      <ResourceTable<ConsultaRow>
        endpoint="/consultas"
        queryKey={`consultas-${organization ?? "all"}`}
        fixedParams={organization ? { organization } : {}}
        searchPlaceholder="Placa, chassi, empresa ou ID no fornecedor"
        filters={[
          {
            name: "status",
            label: "Status",
            options: [
              ["", "Todos"],
              ["success", "Concluídas"],
              ["not_found", "Nada consta"],
              ["processing", "Processando"],
              ["failed", "Falharam"],
            ],
          },
          ...DATE_FILTERS,
        ]}
        columns={[
          { header: "Data", cell: (c) => dateTime(c.created_at), className: "whitespace-nowrap" },
          ...(organization ? [] : [{ header: "Empresa", cell: (c: ConsultaRow) => <OrgCell org={c.organization} /> }]),
          { header: "Produto", cell: (c) => c.product_name },
          { header: "Identificador", cell: (c) => <span className="font-mono">{c.input_type === "PLACA" ? plate(c.input_value) : c.input_value}</span> },
          { header: "Status", cell: (c) => <Badge tone={CONSULTA_TONE[c.status]}>{c.status_display}</Badge> },
          { header: "Cobrado", cell: (c) => money(c.charged_cents), className: "text-right whitespace-nowrap" },
          { header: "Custo", cell: (c) => money(c.provider_cost_cents), className: "text-right whitespace-nowrap" },
          {
            header: "",
            cell: (c) => (
              <Button size="sm" variant="ghost" onClick={() => setOpen(c.id)} aria-label="Ver detalhes">
                <Eye className="size-4" />
              </Button>
            ),
          },
        ]}
      />
      {open && <ConsultaModal id={open} onClose={() => setOpen(null)} />}
    </>
  );
}

export function ConsultasAdminPage() {
  return (
    <>
      <PageHeader title="Consultas" description="Todas as consultas realizadas na plataforma, com custo e cobrança." />
      <ConsultasTable />
    </>
  );
}

const NOTA_TONE: Record<string, "green" | "yellow" | "red" | "gray"> = { authorized: "green", queued: "yellow", processing: "yellow", rejected: "red", error: "red", canceled: "gray" };

export function NotasAdminPage() {
  return (
    <>
      <PageHeader title="Notas fiscais" description="NF-e emitidas por todas as empresas." />
      <ResourceTable<any>
        endpoint="/notas"
        searchPlaceholder="Chave, destinatário ou empresa"
        filters={[
          {
            name: "status",
            label: "Status",
            options: [
              ["", "Todos"],
              ["authorized", "Autorizadas"],
              ["rejected", "Rejeitadas"],
              ["error", "Erro"],
              ["canceled", "Canceladas"],
            ],
          },
          ...DATE_FILTERS,
        ]}
        columns={[
          { header: "Data", cell: (n) => dateTime(n.created_at), className: "whitespace-nowrap" },
          { header: "Empresa", cell: (n) => <OrgCell org={n.organization} /> },
          { header: "Número", cell: (n) => `${n.serie}/${n.numero}${n.ambiente === "2" ? " (hom.)" : ""}` },
          { header: "Operação", cell: (n) => n.tipo_display },
          { header: "Destinatário", cell: (n) => n.destinatario_nome },
          { header: "Valor", cell: (n) => money(n.total_cents), className: "text-right whitespace-nowrap" },
          {
            header: "Status",
            cell: (n) => (
              <>
                <Badge tone={NOTA_TONE[n.status]}>{n.status_display}</Badge>
                {n.message && n.status !== "authorized" && <p className="mt-1 max-w-64 text-xs text-muted">{n.cstat && `${n.cstat} · `}{n.message}</p>}
              </>
            ),
          },
        ]}
      />
    </>
  );
}

export function EstoqueAdminPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Estoque RENAVE" description="Veículos e operações de todas as empresas." />
      <ResourceTable<any>
        endpoint="/stock"
        title="Veículos"
        searchPlaceholder="Placa, RENAVAM ou empresa"
        filters={[
          {
            name: "state",
            label: "Situação",
            options: [
              ["", "Todas"],
              ["CONFIRMADO", "Em estoque"],
              ["SOLICITADO", "Entrada solicitada"],
              ["FINALIZADO", "Vendidos"],
              ["TRANSFERIDO", "Transferidos"],
              ["NEGADO", "Negados"],
              ["CANCELADO", "Cancelados"],
            ],
          },
        ]}
        columns={[
          { header: "Placa", cell: (v) => <span className="font-mono font-semibold">{plate(v.placa)}</span> },
          { header: "Empresa", cell: (v) => <OrgCell org={v.organization} /> },
          { header: "Cliente", cell: (v) => v.client_name ?? "Própria" },
          { header: "Situação", cell: (v) => v.state_display },
          { header: "Entrada", cell: (v) => `${date(v.entry_date)} · ${money(v.entry_value_cents)}` },
          { header: "Saída", cell: (v) => (v.exit_date ? `${date(v.exit_date)} · ${money(v.exit_value_cents)}` : "—") },
          { header: "ID RENAVE", cell: (v) => <span className="font-mono text-muted">{v.id_estoque ?? "—"}</span> },
        ]}
      />
      <ResourceTable<any>
        endpoint="/renave-operations"
        title="Operações"
        searchPlaceholder="Placa, mensagem ou empresa"
        filters={[
          {
            name: "success",
            label: "Resultado",
            options: [
              ["", "Todas"],
              ["true", "Concluídas"],
              ["false", "Recusadas"],
            ],
          },
          ...DATE_FILTERS,
        ]}
        columns={[
          { header: "Data", cell: (o) => dateTime(o.created_at), className: "whitespace-nowrap" },
          { header: "Empresa", cell: (o) => <OrgCell org={o.organization} /> },
          { header: "Operação", cell: (o) => o.kind_display },
          { header: "Placa", cell: (o) => (o.placa ? plate(o.placa) : "—") },
          { header: "Resultado", cell: (o) => (o.success ? <Badge tone="green">Concluída</Badge> : <Badge tone="red">Recusada</Badge>) },
          { header: "Mensagem", cell: (o) => <span className="text-xs text-muted">{o.message || "—"}</span> },
          { header: "Tarifa", cell: (o) => money(o.price_cents), className: "text-right" },
        ]}
      />
    </div>
  );
}

export function ComunicacoesAdminPage() {
  return (
    <>
      <PageHeader title="Comunicações de venda" description="Comunicações cadastradas e transmitidas por todas as empresas." />
      <ResourceTable<any>
        endpoint="/comunicacoes"
        searchPlaceholder="Placa, protocolo, comprador ou empresa"
        filters={DATE_FILTERS}
        columns={[
          { header: "Data", cell: (c) => dateTime(c.created_at), className: "whitespace-nowrap" },
          { header: "Empresa", cell: (c) => <OrgCell org={c.organization} /> },
          { header: "Placa", cell: (c) => <span className="font-mono">{plate(c.placa)}</span> },
          { header: "Comprador", cell: (c) => c.comprador_nome },
          { header: "Valor", cell: (c) => money(c.valor_cents), className: "text-right" },
          { header: "Protocolo", cell: (c) => <span className="font-mono text-muted">{c.protocolo || "—"}</span> },
          { header: "Situação", cell: (c) => c.situacao_display ?? "—" },
        ]}
      />
    </>
  );
}

export function CertificadosAdminPage() {
  return (
    <>
      <PageHeader title="Certificados digitais" description="Certificados A1 ativos, do vencimento mais próximo ao mais distante." />
      <ResourceTable<any>
        endpoint="/certificates"
        searchPlaceholder="Titular, documento ou empresa"
        filters={[
          {
            name: "expiring_in",
            label: "Vencimento",
            options: [
              ["", "Todos"],
              ["30", "Em até 30 dias"],
              ["60", "Em até 60 dias"],
            ],
          },
        ]}
        columns={[
          { header: "Titular", cell: (c) => <><span className="block font-semibold">{c.holder_name}</span><span className="font-mono text-xs text-muted">{document(c.holder_document)}</span></> },
          { header: "Empresa", cell: (c) => <OrgCell org={c.organization} /> },
          { header: "Cliente", cell: (c) => c.client_name ?? "—" },
          { header: "Vencimento", cell: (c) => <>{date(c.not_after)} <Badge tone={c.days_to_expire < 30 ? "red" : c.days_to_expire < 60 ? "yellow" : "green"}>{c.days_to_expire} dias</Badge></> },
          { header: "Integração RENAVE", cell: (c) => (c.carven_synced_at ? <Badge tone="green">Sincronizado</Badge> : c.carven_sync_error ? <span className="text-xs text-red">{c.carven_sync_error}</span> : <Badge tone="yellow">Pendente</Badge>) },
        ]}
      />
    </>
  );
}

