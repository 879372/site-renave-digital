import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { MessageCircle, Phone, Plus, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Link } from "wouter";

import { MoneyInput, Tabs, useMembers, useTab, type Paged } from "@/components/kit";
import { PlanGate } from "@/components/PlanGate";
import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, maskPhone, money, onlyDigits } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

type Lead = {
  id: string;
  name: string;
  phone: string;
  email: string;
  source: string;
  source_display: string;
  stage: string;
  stage_display: string;
  vehicle: string | null;
  vehicle_title: string | null;
  interest: string;
  budget_cents: number | null;
  owner: string | null;
  owner_name: string | null;
  pessoa: string | null;
  lost_reason: string;
  message: string;
  open_tasks: number;
  created_at: string;
};

const STAGES: [string, string][] = [["novo", "Novos"], ["contato", "Em contato"], ["visita", "Visita"], ["proposta", "Proposta"], ["ganho", "Vendidos"], ["perdido", "Perdidos"]];
const SOURCES: [string, string][] = [["loja", "Loja física"], ["site", "Site da loja"], ["whatsapp", "WhatsApp"], ["instagram", "Instagram"], ["facebook", "Facebook"], ["olx", "OLX"], ["webmotors", "Webmotors"], ["mercadolivre", "Mercado Livre"], ["icarros", "iCarros"], ["indicacao", "Indicação"], ["outro", "Outro"]];

export function LeadsPage() {
  const [tab, setTab] = useTab("funil");
  return (
    <>
      <PageHeader title="Leads" description="Funil de atendimento: de onde vem cada interessado e em que etapa está." />
      <PlanGate feature="crm" title="CRM e leads">
        <Tabs tabs={[["funil", "Funil"], ["tarefas", "Retornos"]]} value={tab} onChange={setTab} />
        {tab === "funil" ? <Funil /> : <Tarefas />}
      </PlanGate>
    </>
  );
}

function Funil() {
  const { organization, can } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState<Lead | null>(null);
  const [creating, setCreating] = useState(false);
  const [drag, setDrag] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["leads", organization?.id], queryFn: () => api<Paged<Lead>>("/crm/leads", { params: { page_size: 100 } }) });
  const move = useMutation({
    mutationFn: ({ id, stage, lost_reason }: { id: string; stage: string; lost_reason?: string }) => api(`/crm/leads/${id}/move`, { body: { stage, lost_reason } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["leads"] }),
    onError: (e) => handleApiError(e),
  });
  const onDrop = (stage: string) => {
    if (!drag) return;
    const lead = q.data?.results.find((l) => l.id === drag);
    if (!lead || lead.stage === stage) return;
    let lost: string | undefined;
    if (stage === "perdido") {
      lost = prompt("Motivo da perda (preço, crédito negado, comprou em outro lugar…)") ?? undefined;
      if (!lost) return;
    }
    qc.setQueryData(["leads", organization?.id], (old: Paged<Lead> | undefined) => old && { ...old, results: old.results.map((l) => (l.id === drag ? { ...l, stage } : l)) });
    move.mutate({ id: drag, stage, lost_reason: lost });
    setDrag(null);
  };
  if (q.isLoading) return <Spinner />;
  const leads = q.data?.results ?? [];
  return (
    <>
      {can("vendas.operate") && <div className="mb-4 flex justify-end"><Button onClick={() => setCreating(true)}><Plus className="size-4" /> Novo lead</Button></div>}
      <div className="grid auto-cols-[260px] grid-flow-col gap-3 overflow-x-auto pb-3">
        {STAGES.map(([stage, label]) => {
          const items = leads.filter((l) => l.stage === stage);
          return (
            <section key={stage} onDragOver={(e) => e.preventDefault()} onDrop={() => onDrop(stage)} className={clsx("flex min-h-64 flex-col rounded-xl bg-pale/70 p-2", drag && "ring-1 ring-line")}>
              <header className="mb-2 flex items-center justify-between px-1 text-sm font-semibold">{label}<span className="text-xs font-normal text-muted">{items.length}</span></header>
              <div className="space-y-2">
                {items.map((l) => (
                  <article key={l.id} draggable onDragStart={() => setDrag(l.id)} onDragEnd={() => setDrag(null)} onClick={() => setOpen(l)} className="cursor-pointer rounded-lg border border-line bg-white p-3 text-sm shadow-sm hover:border-brand/50">
                    <p className="font-medium">{l.name}</p>
                    {l.vehicle_title && <p className="truncate text-xs text-muted">{l.vehicle_title}</p>}
                    <div className="mt-2 flex items-center justify-between text-xs text-muted">
                      <span>{l.source_display}</span>
                      {l.open_tasks > 0 && <Badge tone="yellow">{l.open_tasks} retorno</Badge>}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </div>
      {!leads.length && <Empty title="Nenhum lead ainda">Leads do site da loja entram aqui sozinhos. Cadastre também quem chega pela loja ou WhatsApp.</Empty>}
      <LeadForm open={creating} onOpenChange={setCreating} />
      <LeadDrawer lead={open} onClose={() => setOpen(null)} />
    </>
  );
}

function LeadForm({ open, onOpenChange }: { open: boolean; onOpenChange: (b: boolean) => void }) {
  const qc = useQueryClient();
  const members = useMembers();
  const [f, setF] = useState({ name: "", phone: "", email: "", source: "loja", interest: "", budget_cents: 0, owner: "" });
  const m = useMutation({
    mutationFn: () => api("/crm/leads", { body: { ...f, phone: onlyDigits(f.phone), owner: f.owner || null, budget_cents: f.budget_cents || null } }),
    onSuccess: () => { toast.success("Lead criado"); qc.invalidateQueries({ queryKey: ["leads"] }); onOpenChange(false); setF({ ...f, name: "", phone: "", email: "", interest: "" }); },
    onError: (e) => handleApiError(e),
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Novo lead">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Field label="Nome" htmlFor="ld-n"><Input id="ld-n" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Telefone / WhatsApp" htmlFor="ld-p"><Input id="ld-p" value={f.phone} onChange={(e) => setF({ ...f, phone: maskPhone(e.target.value) })} /></Field>
          <Field label="E-mail" htmlFor="ld-e"><Input id="ld-e" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="Origem" htmlFor="ld-s"><Select id="ld-s" value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>{SOURCES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
          <Field label="Responsável" htmlFor="ld-o"><Select id="ld-o" value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })}><option value="">Eu</option>{members.data?.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</Select></Field>
        </div>
        <Field label="Interesse" htmlFor="ld-i"><Input id="ld-i" value={f.interest} onChange={(e) => setF({ ...f, interest: e.target.value })} placeholder="SUV até 80 mil, aceita troca…" /></Field>
        <Field label="Orçamento"><MoneyInput value={f.budget_cents} onChange={(c) => setF({ ...f, budget_cents: c })} /></Field>
        <Button type="submit" className="w-full" loading={m.isPending}>Salvar</Button>
      </form>
    </Modal>
  );
}

function LeadDrawer({ lead, onClose }: { lead: Lead | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [kind, setKind] = useState("nota");
  const [task, setTask] = useState({ title: "", due_at: "" });
  const history = useQuery({ queryKey: ["lead-history", lead?.id], queryFn: () => api<any[]>(`/crm/leads/${lead!.id}/interactions`), enabled: !!lead });
  const tasks = useQuery({ queryKey: ["tarefas", "lead", lead?.id], queryFn: () => api<Paged<any>>("/crm/tarefas", { params: { lead: lead!.id } }), enabled: !!lead });
  const note = useMutation({
    mutationFn: () => api(`/crm/leads/${lead!.id}/interactions`, { body: { kind, text } }),
    onSuccess: () => { setText(""); qc.invalidateQueries({ queryKey: ["lead-history", lead?.id] }); qc.invalidateQueries({ queryKey: ["leads"] }); },
    onError: (e) => handleApiError(e),
  });
  const addTask = useMutation({
    mutationFn: () => api("/crm/tarefas", { body: { lead: lead!.id, title: task.title, due_at: new Date(task.due_at).toISOString() } }),
    onSuccess: () => { setTask({ title: "", due_at: "" }); qc.invalidateQueries({ queryKey: ["tarefas"] }); qc.invalidateQueries({ queryKey: ["leads"] }); },
    onError: (e) => handleApiError(e),
  });
  const convert = useMutation({ mutationFn: () => api<{ pessoa_id: string }>(`/crm/leads/${lead!.id}/convert`, { body: {} }), onSuccess: () => { toast.success("Cliente cadastrado"); qc.invalidateQueries({ queryKey: ["leads"] }); } });
  if (!lead) return null;
  const wa = onlyDigits(lead.phone);
  return (
    <Modal open={!!lead} onOpenChange={(v) => !v && onClose()} title={lead.name} description={`${lead.source_display} · ${lead.stage_display}`} wide>
      <div className="grid gap-6 md:grid-cols-[1fr_260px]">
        <div className="space-y-4">
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); note.mutate(); }}>
            <div className="flex gap-2">
              <Select value={kind} onChange={(e) => setKind(e.target.value)} className="w-36"><option value="nota">Anotação</option><option value="ligacao">Ligação</option><option value="whatsapp">WhatsApp</option><option value="visita">Visita</option></Select>
              <Input required value={text} onChange={(e) => setText(e.target.value)} placeholder="O que foi conversado" />
              <Button type="submit" loading={note.isPending}>Registrar</Button>
            </div>
          </form>
          <ul className="max-h-72 space-y-2 overflow-y-auto text-sm">
            {history.data?.map((h, i) => <li key={i} className="rounded-lg bg-pale p-2"><p className="text-xs text-muted">{h.kind_display} · {h.user_name ?? "Sistema"} · {dateTime(h.created_at)}</p><p>{h.text}</p></li>)}
            {lead.message && <li className="rounded-lg bg-pale p-2"><p className="text-xs text-muted">Mensagem do contato</p><p>{lead.message}</p></li>}
          </ul>
        </div>
        <aside className="space-y-4 text-sm">
          <div className="space-y-1">
            {lead.phone && <p className="flex items-center gap-2"><Phone className="size-4 text-muted" /> {maskPhone(lead.phone)}</p>}
            {wa && <a className="flex items-center gap-2 font-medium text-brand" href={`https://wa.me/55${wa}`} target="_blank" rel="noopener noreferrer"><MessageCircle className="size-4" /> Abrir WhatsApp</a>}
            {lead.email && <p>{lead.email}</p>}
            {lead.vehicle_title && <p>Interesse: <Link href={`/veiculos/${lead.vehicle}`} className="text-brand">{lead.vehicle_title}</Link></p>}
            {lead.interest && <p className="text-muted">{lead.interest}</p>}
            {lead.budget_cents ? <p>Orçamento: {money(lead.budget_cents)}</p> : null}
            <p className="text-muted">Responsável: {lead.owner_name ?? "—"}</p>
          </div>
          {!lead.pessoa ? <Button size="sm" variant="secondary" onClick={() => convert.mutate()}><UserPlus className="size-4" /> Cadastrar como cliente</Button> : <Link href={`/vendas/nova`} className="block font-medium text-brand">Criar proposta →</Link>}
          <div>
            <h3 className="mb-2 font-semibold">Retornos</h3>
            <ul className="mb-2 space-y-1">{tasks.data?.results.map((t) => <li key={t.id} className={t.done_at ? "text-muted line-through" : ""}>{t.title} · {dateTime(t.due_at)}</li>)}</ul>
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); addTask.mutate(); }}>
              <Input required placeholder="Ligar de volta" value={task.title} onChange={(e) => setTask({ ...task, title: e.target.value })} />
              <Input required type="datetime-local" value={task.due_at} onChange={(e) => setTask({ ...task, due_at: e.target.value })} />
              <Button size="sm" type="submit" variant="secondary" className="w-full">Agendar retorno</Button>
            </form>
          </div>
        </aside>
      </div>
    </Modal>
  );
}

function Tarefas() {
  const { organization } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["tarefas", organization?.id, "open"], queryFn: () => api<Paged<any>>("/crm/tarefas", { params: { open: 1 } }) });
  const done = useMutation({ mutationFn: (id: string) => api(`/crm/tarefas/${id}`, { method: "PATCH", body: { done: true } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["tarefas"] }) });
  return (
    <Card title="Retornos agendados">
      {q.isLoading ? <Spinner /> : !q.data?.results.length ? <Empty title="Nenhum retorno pendente" /> : (
        <Table head={["Quando", "Tarefa", "Lead", "Responsável", ""]}>
          {q.data.results.map((t) => (
            <tr key={t.id}>
              <td className={clsx("px-5 py-3 whitespace-nowrap", new Date(t.due_at) < new Date() && "text-red")}>{dateTime(t.due_at)}</td>
              <td className="px-5 py-3">{t.title}</td>
              <td className="px-5 py-3">{t.lead_name ?? "—"}</td>
              <td className="px-5 py-3 text-muted">{t.owner_name ?? "—"}</td>
              <td className="px-5 py-3 text-right"><Button size="sm" variant="secondary" onClick={() => done.mutate(t.id)}>Concluir</Button></td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
