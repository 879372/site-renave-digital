import * as Dialog from "@radix-ui/react-dialog";
import clsx from "clsx";
import { Loader2, X } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "yellow";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-blue text-white hover:bg-navy shadow-sm",
  secondary: "bg-white text-ink border border-line hover:border-blue hover:text-blue",
  ghost: "text-muted hover:text-ink hover:bg-pale",
  danger: "bg-white text-red border border-red/30 hover:bg-red-50",
  yellow: "bg-yellow text-navy hover:brightness-95 shadow-sm",
};

/** Classes do botão, para links com aparência de botão (evita <a><button>). */
export function buttonClass(variant: Variant = "primary", size: "sm" | "md" = "md", className?: string) {
  return clsx(
    "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition disabled:cursor-not-allowed disabled:opacity-60",
    size === "sm" ? "h-9 px-3 text-sm" : "h-11 px-5 text-[15px]",
    VARIANTS[variant],
    className,
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean; size?: "sm" | "md" }>(
  ({ variant = "primary", loading, size = "md", className, children, disabled, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={buttonClass(variant, size, className)}
      {...props}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  ),
);
Button.displayName = "Button";

export function Field({ label, error, hint, children, className, htmlFor }: { label: string; error?: string; hint?: string; children: ReactNode; className?: string; htmlFor?: string }) {
  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-sm font-semibold text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-sm text-red">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-muted">{hint}</p>
      ) : null}
    </div>
  );
}

const inputBase = "w-full rounded-lg border bg-white px-3 text-[15px] text-ink placeholder:text-muted/60 transition disabled:bg-pale aria-[invalid=true]:border-red";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} className={clsx(inputBase, "h-11 border-line", className)} {...props} />
));
Input.displayName = "Input";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(({ className, children, ...props }, ref) => (
  <select ref={ref} className={clsx(inputBase, "h-11 border-line", className)} {...props}>
    {children}
  </select>
));
Select.displayName = "Select";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={clsx(inputBase, "border-line py-2.5", className)} {...props} />
));
Textarea.displayName = "Textarea";

export function Card({ children, className, title, action, description }: { children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode; description?: ReactNode }) {
  return (
    <section className={clsx("rounded-2xl border border-line bg-white", className)}>
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            {title && <h2 className="text-lg font-bold">{title}</h2>}
            {description && <p className="text-sm text-muted">{description}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

const TONES = {
  green: "bg-green-50 text-green",
  red: "bg-red-50 text-red",
  yellow: "bg-yellow-50 text-[#8a6500]",
  blue: "bg-blue-50 text-blue",
  gray: "bg-pale text-muted",
};

export function Badge({ tone = "gray", children }: { tone?: keyof typeof TONES; children: ReactNode }) {
  return <span className={clsx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap", TONES[tone])}>{children}</span>;
}

export function PageHeader({ title, description, action, eyebrow }: { title: string; description?: string; action?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <p className="mb-1 text-xs font-bold tracking-[0.14em] text-blue uppercase">{eyebrow}</p>}
        <h1 className="text-3xl font-bold">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-12 text-center">
      {icon && <div className="mb-1 grid size-12 place-items-center rounded-full bg-pale text-blue">{icon}</div>}
      <p className="font-display text-lg font-semibold">{title}</p>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Spinner({ label = "Carregando…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-muted" role="status">
      <Loader2 className="size-5 animate-spin" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="-mx-5 overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs tracking-wide text-muted uppercase">
            {head.map((h, i) => (
              <th key={i} className="px-5 py-2.5 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}

export function Modal({ open, onOpenChange, title, description, children, wide }: { open: boolean; onOpenChange: (v: boolean) => void; title: string; description?: string; children: ReactNode; wide?: boolean }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-navy/40 backdrop-blur-[2px]" />
        <Dialog.Content
          className={clsx(
            "fixed top-1/2 left-1/2 z-50 max-h-[90vh] w-[calc(100%-32px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl",
            wide ? "max-w-3xl" : "max-w-lg",
          )}
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="font-display text-xl font-bold">{title}</Dialog.Title>
              {description ? <Dialog.Description className="mt-1 text-sm text-muted">{description}</Dialog.Description> : <Dialog.Description className="sr-only">{title}</Dialog.Description>}
            </div>
            <Dialog.Close className="rounded-lg p-1 text-muted hover:bg-pale" aria-label="Fechar">
              <X className="size-5" />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function Stat({ label, value, hint, icon }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-5">
      <div className="flex items-center justify-between text-sm font-semibold text-muted">
        {label}
        {icon && <span className="text-blue">{icon}</span>}
      </div>
      <div className="mt-2 font-display text-3xl font-bold text-ink">{value}</div>
      {hint && <div className="mt-1 text-sm text-muted">{hint}</div>}
    </div>
  );
}
