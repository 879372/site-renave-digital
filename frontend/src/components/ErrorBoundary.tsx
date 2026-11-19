import { Component, type ErrorInfo, type ReactNode } from "react";

import { CrashScreen } from "./StatusScreen";

const RELOAD_KEY = "rd.chunk-reload";

/** Arquivo do app que sumiu depois de um deploy novo (a aba ainda tinha a versão antiga). */
function isChunkError(error: Error) {
  return /dynamically imported module|Importing a module script failed|ChunkLoadError|Loading chunk/i.test(`${error.name} ${error.message}`);
}

type State = { error: Error | null };

/** Captura erros de renderização e mostra uma tela amigável em vez de uma página em branco. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (isChunkError(error)) {
      // Sem internet: a tela de conexão já aparece; tentamos de novo quando a rede voltar.
      if (!navigator.onLine) {
        window.addEventListener("online", () => this.setState({ error: null }), { once: true });
        return;
      }
      // Deploy novo: recarrega uma única vez para buscar a versão atual.
      let reloaded = false;
      try {
        reloaded = sessionStorage.getItem(RELOAD_KEY) === "1";
        sessionStorage.setItem(RELOAD_KEY, "1");
      } catch {
        /* sem storage */
      }
      if (!reloaded) {
        window.location.reload();
        return;
      }
    }
    console.error("Erro na interface", error, info.componentStack);
  }

  componentDidMount() {
    try {
      sessionStorage.removeItem(RELOAD_KEY);
    } catch {
      /* sem storage */
    }
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (isChunkError(error) && !navigator.onLine) return null;
    return <CrashScreen onRetry={() => window.location.reload()} />;
  }
}
