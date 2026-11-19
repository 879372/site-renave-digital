import { useQuery } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Modal, PageHeader, Spinner } from "@/components/ui";
import { dateTime } from "@/lib/format";

import { adminApi } from "../api";
import { DATE_FILTERS, OrgCell, ResourceTable } from "../components";

const PROVIDERS: [string, string][] = [
  ["", "Todos"],
  ["buscars", "BusCars (consultas)"],
  ["carven", "Carven (RENAVE e comunicação)"],
  ["geranet", "Geranet (NF-e)"],
];

function CallModal({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, isLoading } = useQuery({ queryKey: ["admin", "call", id], queryFn: () => adminApi(`/integration-calls/${id}`) });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="Chamada à integração" description="Corpos com dados sensíveis já chegam mascarados." wide>
      {isLoading || !data ? (
        <Spinner />
      ) : (
        <div className="space-y-3 text-sm">
          <p>
            <strong>{data.method}</strong> <span className="font-mono">{data.path}</span> · HTTP {data.status_code ?? "—"} · {data.duration_ms} ms · request id{" "}
            <span className="font-mono">{data.request_id}</span>
          </p>
          {data.error && <p className="rounded-lg bg-red-50 p-3 text-red">{data.error}</p>}
          <p className="font-semibold">Envio</p>
          <pre className="max-h-60 overflow-auto rounded-lg bg-ink p-3 text-xs text-white">{JSON.stringify(data.request_body, null, 2) ?? "—"}</pre>
          <p className="font-semibold">Resposta</p>
          <pre className="max-h-60 overflow-auto rounded-lg bg-ink p-3 text-xs text-white">{JSON.stringify(data.response_body, null, 2) ?? "—"}</pre>
        </div>
      )}
    </Modal>
  );
}

export function IntegracoesPage() {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="space-y-6">
      <PageHeader title="Integrações" description="Cada chamada feita aos provedores, com status, tempo de resposta e erro." />
      <ResourceTable<any>
        endpoint="/integration-calls"
        title="Chamadas"
        searchPlaceholder="Caminho, erro ou request id"
        filters={[
          { name: "provider", label: "Provedor", options: PROVIDERS },
          {
            name: "success",
            label: "Resultado",
            options: [
              ["", "Todos"],
              ["true", "Sucesso"],
              ["false", "Erro"],
            ],
          },
          ...DATE_FILTERS,
        ]}
        columns={[
          { header: "Data", cell: (c) => dateTime(c.created_at), className: "whitespace-nowrap" },
          { header: "Provedor", cell: (c) => <span className="capitalize">{c.provider}</span> },
          { header: "Empresa", cell: (c) => <OrgCell org={c.organization} /> },
          { header: "Chamada", cell: (c) => <span className="font-mono text-xs">{c.method} {c.path}</span> },
          { header: "Resultado", cell: (c) => (c.success ? <Badge tone="green">{c.status_code}</Badge> : <><Badge tone="red">{c.status_code ?? "falha"}</Badge><span className="mt-1 block max-w-60 text-xs text-muted">{c.error}</span></>) },
          { header: "Tempo", cell: (c) => `${c.duration_ms} ms`, className: "text-right whitespace-nowrap" },
          {
            header: "",
            cell: (c) => (
              <Button size="sm" variant="ghost" aria-label="Ver detalhes" onClick={() => setOpen(c.id)}>
                <Eye className="size-4" />
              </Button>
            ),
          },
        ]}
      />
      <ResourceTable<any>
        endpoint="/webhooks"
        title="Avisos recebidos (webhooks)"
        searchPlaceholder="ID da entrega ou evento"
        filters={DATE_FILTERS}
        columns={[
          { header: "Recebido em", cell: (w) => dateTime(w.received_at) },
          { header: "Provedor", cell: (w) => <span className="capitalize">{w.provider}</span> },
          { header: "Evento", cell: (w) => <span className="font-mono text-xs">{w.event}</span> },
          { header: "Entrega", cell: (w) => <span className="font-mono text-xs text-muted">{w.delivery_id}</span> },
        ]}
      />
      {open !== null && <CallModal id={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

export function AuditoriaAdminPage() {
  const [open, setOpen] = useState<any | null>(null);
  return (
    <>
      <PageHeader title="Auditoria" description="Registro imutável de todas as ações sensíveis na plataforma e neste painel." />
      <ResourceTable<any>
        endpoint="/audit"
        searchPlaceholder="Ação, e-mail, IP ou request id"
        filters={[
          {
            name: "action",
            label: "Área",
            options: [
              ["", "Todas"],
              ["admin.", "Painel administrativo"],
              ["auth.", "Acessos"],
              ["consulta.", "Consultas"],
              ["renave.", "RENAVE"],
              ["fiscal.", "Notas fiscais"],
              ["wallet.", "Carteira"],
              ["privacy.", "LGPD"],
              ["certificate.", "Certificados"],
            ],
          },
          ...DATE_FILTERS,
        ]}
        columns={[
          { header: "Data", cell: (e) => dateTime(e.created_at), className: "whitespace-nowrap" },
          { header: "Ação", cell: (e) => <span className="font-mono text-xs font-semibold">{e.action}</span> },
          { header: "Quem", cell: (e) => (e.actor ? <><span className="block">{e.actor.name}</span><span className="text-xs text-muted">{e.actor.email}</span></> : "—") },
          { header: "Empresa", cell: (e) => <OrgCell org={e.organization} /> },
          { header: "IP", cell: (e) => <span className="font-mono text-xs">{e.ip ?? "—"}</span> },
          {
            header: "",
            cell: (e) => (
              <Button size="sm" variant="ghost" aria-label="Ver detalhes" onClick={() => setOpen(e)}>
                <Eye className="size-4" />
              </Button>
            ),
          },
        ]}
      />
      {open && (
        <Modal open onOpenChange={(o) => !o && setOpen(null)} title={open.action} wide>
          <dl className="mb-3 grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-muted uppercase">Alvo</dt>
              <dd className="font-mono text-xs">{open.target_type ? `${open.target_type} ${open.target_id}` : "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted uppercase">Request id</dt>
              <dd className="font-mono text-xs">{open.request_id || "—"}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs text-muted uppercase">Navegador</dt>
              <dd className="text-xs break-all">{open.user_agent || "—"}</dd>
            </div>
          </dl>
          <pre className="max-h-72 overflow-auto rounded-lg bg-ink p-3 text-xs text-white">{JSON.stringify(open.metadata, null, 2)}</pre>
        </Modal>
      )}
    </>
  );
}
