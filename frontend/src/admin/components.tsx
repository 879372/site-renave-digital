import { keepPreviousData, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "wouter";

import { Button, Card, Empty, Input, Select, Spinner } from "@/components/ui";
import { document } from "@/lib/format";

import { adminApi, type Paged } from "./api";

export type OrgRef = { id: string; name: string; cnpj: string } | null;

export function OrgCell({ org }: { org: OrgRef }) {
  if (!org) return <span className="text-muted">—</span>;
  return (
    <Link href={`/empresas/${org.id}`} className="group block min-w-0">
      <span className="block truncate font-semibold text-brand group-hover:underline">{org.name}</span>
      <span className="block font-mono text-xs text-muted">{document(org.cnpj)}</span>
    </Link>
  );
}

export type Column<T> = { header: string; cell: (row: T) => ReactNode; className?: string };
export type Filter = { name: string; label: string; options: [string, string][] } | { name: string; label: string; type: "date" };

function useDebounced<T>(value: T, ms = 350) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Tabela paginada genérica para os recursos do admin, com busca e filtros na mesma linha. */
export function ResourceTable<T extends { id: string | number }>({
  endpoint,
  columns,
  filters = [],
  searchPlaceholder = "Buscar…",
  fixedParams = {},
  title,
  action,
  empty = "Nada encontrado.",
  queryKey,
}: {
  endpoint: string;
  columns: Column<T>[];
  filters?: Filter[];
  searchPlaceholder?: string;
  fixedParams?: Record<string, string>;
  title?: ReactNode;
  action?: ReactNode;
  empty?: string;
  queryKey?: string;
}) {
  const [search, setSearch] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const debounced = useDebounced(search);
  const params = { search: debounced, page, ...values, ...fixedParams };
  const q = useQuery({
    queryKey: ["admin", queryKey ?? endpoint, params],
    queryFn: () => adminApi<Paged<T>>(endpoint, { params }),
    placeholderData: keepPreviousData,
  });
  const pageSize = 25;
  const total = q.data?.count ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <Card title={title} action={action}>
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="relative min-w-56 flex-1">
          <span className="sr-only">Buscar</span>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input
            className="h-10 pl-9"
            placeholder={searchPlaceholder}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </label>
        {filters.map((f) => (
          <label key={f.name} className="flex flex-col gap-1 text-xs font-semibold text-muted">
            {f.label}
            {"options" in f ? (
              <Select
                className="h-10 w-44"
                value={values[f.name] ?? ""}
                onChange={(e) => {
                  setValues((v) => ({ ...v, [f.name]: e.target.value }));
                  setPage(1);
                }}
              >
                {f.options.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                type="date"
                className="h-10 w-40"
                value={values[f.name] ?? ""}
                onChange={(e) => {
                  setValues((v) => ({ ...v, [f.name]: e.target.value }));
                  setPage(1);
                }}
              />
            )}
          </label>
        ))}
      </div>
      {q.isLoading ? (
        <Spinner />
      ) : !q.data?.results.length ? (
        <Empty title={empty} />
      ) : (
        <div className={clsx("-mx-5 overflow-x-auto transition-opacity", q.isFetching && "opacity-60")}>
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs tracking-wide text-muted uppercase">
                {columns.map((c) => (
                  <th key={c.header} className={clsx("px-5 py-2.5 font-semibold", c.className)}>
                    {c.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {q.data.results.map((row) => (
                <tr key={row.id} className="align-top hover:bg-pale/60">
                  {columns.map((c) => (
                    <td key={c.header} className={clsx("px-5 py-3", c.className)}>
                      {c.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {total > 0 && (
        <div className="mt-4 flex items-center justify-between text-sm text-muted">
          <span>
            {total.toLocaleString("pt-BR")} registro(s) · página {page} de {pages}
          </span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Página anterior">
              <ChevronLeft className="size-4" />
            </Button>
            <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => setPage((p) => p + 1)} aria-label="Próxima página">
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

export const STATUS_OPTIONS = {
  active: [
    ["", "Todos"],
    ["true", "Ativos"],
    ["false", "Inativos"],
  ] as [string, string][],
};

export const DATE_FILTERS: Filter[] = [
  { name: "date_from", label: "De", type: "date" },
  { name: "date_to", label: "Até", type: "date" },
];
