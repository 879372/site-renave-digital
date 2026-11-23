/** Peças compartilhadas pelos módulos de gestão: abas, paginação, campo de dinheiro e seletores. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { document, maskDocument, maskMoney, maskPhone, money, onlyDigits, parseMoney } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

import { Button, Field, Input, Modal } from "./ui";

export type Paged<T> = { count: number; next: string | null; previous: string | null; results: T[] };

/** Abas simples controladas pela URL (?aba=). */
export function Tabs({ tabs, value, onChange }: { tabs: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="mb-5 flex gap-1 overflow-x-auto border-b border-line" role="tablist">
      {tabs.map(([key, label]) => (
        <button
          key={key}
          role="tab"
          aria-selected={value === key}
          onClick={() => onChange(key)}
          className={clsx(
            "-mb-px border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition",
            value === key ? "border-brand text-ink" : "border-transparent text-muted hover:text-ink",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function useTab(defaultTab: string) {
  const initial = new URLSearchParams(window.location.search).get("aba") || defaultTab;
  const [tab, setTab] = useState(initial);
  const change = (v: string) => {
    setTab(v);
    const url = new URL(window.location.href);
    url.searchParams.set("aba", v);
    window.history.replaceState(null, "", url);
  };
  return [tab, change] as const;
}

export function Pager({ page, data, onPage }: { page: number; data?: Paged<unknown>; onPage: (p: number) => void }) {
  if (!data || (!data.next && !data.previous)) return null;
  return (
    <div className="mt-4 flex items-center justify-between text-sm text-muted">
      <span>{data.count} registros</span>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" disabled={!data.previous} onClick={() => onPage(page - 1)} aria-label="Página anterior">
          <ChevronLeft className="size-4" />
        </Button>
        <span className="self-center">Página {page}</span>
        <Button size="sm" variant="secondary" disabled={!data.next} onClick={() => onPage(page + 1)} aria-label="Próxima página">
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}

/** Campo de valor em reais: mostra "1.234,56" e devolve centavos. */
export function MoneyInput({ value, onChange, id, placeholder = "0,00", ...rest }: { value: number | null | undefined; onChange: (cents: number) => void; id?: string; placeholder?: string; disabled?: boolean; className?: string }) {
  const [text, setText] = useState(value ? maskMoney(String(value)) : "");
  useEffect(() => {
    if ((value ?? 0) !== parseMoney(text)) setText(value ? maskMoney(String(value)) : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <div className="relative">
      <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-sm text-muted">R$</span>
      <Input
        id={id}
        inputMode="decimal"
        placeholder={placeholder}
        className={clsx("pl-9 text-right tabular", rest.className)}
        disabled={rest.disabled}
        value={text}
        onChange={(e) => {
          const masked = maskMoney(e.target.value);
          setText(masked);
          onChange(parseMoney(masked));
        }}
      />
    </div>
  );
}

export function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div className="relative w-full sm:w-72">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" aria-hidden />
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="h-9 pl-9" aria-label={placeholder} />
    </div>
  );
}

export function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

type PessoaRef = { id: string; nome: string; documento: string };

/** Escolhe cliente/fornecedor com busca e permite cadastrar na hora. */
export function PessoaPicker({ value, onChange, label = "Cliente", tipo, required }: { value: PessoaRef | null; onChange: (p: PessoaRef | null) => void; label?: string; tipo?: "cliente" | "fornecedor"; required?: boolean }) {
  const { organization } = useAuth();
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const q = useDebounced(term);
  const list = useQuery({
    queryKey: ["pessoas-choices", organization?.id, q, tipo],
    queryFn: () => api<PessoaRef[]>("/pessoas/choices", { params: { search: q, tipo } }),
    enabled: open,
  });
  return (
    <Field label={label + (required ? "" : " (opcional)")}>
      {value ? (
        <div className="flex h-10 items-center justify-between rounded-lg border border-line bg-white px-3 text-sm">
          <span className="truncate">
            {value.nome} {value.documento && <span className="text-muted">· {document(value.documento)}</span>}
          </span>
          <button type="button" className="text-xs font-medium text-brand" onClick={() => onChange(null)}>
            Trocar
          </button>
        </div>
      ) : (
        <div className="relative">
          <Input
            placeholder="Buscar por nome, CPF/CNPJ ou telefone"
            value={term}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            onChange={(e) => setTerm(e.target.value)}
          />
          {open && (
            <div className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-line bg-white shadow-lg">
              {list.data?.map((p) => (
                <button key={p.id} type="button" className="block w-full px-3 py-2 text-left text-sm hover:bg-pale" onMouseDown={() => onChange(p)}>
                  {p.nome} <span className="text-muted">{p.documento && document(p.documento)}</span>
                </button>
              ))}
              {list.data?.length === 0 && <p className="px-3 py-2 text-sm text-muted">Nenhum cadastro encontrado.</p>}
              <button type="button" className="flex w-full items-center gap-2 border-t border-line px-3 py-2 text-left text-sm font-medium text-brand hover:bg-pale" onMouseDown={() => setCreating(true)}>
                <Plus className="size-4" /> Cadastrar {term ? `"${term}"` : "novo"}
              </button>
            </div>
          )}
        </div>
      )}
      <PessoaModal
        open={creating}
        onOpenChange={setCreating}
        initialName={term}
        tipo={tipo}
        onSaved={(p) => {
          onChange({ id: p.id, nome: p.nome, documento: p.documento });
          setCreating(false);
        }}
      />
    </Field>
  );
}

export type Pessoa = {
  id: string;
  documento: string;
  nome: string;
  email: string;
  telefone: string;
  data_nascimento: string | null;
  rg_ie: string;
  cep: string;
  logradouro: string;
  numero: string;
  complemento: string;
  bairro: string;
  cidade: string;
  cidade_ibge: string;
  uf: string;
  is_cliente: boolean;
  is_fornecedor: boolean;
  observacoes: string;
};

const EMPTY: Omit<Pessoa, "id"> = {
  documento: "",
  nome: "",
  email: "",
  telefone: "",
  data_nascimento: null,
  rg_ie: "",
  cep: "",
  logradouro: "",
  numero: "",
  complemento: "",
  bairro: "",
  cidade: "",
  cidade_ibge: "",
  uf: "",
  is_cliente: true,
  is_fornecedor: false,
  observacoes: "",
};

export function PessoaModal({ open, onOpenChange, pessoa, initialName, tipo, onSaved }: { open: boolean; onOpenChange: (v: boolean) => void; pessoa?: Pessoa | null; initialName?: string; tipo?: "cliente" | "fornecedor"; onSaved?: (p: Pessoa) => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<Omit<Pessoa, "id">>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (open) {
      setForm(pessoa ? { ...EMPTY, ...pessoa } : { ...EMPTY, nome: initialName ?? "", is_fornecedor: tipo === "fornecedor", is_cliente: tipo !== "fornecedor" });
      setErrors({});
    }
  }, [open, pessoa, initialName, tipo]);
  const set = (k: keyof typeof form, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const save = useMutation({
    mutationFn: () => api<Pessoa>(pessoa ? `/pessoas/${pessoa.id}` : "/pessoas/", { method: pessoa ? "PATCH" : "POST", body: { ...form, documento: onlyDigits(form.documento), telefone: onlyDigits(form.telefone) } }),
    onSuccess: (p) => {
      toast.success(pessoa ? "Cadastro atualizado" : "Cadastro criado");
      qc.invalidateQueries({ queryKey: ["pessoas"] });
      qc.invalidateQueries({ queryKey: ["pessoas-choices"] });
      onSaved?.(p);
      onOpenChange(false);
    },
    onError: (e: any) => {
      const f: Record<string, string> = {};
      Object.entries(e?.fields ?? {}).forEach(([k, v]) => (f[k] = Array.isArray(v) ? String(v[0]) : String(v)));
      setErrors(f);
      handleApiError(e);
    },
  });
  const lookupCep = async (cep: string) => {
    if (onlyDigits(cep).length !== 8) return;
    try {
      const r = await api<any>(`/lookup/cep/${onlyDigits(cep)}`);
      setForm((f) => ({ ...f, logradouro: r.street || f.logradouro, bairro: r.district || f.bairro, cidade: r.city || f.cidade, uf: r.uf || f.uf, cidade_ibge: r.city_ibge || f.cidade_ibge }));
    } catch {
      /* CEP não encontrado: preenche à mão */
    }
  };
  const text = (k: keyof typeof form, label: string, extra: Partial<{ placeholder: string; mask: (v: string) => string; className: string; onBlur: () => void }> = {}) => (
    <Field label={label} htmlFor={`p-${k}`} error={errors[k]} className={extra.className}>
      <Input id={`p-${k}`} value={(form[k] as string) ?? ""} placeholder={extra.placeholder} onBlur={extra.onBlur} onChange={(e) => set(k, extra.mask ? extra.mask(e.target.value) : e.target.value)} aria-invalid={!!errors[k]} />
    </Field>
  );
  return (
    <Modal open={open} onOpenChange={onOpenChange} title={pessoa ? "Editar cadastro" : "Novo cadastro"} wide>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          {text("nome", "Nome / razão social", { className: "sm:col-span-2" })}
          {text("documento", "CPF / CNPJ", { mask: maskDocument })}
          {text("rg_ie", "RG / inscrição estadual")}
          {text("telefone", "Telefone / WhatsApp", { mask: maskPhone })}
          {text("email", "E-mail")}
          {text("cep", "CEP", { onBlur: () => lookupCep(form.cep) })}
          {text("logradouro", "Endereço")}
          {text("numero", "Número")}
          {text("complemento", "Complemento")}
          {text("bairro", "Bairro")}
          <div className="grid grid-cols-[1fr_80px] gap-3">
            {text("cidade", "Cidade")}
            {text("uf", "UF", { mask: (v) => v.toUpperCase().slice(0, 2) })}
          </div>
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" className="size-4 accent-brand" checked={form.is_cliente} onChange={(e) => set("is_cliente", e.target.checked)} /> Cliente
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="size-4 accent-brand" checked={form.is_fornecedor} onChange={(e) => set("is_fornecedor", e.target.checked)} /> Fornecedor
          </label>
        </div>
        <p className="text-xs text-muted">Para emitir nota fiscal e dar saída no RENAVE, o cadastro precisa de CPF/CNPJ e endereço completo.</p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="submit" loading={save.isPending}>
            Salvar
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function Money({ cents, className }: { cents: number | null | undefined; className?: string }) {
  return <span className={clsx("tabular whitespace-nowrap", className)}>{money(cents)}</span>;
}

export function Profit({ cents }: { cents: number | null | undefined }) {
  if (cents == null) return <span className="text-muted">—</span>;
  return <span className={clsx("tabular font-medium whitespace-nowrap", cents >= 0 ? "text-green" : "text-red")}>{money(cents)}</span>;
}

export function KV({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <span className="text-muted">{label}</span>
      <span className="text-right font-medium">{children}</span>
    </div>
  );
}

export function useMembers() {
  const { organization } = useAuth();
  return useQuery({ queryKey: ["vendedores", organization?.id], queryFn: () => api<{ id: string; name: string; role: string }[]>("/vendas/vendedores"), staleTime: 300_000 });
}
