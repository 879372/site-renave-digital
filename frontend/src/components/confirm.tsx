/**
 * Modais de confirmação no lugar de window.confirm/prompt.
 *
 *   if (await ask("Apagar esta foto?")) remove()
 *   const motivo = await askText({ title: "Motivo da perda" })
 *
 * <ConfirmHost /> fica montado uma vez na raiz do app e do painel admin.
 */
import { useEffect, useState } from "react";

import { Button, Field, Input, Modal } from "./ui";

type Request =
  | { kind: "confirm"; message: string; danger: boolean; confirmLabel: string; resolve: (v: boolean) => void }
  | { kind: "text"; title: string; label: string; placeholder: string; confirmLabel: string; resolve: (v: string | null) => void };

let push: ((r: Request) => void) | null = null;
const queue: Request[] = [];

function enqueue(r: Request) {
  if (push) push(r);
  else queue.push(r);
}

const DANGER = /\b(apagar|remover|excluir|cancelar|desativar|bloquear|estornar|devolver)\b/i;

/** Pergunta sim/não. A primeira frase vira o título; o resto, a explicação. */
export function ask(message: string, opts: { danger?: boolean; confirmLabel?: string } = {}): Promise<boolean> {
  return new Promise((resolve) =>
    enqueue({ kind: "confirm", message, danger: opts.danger ?? DANGER.test(message), confirmLabel: opts.confirmLabel ?? "Confirmar", resolve }),
  );
}

/** Pede um texto obrigatório. Devolve null se a pessoa desistir. */
export function askText(opts: { title: string; label?: string; placeholder?: string; confirmLabel?: string }): Promise<string | null> {
  return new Promise((resolve) =>
    enqueue({ kind: "text", title: opts.title, label: opts.label ?? opts.title, placeholder: opts.placeholder ?? "", confirmLabel: opts.confirmLabel ?? "Confirmar", resolve }),
  );
}

function split(message: string) {
  const i = message.indexOf("?");
  if (i === -1 || i === message.length - 1) return { title: message, description: undefined };
  return { title: message.slice(0, i + 1), description: message.slice(i + 1).trim() };
}

export function ConfirmHost() {
  const [current, setCurrent] = useState<Request | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const pending: Request[] = [];
    push = (r) => {
      pending.push(r);
      setCurrent((c) => c ?? pending.shift() ?? null);
    };
    while (queue.length) push(queue.shift()!);
    return () => {
      push = null;
    };
  }, []);

  const close = (value: boolean | string | null) => {
    if (!current) return;
    if (current.kind === "confirm") current.resolve(value === true);
    else current.resolve(typeof value === "string" ? value : null);
    setText("");
    setError("");
    setCurrent(null);
  };

  if (!current) return null;
  if (current.kind === "confirm") {
    const { title, description } = split(current.message);
    return (
      <Modal open onOpenChange={(v) => !v && close(false)} title={title} description={description}>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => close(false)}>
            Voltar
          </Button>
          <Button variant={current.danger ? "danger" : "primary"} onClick={() => close(true)} autoFocus>
            {current.confirmLabel}
          </Button>
        </div>
      </Modal>
    );
  }
  return (
    <Modal open onOpenChange={(v) => !v && close(null)} title={current.title}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim()) {
            setError("Preencha para continuar.");
            return;
          }
          close(text.trim());
        }}
      >
        <Field label={current.label} htmlFor="ask-text" error={error}>
          <Input id="ask-text" autoFocus value={text} placeholder={current.placeholder} onChange={(e) => { setText(e.target.value); setError(""); }} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => close(null)}>
            Voltar
          </Button>
          <Button type="submit">{current.confirmLabel}</Button>
        </div>
      </form>
    </Modal>
  );
}
