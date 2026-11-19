import clsx from "clsx";
import { ArrowLeft, Compass, Home, RefreshCw, ServerCrash, TriangleAlert, WifiOff } from "lucide-react";
import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { Link } from "wouter";

import { checkServer, useConnectivity } from "@/lib/connectivity";
import { LEGAL } from "@/lib/legal";

import { Logo } from "./AppShell";
import { Button, buttonClass } from "./ui";

const WHATSAPP = `https://wa.me/55${LEGAL.supportWhatsapp.replace(/\D/g, "")}`;

type Props = {
  code?: string;
  icon: ComponentType<{ className?: string }>;
  tone?: "blue" | "yellow" | "red";
  title: string;
  children: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  /** Dentro do layout do app (com menu): sem logo e sem ocupar a tela toda. */
  embedded?: boolean;
};

const TONES = {
  blue: "bg-blue-50 text-blue",
  yellow: "bg-yellow-50 text-[#8a6500]",
  red: "bg-red-50 text-red",
};

export function StatusScreen({ code, icon: Icon, tone = "blue", title, children, actions, footer, embedded }: Props) {
  const body = (
    <div className="mx-auto flex w-full max-w-lg flex-col items-center text-center">
      <div className="relative mb-6">
        {code && (
          <p aria-hidden className="font-display text-[112px] leading-none font-extrabold tracking-tighter text-navy/[0.07] select-none sm:text-[150px]">
            {code}
          </p>
        )}
        <div className={clsx("grid size-16 place-items-center rounded-2xl shadow-sm ring-4 ring-white", TONES[tone], code && "absolute inset-0 m-auto")}>
          <Icon className="size-8" />
        </div>
      </div>
      {code && <p className="mb-2 text-xs font-bold tracking-[0.18em] text-blue uppercase">Erro {code}</p>}
      <h1 id="status-title" className="text-3xl font-bold sm:text-4xl">{title}</h1>
      <div className="mt-3 max-w-md text-muted">{children}</div>
      {actions && <div className="mt-8 flex w-full flex-col-reverse justify-center gap-3 sm:w-auto sm:flex-row">{actions}</div>}
      {footer && <div className="mt-8 text-sm text-muted">{footer}</div>}
    </div>
  );

  if (embedded) return <div className="py-12 sm:py-20">{body}</div>;

  return (
    <div className="flex min-h-dvh flex-col bg-pale">
      <header className="px-4 py-5 sm:px-8">
        <a href="/" aria-label="RENAVE DIGITAL início" className="inline-block">
          <Logo />
        </a>
      </header>
      <main className="flex flex-1 items-center px-4 pb-16">{body}</main>
    </div>
  );
}

function Support() {
  return (
    <>
      Precisa de ajuda?{" "}
      <a href={WHATSAPP} target="_blank" rel="noopener" className="font-semibold text-blue hover:underline">
        Fale com o suporte pelo WhatsApp
      </a>
    </>
  );
}

export function NotFoundPage({ embedded, homeLabel = "Ir para o início" }: { embedded?: boolean; homeLabel?: string }) {
  const canGoBack = typeof window !== "undefined" && window.history.length > 1;
  return (
    <StatusScreen
      code="404"
      icon={Compass}
      title="Página não encontrada"
      embedded={embedded}
      actions={
        <>
          {canGoBack && (
            <Button variant="secondary" onClick={() => window.history.back()}>
              <ArrowLeft className="size-4" /> Voltar
            </Button>
          )}
          <Link href="/" className={buttonClass("primary")}>
            <Home className="size-4" /> {homeLabel}
          </Link>
        </>
      }
      footer={<Support />}
    >
      O endereço pode ter sido digitado errado ou a página mudou de lugar. Confira o link ou volte para o início.
    </StatusScreen>
  );
}

/** Mostrada por cima do app enquanto não houver internet ou a API estiver fora; o app continua montado por baixo. */
export function ConnectionOverlay() {
  const { online, serverDown } = useConnectivity();
  const [retrying, setRetrying] = useState(false);
  const show = !online || serverDown;

  useEffect(() => {
    if (!show) return;
    const previous = document.title;
    document.title = online ? "Servidor indisponível | RENAVE DIGITAL" : "Sem internet | RENAVE DIGITAL";
    return () => {
      document.title = previous;
    };
  }, [show, online]);

  if (!show) return null;

  const retry = async () => {
    setRetrying(true);
    try {
      await checkServer();
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] overflow-y-auto" role="alertdialog" aria-modal="true" aria-labelledby="status-title">
      {online ? (
        <StatusScreen
          icon={ServerCrash}
          tone="red"
          title="Servidor indisponível"
          actions={
            <Button onClick={retry} loading={retrying}>
              <RefreshCw className="size-4" /> Tentar agora
            </Button>
          }
          footer={<Support />}
        >
          Nossos servidores não estão respondendo agora, provavelmente por uma manutenção rápida. Seus dados estão seguros e nada do que você estava
          fazendo foi perdido. <strong className="text-ink">Vamos reconectar sozinhos</strong> assim que o serviço voltar.
          <PollingHint />
        </StatusScreen>
      ) : (
        <StatusScreen
          icon={WifiOff}
          tone="yellow"
          title="Você está sem internet"
          actions={
            <Button onClick={retry} loading={retrying}>
              <RefreshCw className="size-4" /> Tentar novamente
            </Button>
          }
        >
          Verifique o Wi-Fi, o cabo ou os dados móveis. Assim que a conexão voltar, você continua de onde parou, sem perder o que estava preenchendo.
        </StatusScreen>
      )}
    </div>
  );
}

function PollingHint() {
  return (
    <span className="mt-5 flex items-center justify-center gap-2 text-sm">
      <span className="relative flex size-2.5">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-blue opacity-60" />
        <span className="relative inline-flex size-2.5 rounded-full bg-blue" />
      </span>
      Verificando a conexão a cada poucos segundos…
    </span>
  );
}

export function CrashScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <StatusScreen
      code="500"
      icon={TriangleAlert}
      tone="red"
      title="Algo deu errado"
      actions={
        <>
          <a href="/" className={buttonClass("secondary")}>
            <Home className="size-4" /> Ir para o início
          </a>
          <Button onClick={onRetry}>
            <RefreshCw className="size-4" /> Recarregar a página
          </Button>
        </>
      }
      footer={<Support />}
    >
      Encontramos um erro inesperado ao mostrar esta tela. Recarregue a página para continuar.
    </StatusScreen>
  );
}
