import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileSignature, Printer } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Link, useParams } from "wouter";

import { Pager, Tabs, useTab, type Paged } from "@/components/kit";
import { PlanGate } from "@/components/PlanGate";
import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Spinner, Table, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBilling } from "@/lib/billing";
import { date } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

type Modelo = { id: string; kind: string; kind_display: string; title: string; body: string; is_active: boolean };
type Documento = { id: string; kind_display: string; title: string; content: string; venda_id: string | null; pessoa_name: string | null; signature_status: string; signature_display: string; signature_links: { name: string; url: string }[]; signed_file_url: string; created_at: string };

const VARS = "{{loja.razao_social}} {{loja.cnpj}} {{loja.endereco}} {{loja.cidade}} {{cliente.nome}} {{cliente.documento}} {{cliente.endereco}} {{veiculo.descricao}} {{veiculo.placa}} {{veiculo.chassi}} {{veiculo.renavam}} {{veiculo.km}} {{veiculo.preco}} {{venda.valor}} {{venda.valor_extenso}} {{venda.pagamentos}} {{data.hoje}}";

export function ContratosPage() {
  const [tab, setTab] = useTab("documentos");
  return (
    <>
      <PageHeader title="Contratos" description="Documentos gerados nas vendas e os modelos da loja." />
      <PlanGate feature="contratos" title="Contratos">
        <Tabs tabs={[["documentos", "Documentos gerados"], ["modelos", "Modelos"]]} value={tab} onChange={setTab} />
        {tab === "documentos" ? <Documentos /> : <Modelos />}
      </PlanGate>
    </>
  );
}

function Documentos() {
  const { organization } = useAuth();
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["documentos", organization?.id, page], queryFn: () => api<Paged<Documento>>("/contratos/documentos", { params: { page } }) });
  return (
    <Card>
      {q.isLoading ? <Spinner /> : !q.data?.results.length ? <Empty title="Nenhum documento gerado" icon={<FileSignature />}>Gere contratos e recibos pela tela da venda.</Empty> : (
        <>
          <Table head={["Data", "Documento", "Pessoa", "Assinatura", ""]}>
            {q.data.results.map((d) => (
              <tr key={d.id}>
                <td className="px-5 py-3 text-muted">{date(d.created_at)}</td>
                <td className="px-5 py-3">{d.title}</td>
                <td className="px-5 py-3">{d.pessoa_name ?? "—"}</td>
                <td className="px-5 py-3">{d.signature_status ? <Badge tone={d.signature_status === "signed" ? "green" : d.signature_status === "refused" ? "red" : "yellow"}>{d.signature_display}</Badge> : <span className="text-muted">—</span>}</td>
                <td className="px-5 py-3 text-right"><Link href={`/contratos/${d.id}`} className="font-medium text-brand">Abrir</Link></td>
              </tr>
            ))}
          </Table>
          <Pager page={page} data={q.data} onPage={setPage} />
        </>
      )}
    </Card>
  );
}

function Modelos() {
  const { organization, can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["modelos", organization?.id], queryFn: () => api<Modelo[]>("/contratos/modelos") });
  const [edit, setEdit] = useState<Modelo | null>(null);
  const save = useMutation({
    mutationFn: (m: Modelo) => api(`/contratos/modelos/${m.id}`, { method: "PATCH", body: { title: m.title, body: m.body, is_active: m.is_active } }),
    onSuccess: () => { toast.success("Modelo salvo"); setEdit(null); qc.invalidateQueries({ queryKey: ["modelos"] }); },
    onError: (e) => handleApiError(e),
  });
  return (
    <Card description="Revise os modelos com seu advogado. As variáveis entre chaves são preenchidas com os dados da venda.">
      {q.isLoading ? <Spinner /> : (
        <ul className="divide-y divide-line">
          {q.data?.map((m) => (
            <li key={m.id} className="flex items-center justify-between py-3 text-sm">
              <span><span className="font-medium">{m.title}</span> <span className="text-muted">· {m.kind_display}</span> {!m.is_active && <Badge>inativo</Badge>}</span>
              {can("org.manage") && <Button size="sm" variant="secondary" onClick={() => setEdit(m)}>Editar</Button>}
            </li>
          ))}
        </ul>
      )}
      <Modal open={!!edit} onOpenChange={(v) => !v && setEdit(null)} title="Editar modelo" wide>
        {edit && (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(edit); }}>
            <Field label="Título" htmlFor="m-t"><Input placeholder="Contrato de compra e venda" id="m-t" value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
            <Field label="Texto" htmlFor="m-b" hint={`Variáveis: ${VARS}`}><Textarea placeholder="Texto do contrato. Use variáveis como {{cliente.nome}} e {{veiculo.placa}}." id="m-b" rows={18} className="font-mono text-xs" value={edit.body} onChange={(e) => setEdit({ ...edit, body: e.target.value })} /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-brand" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /> Ativo</label>
            <Button type="submit" loading={save.isPending}>Salvar modelo</Button>
          </form>
        )}
      </Modal>
    </Card>
  );
}

export function DocumentoPage() {
  const { id } = useParams<{ id: string }>();
  const { has } = useBilling();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["documento", id], queryFn: () => api<Documento>(`/contratos/documentos/${id}`) });
  const [content, setContent] = useState("");
  const [editing, setEditing] = useState(false);
  const [signOpen, setSignOpen] = useState(false);
  const [signers, setSigners] = useState([{ name: "", email: "" }]);
  useEffect(() => { if (q.data) setContent(q.data.content); }, [q.data]);
  const save = useMutation({
    mutationFn: () => api<Documento>(`/contratos/documentos/${id}`, { method: "PATCH", body: { content } }),
    onSuccess: (d) => { qc.setQueryData(["documento", id], d); setEditing(false); toast.success("Documento salvo"); },
    onError: (e) => handleApiError(e),
  });
  const sign = useMutation({
    mutationFn: () => api<Documento>(`/contratos/documentos/${id}/sign`, { body: { signers: signers.filter((s) => s.name) } }),
    onSuccess: (d) => { qc.setQueryData(["documento", id], d); setSignOpen(false); toast.success("Enviado para assinatura"); },
    onError: (e) => handleApiError(e),
  });
  if (q.isLoading) return <Spinner />;
  const d = q.data;
  if (!d) return <Empty title="Documento não encontrado" />;
  const locked = ["pending", "signed"].includes(d.signature_status);
  return (
    <>
      <div className="no-print">
        <Link href={d.venda_id ? `/vendas/${d.venda_id}` : "/contratos"} className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Voltar</Link>
        <PageHeader title={d.title} action={
          <div className="flex flex-wrap gap-2">
            {d.signature_status && <Badge tone={d.signature_status === "signed" ? "green" : "yellow"}>{d.signature_display}</Badge>}
            {!locked && (editing ? <Button size="sm" onClick={() => save.mutate()} loading={save.isPending}>Salvar</Button> : <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>Editar texto</Button>)}
            {has("assinatura") && !locked && <Button size="sm" variant="secondary" onClick={() => setSignOpen(true)}><FileSignature className="size-4" /> Assinatura eletrônica</Button>}
            <Button size="sm" onClick={() => window.print()}><Printer className="size-4" /> Imprimir / PDF</Button>
          </div>
        } />
        {d.signature_links.length > 0 && <Card title="Links de assinatura" className="mb-4"><ul className="space-y-1 text-sm">{d.signature_links.map((s) => <li key={s.url}>{s.name}: <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-brand break-all">{s.url}</a></li>)}</ul>{d.signed_file_url && <a href={d.signed_file_url} target="_blank" rel="noopener noreferrer" className="mt-2 block font-medium text-brand">Baixar documento assinado</a>}</Card>}
      </div>
      {editing ? (
        <Textarea placeholder="Texto do documento" rows={30} className="font-mono text-xs" value={content} onChange={(e) => setContent(e.target.value)} />
      ) : (
        <article className="mx-auto max-w-3xl rounded-xl border border-line bg-white p-10 text-[13px] leading-6 whitespace-pre-wrap print:border-0 print:p-0">{d.content}</article>
      )}
      <Modal open={signOpen} onOpenChange={setSignOpen} title="Enviar para assinatura" description="Cada pessoa recebe um link para assinar pelo celular.">
        <div className="space-y-3">
          {signers.map((s, i) => (
            <div key={i} className="grid grid-cols-2 gap-2">
              <Input placeholder="Nome" value={s.name} onChange={(e) => setSigners(signers.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
              <Input placeholder="E-mail (opcional)" value={s.email} onChange={(e) => setSigners(signers.map((x, j) => (j === i ? { ...x, email: e.target.value } : x)))} />
            </div>
          ))}
          <Button size="sm" variant="ghost" onClick={() => setSigners([...signers, { name: "", email: "" }])}>+ Pessoa</Button>
          <Button className="w-full" onClick={() => sign.mutate()} loading={sign.isPending}>Enviar</Button>
        </div>
      </Modal>
    </>
  );
}
