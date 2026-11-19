import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { Badge, Button, Card, Field, Input, Modal, PageHeader, Select, Spinner, Textarea } from "@/components/ui";
import { maskMoney, money, parseMoney } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

import { adminApi } from "../api";

type Product = {
  id: number;
  code: string;
  sku: string;
  name: string;
  description: string;
  category: string;
  input_type: string;
  cost_cents: number;
  price_cents: number;
  margin_cents: number;
  is_async: boolean;
  is_active: boolean;
  is_featured: boolean;
  sort_order: number;
  highlights: string[];
};

const CATEGORIES: Record<string, string> = {
  completa: "Pacotes completos",
  restricoes: "Restrições e riscos",
  historico: "Histórico",
  preco: "Preço e FIPE",
  cadastro: "Dados cadastrais",
  debitos: "Débitos e documentos",
  empresa: "Empresas",
};
const INPUTS = ["PLACA", "CHASSI", "RENAVAM", "MOTOR", "CPF", "CNPJ"];

function ProductModal({ product, onClose }: { product: Product | null; onClose: () => void }) {
  const qc = useQueryClient();
  const form = useForm<Record<string, any>>({
    defaultValues: product
      ? { ...product, cost: maskMoney(String(product.cost_cents)), price: maskMoney(String(product.price_cents)), highlights_text: product.highlights.join("\n") }
      : { category: "cadastro", input_type: "PLACA", sort_order: 100, is_active: false },
  });
  const e = form.formState.errors as Record<string, { message?: string }>;
  const submit = form.handleSubmit(async (v) => {
    const body = {
      code: v.code,
      sku: v.sku,
      name: v.name,
      description: v.description ?? "",
      category: v.category,
      input_type: v.input_type,
      cost_cents: parseMoney(v.cost ?? ""),
      price_cents: parseMoney(v.price ?? ""),
      is_async: !!v.is_async,
      is_active: !!v.is_active,
      is_featured: !!v.is_featured,
      sort_order: Number(v.sort_order) || 100,
      highlights: String(v.highlights_text ?? "")
        .split("\n")
        .map((s: string) => s.trim())
        .filter(Boolean),
    };
    try {
      if (product) await adminApi(`/products/${product.id}`, { method: "PATCH", body });
      else await adminApi("/products", { body });
      toast.success(product ? "Produto atualizado." : "Produto criado.");
      qc.invalidateQueries({ queryKey: ["admin", "products"] });
      onClose();
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });
  const margin = parseMoney(form.watch("price") ?? "") - parseMoney(form.watch("cost") ?? "");
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={product ? `Editar ${product.name}` : "Novo produto"} wide>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2" noValidate>
        <Field label="Nome exibido" htmlFor="p-name" error={e.name?.message}>
          <Input id="p-name" placeholder="Ex.: Leilão" required {...form.register("name")} />
        </Field>
        <Field label="Código público" htmlFor="p-code" error={e.code?.message} hint="Aparece para o lojista. Letras minúsculas e hífen.">
          <Input id="p-code" placeholder="ex.: leilao" required {...form.register("code")} />
        </Field>
        <Field label="Código no fornecedor (SKU)" htmlFor="p-sku" error={e.sku?.message} hint="Nunca aparece para o lojista.">
          <Input id="p-sku" placeholder="ex.: veicular-leilao-base-3-cf" required {...form.register("sku")} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Categoria" htmlFor="p-cat">
            <Select id="p-cat" {...form.register("category")}>
              {Object.entries(CATEGORIES).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Entrada" htmlFor="p-input">
            <Select id="p-input" {...form.register("input_type")}>
              {INPUTS.map((i) => (
                <option key={i}>{i}</option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Descrição" htmlFor="p-desc" className="sm:col-span-2">
          <Input id="p-desc" placeholder="Frase curta que explica o que a consulta traz" {...form.register("description")} />
        </Field>
        <div className="grid grid-cols-3 gap-3 sm:col-span-2">
          <Field label="Custo (R$)" htmlFor="p-cost" error={e.cost_cents?.message}>
            <Input id="p-cost" inputMode="decimal" placeholder="0,00" {...form.register("cost", { onChange: (ev) => form.setValue("cost", maskMoney(ev.target.value)) })} />
          </Field>
          <Field label="Preço de venda (R$)" htmlFor="p-price" error={e.price_cents?.message}>
            <Input id="p-price" inputMode="decimal" placeholder="0,00" {...form.register("price", { onChange: (ev) => form.setValue("price", maskMoney(ev.target.value)) })} />
          </Field>
          <Field label="Margem" htmlFor="p-margin">
            <Input id="p-margin" disabled value={money(margin)} className={margin < 0 ? "text-red" : ""} />
          </Field>
        </div>
        <Field label="Itens do card (um por linha)" htmlFor="p-high" className="sm:col-span-2">
          <Textarea id="p-high" rows={3} placeholder={"Leilões encontrados\nLote e condição"} {...form.register("highlights_text")} />
        </Field>
        <Field label="Ordem de exibição" htmlFor="p-order">
          <Input id="p-order" inputMode="numeric" placeholder="100" {...form.register("sort_order")} />
        </Field>
        <div className="flex flex-wrap items-end gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" className="size-4 accent-blue" {...form.register("is_active")} /> Ativo
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="size-4 accent-blue" {...form.register("is_featured")} /> Destaque
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="size-4 accent-blue" {...form.register("is_async")} /> Retorno posterior
          </label>
        </div>
        <div className="sm:col-span-2">
          <Button type="submit" loading={form.formState.isSubmitting}>
            {product ? "Salvar alterações" : "Criar produto"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function ProdutosPage() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<Product | null | "new">(null);
  const [filter, setFilter] = useState("");
  const { data, isLoading } = useQuery({ queryKey: ["admin", "products"], queryFn: () => adminApi<Product[]>("/products") });
  const toggle = useMutation({
    mutationFn: (p: Product) => adminApi(`/products/${p.id}`, { method: "PATCH", body: { is_active: !p.is_active } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "products"] }),
    onError: (e) => handleApiError(e),
  });
  const rows = (data ?? []).filter((p) => !filter || `${p.name} ${p.code} ${p.sku}`.toLowerCase().includes(filter.toLowerCase()));
  return (
    <>
      <PageHeader
        title="Produtos de consulta"
        description="Catálogo vendido aos lojistas, com custo, preço e margem."
        action={
          <Button onClick={() => setEditing("new")}>
            <Plus className="size-4" /> Novo produto
          </Button>
        }
      />
      <Card>
        <Input className="mb-4 h-10" placeholder="Filtrar por nome ou código" value={filter} onChange={(e) => setFilter(e.target.value)} />
        {isLoading ? (
          <Spinner />
        ) : (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead className="text-left text-xs text-muted uppercase">
                <tr className="border-b border-line">
                  <th className="px-5 py-2">Produto</th>
                  <th className="px-5 py-2">Categoria</th>
                  <th className="px-5 py-2">Entrada</th>
                  <th className="px-5 py-2 text-right">Custo</th>
                  <th className="px-5 py-2 text-right">Preço</th>
                  <th className="px-5 py-2 text-right">Margem</th>
                  <th className="px-5 py-2">Situação</th>
                  <th className="px-5 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((p) => (
                  <tr key={p.id} className="hover:bg-pale/60">
                    <td className="px-5 py-3">
                      <span className="block font-semibold">
                        {p.name} {p.is_featured && <Badge tone="yellow">Destaque</Badge>}
                      </span>
                      <span className="font-mono text-xs text-muted">
                        {p.code} · {p.sku}
                      </span>
                    </td>
                    <td className="px-5 py-3">{CATEGORIES[p.category] ?? p.category}</td>
                    <td className="px-5 py-3">{p.input_type}</td>
                    <td className="px-5 py-3 text-right">{money(p.cost_cents)}</td>
                    <td className="px-5 py-3 text-right font-semibold">{money(p.price_cents)}</td>
                    <td className={`px-5 py-3 text-right ${p.margin_cents < 0 ? "text-red" : ""}`}>{money(p.margin_cents)}</td>
                    <td className="px-5 py-3">
                      <button onClick={() => toggle.mutate(p)} aria-label={p.is_active ? "Desativar" : "Ativar"}>
                        {p.is_active ? <Badge tone="green">Ativo</Badge> : <Badge>Inativo</Badge>}
                      </button>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(p)} aria-label="Editar">
                        <Pencil className="size-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {editing && <ProductModal product={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </>
  );
}
