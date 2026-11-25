import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({ api: vi.fn(), auth: {} as any }));
vi.mock("@/lib/api", () => ({ api: mock.api }));
vi.mock("@/lib/auth", () => ({ useAuth: () => mock.auth }));
import { PaymentReturnPage } from "@/pages/pagamento-retorno";

function mount() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><PaymentReturnPage /></QueryClientProvider>);
}

afterEach(cleanup);
beforeEach(() => {
  mock.api.mockReset();
  sessionStorage.clear();
  window.history.replaceState({}, "", "/pagamento/retorno?order_nsu=revenda-123&transaction_nsu=tx&slug=slug&paid=true");
  mock.auth = { user: { id: "u" }, status: "authenticated", organization: { id: "o" }, organizations: [{ id: "o", name: "Loja" }], setOrganization: vi.fn() };
});

describe("retorno do checkout", () => {
  it("não confia no status da URL e aguarda a confirmação do servidor", async () => {
    mock.api.mockResolvedValue({ paid: false, kind: "invoice" });
    mount();
    await waitFor(() => expect(mock.api).toHaveBeenCalledWith("/billing/checkout/confirm", { body: { order_nsu: "revenda-123", transaction_nsu: "tx", slug: "slug" } }));
    expect(await screen.findByText(/ainda não foi confirmado/)).toBeTruthy();
    expect(screen.queryByText(/Pagamento confirmado\./)).toBeNull();
  });
  it("mostra confirmação somente após a resposta validada e limpa o retorno pendente", async () => {
    sessionStorage.setItem("rd.checkout-return", "/pagamento/retorno?order_nsu=revenda-123");
    mock.api.mockResolvedValue({ paid: true, kind: "invoice" });
    mount();
    expect(await screen.findByText(/Pagamento confirmado\./)).toBeTruthy();
    expect(sessionStorage.getItem("rd.checkout-return")).toBeNull();
  });
  it("preserva o retorno enquanto o cliente precisa entrar novamente", () => {
    mock.auth = { ...mock.auth, user: null, status: "anonymous" };
    mount();
    expect(screen.getByText(/Entre na sua conta/)).toBeTruthy();
    expect(sessionStorage.getItem("rd.checkout-return")).toContain("order_nsu=revenda-123");
    expect(mock.api).not.toHaveBeenCalled();
  });
});
