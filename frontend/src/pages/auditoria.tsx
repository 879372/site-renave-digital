import { useInfiniteQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";

import { Button, Card, Empty, PageHeader, Spinner, Table } from "@/components/ui";
import { api, cursorOf, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime } from "@/lib/format";

type Event = { id: number; created_at: string; actor: string | null; action: string; target_type: string; target_id: string; ip: string | null };

const LABEL: Record<string, string> = {
  "account.registered": "Conta criada",
  "auth.login": "Login",
  "auth.login_failed": "Login recusado",
  "auth.mfa_enabled": "2FA ativado",
  "auth.mfa_disabled": "2FA desativado",
  "auth.password_changed": "Senha alterada",
  "consulta.created": "Consulta realizada",
  "consulta.failed": "Consulta não concluída",
  "certificate.uploaded": "Certificado enviado",
  "certificate.deactivated": "Certificado desativado",
  "renave.entrada": "Entrada RENAVE",
  "renave.saida": "Saída RENAVE",
  "renave.cancelar_entrada": "Cancelamento de entrada",
  "renave.cancelar_saida": "Cancelamento de saída",
  "comunicacao.criada": "Comunicação cadastrada",
  "comunicacao.transmitida": "Comunicação transmitida",
  "fiscal.nfe_criada": "NF-e emitida",
  "fiscal.nfe_cancelada": "NF-e cancelada",
  "member.invited": "Membro convidado",
  "member.updated": "Membro alterado",
  "member.removed": "Membro removido",
  "wallet.topup_requested": "Recarga solicitada",
  "wallet.topup_confirmed": "Recarga confirmada",
  "organization.updated": "Dados da empresa alterados",
};

export function AuditoriaPage() {
  const { organization } = useAuth();
  const q = useInfiniteQuery({
    queryKey: ["audit", organization?.id],
    queryFn: ({ pageParam }) => api<Page<Event>>("/audit/events", { params: { cursor: pageParam } }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (l) => cursorOf(l.next),
  });
  const rows = q.data?.pages.flatMap((p) => p.results) ?? [];
  return (
    <>
      <PageHeader title="Auditoria" description="Registro imutável de todas as ações sensíveis realizadas na empresa." />
      <Card>
        {q.isLoading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <Empty title="Nenhum evento" icon={<ScrollText />} />
        ) : (
          <>
            <Table head={["Data", "Ação", "Usuário", "Referência", "IP"]}>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className="px-5 py-3 whitespace-nowrap">{dateTime(e.created_at)}</td>
                  <td className="px-5 py-3 font-semibold">{LABEL[e.action] ?? e.action}</td>
                  <td className="px-5 py-3">{e.actor ?? "—"}</td>
                  <td className="px-5 py-3 font-mono text-xs text-muted">{e.target_type ? `${e.target_type} ${e.target_id.slice(0, 8)}` : "—"}</td>
                  <td className="px-5 py-3 font-mono text-xs text-muted">{e.ip ?? "—"}</td>
                </tr>
              ))}
            </Table>
            {q.hasNextPage && (
              <div className="mt-4 text-center">
                <Button variant="secondary" size="sm" onClick={() => q.fetchNextPage()}>
                  Carregar mais
                </Button>
              </div>
            )}
          </>
        )}
      </Card>
    </>
  );
}
