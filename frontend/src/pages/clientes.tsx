import { useQuery } from "@tanstack/react-query";
import { Plus, Users } from "lucide-react";
import { useState } from "react";

import { Pager, PessoaModal, SearchInput, useDebounced, type Paged, type Pessoa } from "@/components/kit";
import { Badge, Button, Card, Empty, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { document, maskPhone } from "@/lib/format";

export function ClientesPage() {
  const { organization, can } = useAuth();
  const [term, setTerm] = useState("");
  const [tipo, setTipo] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Pessoa | null | undefined>(undefined);
  const search = useDebounced(term);
  const q = useQuery({ queryKey: ["pessoas", organization?.id, search, tipo, page], queryFn: () => api<Paged<Pessoa>>("/pessoas/", { params: { search, tipo, page } }) });
  return (
    <>
      <PageHeader title="Clientes e fornecedores" description="Cadastro único: quem compra, quem vende para a loja e donos de consignados." action={can("vendas.operate") && <Button onClick={() => setEditing(null)}><Plus className="size-4" /> Novo cadastro</Button>} />
      <Card title="Cadastros" action={
        <div className="flex flex-wrap gap-2">
          <SearchInput value={term} onChange={(v) => { setTerm(v); setPage(1); }} placeholder="Nome, CPF/CNPJ ou telefone" />
          <Select value={tipo} onChange={(e) => { setTipo(e.target.value); setPage(1); }} className="h-9 w-36"><option value="">Todos</option><option value="cliente">Clientes</option><option value="fornecedor">Fornecedores</option></Select>
        </div>
      }>
        {q.isLoading ? <Spinner /> : !q.data?.results.length ? <Empty title="Nenhum cadastro" icon={<Users />} /> : (
          <>
            <Table head={["Nome", "CPF/CNPJ", "Telefone", "Cidade", ""]}>
              {q.data.results.map((p) => (
                <tr key={p.id} className="cursor-pointer hover:bg-pale/60" onClick={() => can("vendas.operate") && setEditing(p)}>
                  <td className="px-5 py-3 font-medium">{p.nome}</td>
                  <td className="px-5 py-3 text-muted">{document(p.documento) || "—"}</td>
                  <td className="px-5 py-3">{p.telefone ? maskPhone(p.telefone) : "—"}</td>
                  <td className="px-5 py-3 text-muted">{p.cidade ? `${p.cidade}/${p.uf}` : "—"}</td>
                  <td className="px-5 py-3 text-right">{p.is_cliente && <Badge>cliente</Badge>} {p.is_fornecedor && <Badge tone="blue">fornecedor</Badge>}</td>
                </tr>
              ))}
            </Table>
            <Pager page={page} data={q.data} onPage={setPage} />
          </>
        )}
      </Card>
      <PessoaModal open={editing !== undefined} onOpenChange={(v) => !v && setEditing(undefined)} pessoa={editing ?? null} />
    </>
  );
}
