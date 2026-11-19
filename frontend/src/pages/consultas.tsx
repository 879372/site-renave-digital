import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, CheckCircle2, Clock, Printer, RefreshCw, Search, ShieldAlert, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Link, useLocation, useParams, useSearch } from "wouter";

import { Badge, Button, Card, Empty, Field, Input, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { api, ApiError, cursorOf, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, labelize, money, plate } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

export type Product = {
  code: string;
  name: string;
  description: string;
  category: string;
  input_type: string;
  price_cents: number;
  is_async: boolean;
  is_featured: boolean;
  highlights: string[];
};

export type Consulta = {
  id: string;
  product: string;
  product_name: string;
  input_type: string;
  input_value: string;
  status: "pending" | "processing" | "success" | "not_found" | "failed";
  status_display: string;
  price_cents: number;
  charged_cents: number;
  message: string;
  user_name: string | null;
  created_at: string;
  completed_at: string | null;
  result?: { familia?: string; encontrado?: boolean; dados?: Record<string, unknown>; consultadoEm?: string } | null;
};

const INPUT_LABEL: Record<string, string> = { PLACA: "Placa", CHASSI: "Chassi", RENAVAM: "RENAVAM", MOTOR: "Motor", CPF: "CPF", CNPJ: "CNPJ" };
const CATEGORY_LABEL: Record<string, string> = {
  completa: "Pacotes completos",
  restricoes: "Restrições e riscos",
  historico: "Histórico",
  preco: "Preço e FIPE",
  cadastro: "Dados cadastrais",
  debitos: "Débitos e documentos",
  empresa: "Empresas",
};

export function StatusBadge({ status, label }: { status: Consulta["status"]; label: string }) {
  const tone = { success: "green", not_found: "blue", failed: "red", processing: "yellow", pending: "yellow" } as const;
  return <Badge tone={tone[status]}>{label}</Badge>;
}

export function useProducts() {
  return useQuery({ queryKey: ["products"], queryFn: () => api<Product[]>("/consultas/products"), staleTime: 5 * 60_000 });
}

function NewConsulta() {
  const initial = new URLSearchParams(useSearch()).get("placa") ?? "";
  const { data: products, isLoading } = useProducts();
  const { can, organization } = useAuth();
  const [sku, setSku] = useState<string>("");
  const [value, setValue] = useState(initial ? plate(initial) : "");
  const [purpose, setPurpose] = useState("compra");
  const [, navigate] = useLocation();
  const qc = useQueryClient();

  useEffect(() => {
    if (products?.length && !sku) setSku(products.find((p) => p.is_featured)?.code ?? products[0].code);
  }, [products, sku]);

  const selected = products?.find((p) => p.code === sku);
  const grouped = useMemo(() => {
    const map = new Map<string, Product[]>();
    products?.forEach((p) => map.set(p.category, [...(map.get(p.category) ?? []), p]));
    return [...map.entries()];
  }, [products]);

  const run = useMutation({
    mutationFn: () => api<Consulta>("/consultas/", { body: { product: sku, value, purpose } }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["wallet", organization?.id] });
      qc.invalidateQueries({ queryKey: ["consultas"] });
      if (c.status === "processing") toast.info("Consulta em processamento. Avisaremos quando ficar pronta.");
      navigate(`/consultas/${c.id}`);
    },
    onError: (e) => {
      qc.invalidateQueries({ queryKey: ["wallet", organization?.id] });
      qc.invalidateQueries({ queryKey: ["consultas"] });
      if (e instanceof ApiError && e.code === "insufficient_balance") {
        toast.error(e.message, { action: { label: "Recarregar", onClick: () => navigate("/carteira") } });
      } else handleApiError(e);
    },
  });

  if (isLoading) return <Spinner />;
  if (!products?.length) return <Empty title="Nenhum produto disponível" icon={<Search />} />;

  const inputType = selected?.input_type ?? "PLACA";
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <div className="space-y-6">
        {grouped.map(([cat, items]) => (
          <section key={cat}>
            <h2 className="mb-3 text-sm font-bold tracking-wide text-muted uppercase">{CATEGORY_LABEL[cat] ?? cat}</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              {items.map((p) => (
                <button
                  key={p.code}
                  type="button"
                  onClick={() => setSku(p.code)}
                  aria-pressed={sku === p.code}
                  className={clsx(
                    "rounded-xl border bg-white p-4 text-left transition",
                    sku === p.code ? "border-blue ring-2 ring-blue/20" : "border-line hover:border-blue/50",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-display text-lg font-semibold">{p.name}</span>
                    <span className="font-semibold whitespace-nowrap text-blue">{money(p.price_cents)}</span>
                  </div>
                  <p className="mt-1 text-sm text-muted">{p.description}</p>
                  {p.highlights.length > 0 && (
                    <ul className="mt-3 space-y-1 text-sm">
                      {p.highlights.map((h) => (
                        <li key={h} className="flex items-center gap-2">
                          <CheckCircle2 className="size-4 text-green" aria-hidden /> {h}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="mt-3 flex gap-2">
                    <Badge>{INPUT_LABEL[p.input_type]}</Badge>
                    {p.is_featured && <Badge tone="yellow">Mais usado</Badge>}
                    {p.is_async && <Badge tone="blue">Retorno posterior</Badge>}
                  </div>
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>

      <form
        className="h-fit rounded-2xl border border-line bg-white p-5 lg:sticky lg:top-24"
        onSubmit={(e) => {
          e.preventDefault();
          run.mutate();
        }}
      >
        <h2 className="text-lg font-bold">{selected?.name}</h2>
        <p className="mb-4 text-sm text-muted">{selected?.description}</p>
        <div className="space-y-4">
          <Field label={INPUT_LABEL[inputType]} htmlFor="value">
            <Input
              id="value"
              value={value}
              onChange={(e) => setValue(inputType === "PLACA" ? plate(e.target.value) : e.target.value.toUpperCase())}
              placeholder={{ PLACA: "ABC1D23", CHASSI: "9BWZZZ377VT004251", RENAVAM: "00000000000", MOTOR: "Número do motor", CPF: "000.000.000-00", CNPJ: "00.000.000/0000-00" }[inputType]}
              className="text-center font-display text-2xl font-bold tracking-widest uppercase"
              autoFocus
              required
            />
          </Field>
          <Field label="Finalidade da consulta" htmlFor="purpose" hint="Exigida pela LGPD e registrada na auditoria.">
            <Select id="purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)}>
              <option value="compra">Avaliação para compra</option>
              <option value="venda">Preparação para venda</option>
              <option value="financiamento">Análise de crédito/financiamento</option>
              <option value="documentacao">Regularização documental</option>
              <option value="outro">Outro</option>
            </Select>
          </Field>
          <div className="flex items-center justify-between rounded-xl bg-pale px-4 py-3">
            <span className="text-sm text-muted">Valor da consulta</span>
            <strong className="font-display text-xl">{money(selected?.price_cents)}</strong>
          </div>
          <Button type="submit" className="w-full" loading={run.isPending} disabled={!can("consultas.run") || !value}>
            <Search className="size-4" /> Consultar
          </Button>
          {!can("consultas.run") && <p className="text-center text-xs text-muted">Seu perfil não permite executar consultas.</p>}
          <p className="text-center text-xs text-muted">Se a fonte não retornar dados, o valor é estornado automaticamente.</p>
        </div>
      </form>
    </div>
  );
}

function History() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const { organization } = useAuth();
  const q = useInfiniteQuery({
    queryKey: ["consultas", organization?.id, search, status],
    queryFn: ({ pageParam }) => api<Page<Consulta>>("/consultas/", { params: { cursor: pageParam, search, status } }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => cursorOf(last.next),
  });
  const rows = q.data?.pages.flatMap((p) => p.results) ?? [];
  return (
    <Card
      title="Histórico"
      action={
        <div className="flex flex-wrap gap-2">
          <Input placeholder="Buscar placa…" value={search} onChange={(e) => setSearch(e.target.value)} className="h-9 w-44" />
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 w-40">
            <option value="">Todos</option>
            <option value="success">Concluídas</option>
            <option value="not_found">Nada consta</option>
            <option value="processing">Processando</option>
            <option value="failed">Falharam</option>
          </Select>
        </div>
      }
    >
      {q.isLoading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <Empty title="Nenhuma consulta ainda" icon={<Search />}>
          Faça a primeira consulta na aba Nova consulta.
        </Empty>
      ) : (
        <>
          <Table head={["Data", "Produto", "Identificador", "Status", "Valor", "Usuário"]}>
            {rows.map((c) => (
              <tr key={c.id} className="hover:bg-pale/60">
                <td className="px-5 py-3 whitespace-nowrap">{dateTime(c.created_at)}</td>
                <td className="px-5 py-3">
                  <Link href={`/consultas/${c.id}`} className="font-semibold text-blue hover:underline">
                    {c.product_name}
                  </Link>
                </td>
                <td className="px-5 py-3 font-mono">{c.input_type === "PLACA" ? plate(c.input_value) : c.input_value}</td>
                <td className="px-5 py-3">
                  <StatusBadge status={c.status} label={c.status_display} />
                </td>
                <td className="px-5 py-3">{money(c.charged_cents)}</td>
                <td className="px-5 py-3 text-muted">{c.user_name ?? "—"}</td>
              </tr>
            ))}
          </Table>
          {q.hasNextPage && (
            <div className="mt-4 text-center">
              <Button variant="secondary" size="sm" onClick={() => q.fetchNextPage()} loading={q.isFetchingNextPage}>
                Carregar mais
              </Button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

export function ConsultasPage() {
  const [tab, setTab] = useState<"nova" | "historico">("nova");
  return (
    <>
      <PageHeader eyebrow="01 / Consultar" title="Consultas veiculares" description="Escolha o produto, informe o identificador e receba o laudo na hora." />
      <div className="mb-6 flex gap-1 rounded-xl bg-white p-1 ring-1 ring-line sm:w-fit" role="tablist">
        {(["nova", "historico"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={clsx("flex-1 rounded-lg px-4 py-2 text-sm font-semibold sm:flex-none", tab === t ? "bg-navy text-white" : "text-muted hover:text-ink")}
          >
            {t === "nova" ? "Nova consulta" : "Histórico"}
          </button>
        ))}
      </div>
      {tab === "nova" ? <NewConsulta /> : <History />}
    </>
  );
}

// --- Laudo -------------------------------------------------------------------------

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <span className="text-muted">—</span>;
  if (typeof value === "boolean") return value ? <Badge tone="red">Sim</Badge> : <Badge tone="green">Não</Badge>;
  return <span className="break-words">{String(value)}</span>;
}

function ResultTree({ data, depth = 0 }: { data: Record<string, unknown>; depth?: number }) {
  const primitives = Object.entries(data).filter(([, v]) => !isPlainObject(v) && !Array.isArray(v));
  const nested = Object.entries(data).filter(([, v]) => isPlainObject(v) || Array.isArray(v));
  return (
    <div className="space-y-5">
      {primitives.length > 0 && (
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {primitives.map(([k, v]) => (
            <div key={k} className="border-b border-line/70 pb-2">
              <dt className="text-xs font-semibold tracking-wide text-muted uppercase">{labelize(k)}</dt>
              <dd className="mt-0.5 font-medium">
                <Value value={v} />
              </dd>
            </div>
          ))}
        </dl>
      )}
      {nested.map(([k, v]) => (
        <section key={k} className={clsx(depth === 0 ? "rounded-xl border border-line p-4" : "pl-3 border-l-2 border-blue/20")}>
          <h3 className="mb-3 font-display text-lg font-semibold">{labelize(k)}</h3>
          {Array.isArray(v) ? (
            v.length === 0 ? (
              <p className="text-sm text-muted">Nada consta.</p>
            ) : (
              <div className="space-y-3">
                {v.map((item, i) =>
                  isPlainObject(item) ? (
                    <div key={i} className="rounded-lg bg-pale/60 p-3">
                      <ResultTree data={item} depth={depth + 1} />
                    </div>
                  ) : (
                    <div key={i}>
                      <Value value={item} />
                    </div>
                  ),
                )}
              </div>
            )
          ) : (
            <ResultTree data={v as Record<string, unknown>} depth={depth + 1} />
          )}
        </section>
      ))}
    </div>
  );
}

export function ConsultaDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { data: c, isLoading } = useQuery({
    queryKey: ["consulta", id],
    queryFn: () => api<Consulta>(`/consultas/${id}`),
    refetchInterval: (q) => (q.state.data && ["processing", "pending"].includes(q.state.data.status) ? 15_000 : false),
  });
  const refresh = useMutation({
    mutationFn: () => api<Consulta>(`/consultas/${id}/refresh`, { method: "POST" }),
    onSuccess: (d) => qc.setQueryData(["consulta", id], d),
    onError: (e) => handleApiError(e),
  });

  if (isLoading || !c) return <Spinner />;
  const Icon = { success: CheckCircle2, not_found: ShieldAlert, failed: XCircle, processing: Clock, pending: Clock }[c.status];

  return (
    <div className="space-y-6">
      <div className="no-print flex items-center justify-between gap-3">
        <Link href="/consultas" className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink">
          <ArrowLeft className="size-4" /> Voltar
        </Link>
        <div className="flex gap-2">
          {["processing", "pending"].includes(c.status) && (
            <Button variant="secondary" size="sm" onClick={() => refresh.mutate()} loading={refresh.isPending}>
              <RefreshCw className="size-4" /> Atualizar
            </Button>
          )}
          {c.status === "success" && (
            <Button variant="secondary" size="sm" onClick={() => window.print()}>
              <Printer className="size-4" /> Imprimir / PDF
            </Button>
          )}
        </div>
      </div>

      <section className="overflow-hidden rounded-2xl bg-navy text-white">
        <div className="flex flex-wrap items-center justify-between gap-6 p-6">
          <div>
            <p className="text-xs font-bold tracking-[0.14em] text-yellow uppercase">Laudo · {c.product_name}</p>
            <p className="mt-2 font-display text-4xl font-bold tracking-wider">{c.input_type === "PLACA" ? plate(c.input_value) : c.input_value}</p>
            <p className="mt-1 text-sm text-[#c7d0ed]">
              {dateTime(c.created_at)} · {c.user_name}
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-xl bg-white/10 px-4 py-3">
            <Icon className="size-8 text-yellow" aria-hidden />
            <div>
              <p className="font-semibold">{c.status_display}</p>
              <p className="text-sm text-[#c7d0ed]">Cobrado: {money(c.charged_cents)}</p>
            </div>
          </div>
        </div>
      </section>

      {c.message && <div className="rounded-xl border border-line bg-white p-4 text-muted">{c.message}</div>}
      {c.result?.dados && Object.keys(c.result.dados).length > 0 && (
        <Card title="Resultado" description={c.result.consultadoEm ? `Dados consultados em ${dateTime(c.result.consultadoEm)}` : undefined}>
          <ResultTree data={c.result.dados} />
        </Card>
      )}
      <p className="text-xs text-muted">
        Informações fornecidas pelas bases consultadas no momento da pesquisa. Uso restrito à finalidade declarada, conforme a LGPD.
      </p>
    </div>
  );
}
