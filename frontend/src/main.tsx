import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Toaster } from "sonner";

import { App } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ConnectionOverlay } from "./components/StatusScreen";
import { ApiError } from "./lib/api";
import { AuthProvider } from "./lib/auth";
import { connectivity } from "./lib/connectivity";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // Erro de regra (4xx) não adianta repetir; erro de conexão é tratado pela tela de conexão.
      retry: (count, error) => !(error instanceof ApiError && error.status < 500 && error.status !== 0) && count < 2,
    },
  },
});

// Quando a internet ou o servidor voltam, atualiza o que estava na tela.
connectivity.onRecover(() => {
  void queryClient.invalidateQueries();
});

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  // Só serve a página "sem internet" quando a navegação falha; não guarda o app em cache.
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <AuthProvider>
          <App />
          <Toaster richColors position="top-right" closeButton />
        </AuthProvider>
      </ErrorBoundary>
      <ConnectionOverlay />
    </QueryClientProvider>
  </StrictMode>,
);
