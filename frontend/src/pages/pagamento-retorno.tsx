import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { Button, Card, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function PaymentReturnPage() {
  const { user, status, organization, organizations, setOrganization } = useAuth();
  const qc = useQueryClient();
  const query = new URLSearchParams(window.location.search);
  const order_nsu = query.get("order_nsu") ?? "";
  const transaction_nsu = query.get("transaction_nsu") ?? "";
  const slug = query.get("slug") ?? "";
  const valid = !!order_nsu && !!transaction_nsu && !!slug;
  const attempted = useRef("");
  const confirm = useMutation({
    mutationFn: () => api<{ paid: boolean; kind: string; requires_review?: boolean }>("/billing/checkout/confirm", { body: { order_nsu, transaction_nsu, slug } }),
    onSuccess: (result) => {
      if (result.paid) {
        sessionStorage.removeItem("rd.checkout-return");
        for (const key of ["billing", "invoices", "wallet", "topups", "ledger"]) void qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
  const { mutate } = confirm;
  useEffect(() => {
    if (valid && !user) sessionStorage.setItem("rd.checkout-return", window.location.pathname + window.location.search);
    const key = `${organization?.id}:${order_nsu}:${transaction_nsu}:${slug}`;
    if (valid && user && organization && attempted.current !== key) {
      attempted.current = key;
      mutate();
    }
  }, [valid, user, organization?.id, order_nsu, transaction_nsu, slug, mutate]);
  if (status === "loading") return <Spinner />;
  return <main className="mx-auto max-w-xl p-6"><Card title="Confirmação do pagamento">
    {!valid ? <p>O retorno está incompleto. Consulte sua fatura na plataforma; a confirmação também chega automaticamente.</p>
      : !user ? <><p>Entre na sua conta para acompanhar o pagamento.</p><a href="/entrar">Entrar na plataforma</a></>
      : <div className="space-y-4">
        <p>{confirm.isPending ? "Conferindo o pagamento na InfinitePay…" : confirm.data?.requires_review ? "Pagamento identificado após o cancelamento. A equipe precisa revisar o crédito ou estorno; o plano não foi reativado por esta cobrança." : confirm.data?.paid ? "Pagamento confirmado. Seu plano ou crédito já foi atualizado." : confirm.error ? confirm.error.message : "O pagamento ainda não foi confirmado. Você pode conferir novamente em instantes."}</p>
        {organizations.length > 1 && <label className="block">Loja <select value={organization?.id ?? ""} onChange={(e) => setOrganization(e.target.value)}>{organizations.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>}
        {!confirm.data?.paid && <Button onClick={() => confirm.mutate()} loading={confirm.isPending} disabled={!organization}>Conferir pagamento</Button>}
        <a className="block font-semibold text-brand" href={confirm.data?.kind === "topup" ? "/carteira" : "/planos"}>Voltar para a plataforma</a>
      </div>}
  </Card></main>;
}
