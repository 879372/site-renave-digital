import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  BarChart3,
  Building2,
  Car,
  ChevronDown,
  ClipboardCheck,
  CreditCard,
  FileSignature,
  FileText,
  Globe,
  Handshake,
  Landmark,
  LayoutDashboard,
  Lock,
  LogOut,
  Menu,
  ScrollText,
  Search,
  Send,
  ShieldCheck,
  Store,
  Trophy,
  User as UserIcon,
  UserRound,
  Users,
  Wallet,
  Warehouse,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useLocation } from "wouter";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { daysUntil, useBilling } from "@/lib/billing";
import { document, money, ROLE_LABEL } from "@/lib/format";

import { AddCompanyModal } from "./AddCompanyModal";
import { LegalFooter } from "./LegalFooter";

type NavItem = { href: string; label: string; icon: typeof Car; perm?: string; feature?: string };

const NAV: { group: string; items: NavItem[] }[] = [
  { group: "", items: [{ href: "/", label: "Painel", icon: LayoutDashboard }] },
  {
    group: "Loja",
    items: [
      { href: "/veiculos", label: "Veículos", icon: Car, feature: "estoque" },
      { href: "/avaliacoes", label: "Avaliações", icon: ClipboardCheck, feature: "avaliacao" },
      { href: "/vendas", label: "Vendas", icon: Handshake, feature: "estoque" },
      { href: "/leads", label: "Leads", icon: Users, feature: "crm" },
      { href: "/clientes", label: "Clientes", icon: UserRound },
      { href: "/financiamento", label: "Financiamento", icon: Landmark, feature: "financiamento" },
      { href: "/pos-venda", label: "Pós-venda", icon: ShieldCheck, feature: "posvenda" },
    ],
  },
  {
    group: "Gestão",
    items: [
      { href: "/financeiro", label: "Financeiro", icon: Wallet, feature: "financeiro" },
      { href: "/comissoes", label: "Comissões", icon: Trophy, feature: "comissoes" },
      { href: "/contratos", label: "Contratos", icon: FileSignature, feature: "contratos" },
      { href: "/relatorios", label: "Relatórios", icon: BarChart3, feature: "relatorios" },
    ],
  },
  {
    group: "RENAVE e fiscal",
    items: [
      { href: "/estoque", label: "Estoque RENAVE", icon: Warehouse },
      { href: "/comunicacao-venda", label: "Comunicação de venda", icon: Send },
      { href: "/notas", label: "Notas fiscais", icon: FileText, feature: "fiscal" },
      { href: "/consultas", label: "Consultas", icon: Search },
    ],
  },
  {
    group: "Configurações",
    items: [
      { href: "/site", label: "Site da loja", icon: Globe, feature: "vitrine" },
      { href: "/lojas", label: "Lojas", icon: Store, feature: "multiloja" },
      { href: "/planos", label: "Plano e faturas", icon: CreditCard },
      { href: "/carteira", label: "Carteira", icon: Wallet },
      { href: "/empresa", label: "Empresa", icon: Building2 },
      { href: "/auditoria", label: "Auditoria", icon: ScrollText, perm: "audit.view" },
    ],
  },
];

export function Logo({ light }: { light?: boolean }) {
  return (
    <span className="flex items-center gap-2.5 leading-none">
      <img src="/simbolo.svg" alt="" width={30} height={30} />
      <span className={clsx("text-[15px] font-semibold tracking-tight", light ? "text-white" : "text-graphite")}>
        REVENDA <span className={light ? "text-mint" : "text-brand"}>DIGITAL</span>
      </span>
    </span>
  );
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  const [location] = useLocation();
  const { can } = useAuth();
  const { has } = useBilling();
  return (
    <nav className="flex flex-col gap-4" aria-label="Principal">
      {NAV.map(({ group, items }) => (
        <div key={group || "top"} className="flex flex-col gap-0.5">
          {group && <p className="mb-1 px-3 text-[11px] font-medium tracking-wide text-[#71717a] uppercase">{group}</p>}
          {items
            .filter((n) => !n.perm || can(n.perm))
            .map(({ href, label, icon: Icon, feature }) => {
              const active = href === "/" ? location === "/" : location === href || location.startsWith(`${href}/`);
              const locked = !!feature && !has(feature);
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={onNavigate}
                  className={clsx(
                    "flex items-center gap-3 rounded-lg px-3 py-1.5 text-sm font-medium transition",
                    active ? "bg-white/10 text-white" : "text-[#a1a1aa] hover:bg-white/5 hover:text-white",
                  )}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon className={clsx("size-[17px]", active && "text-mint")} aria-hidden />
                  <span className="flex-1">{label}</span>
                  {locked && <Lock className="size-3.5 text-[#71717a]" aria-label="Fora do plano" />}
                </Link>
              );
            })}
        </div>
      ))}
    </nav>
  );
}

function OrgCard() {
  const { organization } = useAuth();
  if (!organization) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-white">
      <span className="block truncate text-sm font-semibold">{organization.name}</span>
      <span className="block text-xs text-[#a1a1aa]">
        {document(organization.cnpj)} · {ROLE_LABEL[organization.role]}
      </span>
    </div>
  );
}

const NEW_COMPANY = "__nova__";

/** Seletor de empresa no topo, visível quando o usuário tem mais de uma. */
function CompanySelect({ onAdd }: { onAdd: () => void }) {
  const { organization, organizations, setOrganization } = useAuth();
  if (!organization || organizations.length < 2) return null;
  return (
    <label className="flex min-w-0 items-center gap-2 rounded-full border border-line bg-white py-1 pr-1 pl-3 text-sm hover:border-brand">
      <Building2 className="size-4 shrink-0 text-brand" aria-hidden />
      <span className="sr-only">Empresa ativa</span>
      <select
        value={organization.id}
        onChange={(e) => (e.target.value === NEW_COMPANY ? onAdd() : setOrganization(e.target.value))}
        className="max-w-[46vw] min-w-0 cursor-pointer truncate rounded-full bg-transparent py-1 pr-1 font-semibold outline-none sm:max-w-64"
      >
        {organizations.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name} — {document(o.cnpj)}
          </option>
        ))}
        <option value={NEW_COMPANY}>+ Adicionar empresa</option>
      </select>
    </label>
  );
}

function UserMenu({ onAddCompany }: { onAddCompany: () => void }) {
  const { user, signOut } = useAuth();
  const [, navigate] = useLocation();
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className="flex items-center gap-2 rounded-full border border-line bg-white py-1 pr-3 pl-1 text-sm font-semibold hover:border-brand">
        <span className="grid size-8 place-items-center rounded-full bg-graphite text-xs text-white">
          {user?.full_name
            .split(" ")
            .slice(0, 2)
            .map((p) => p[0])
            .join("")
            .toUpperCase()}
        </span>
        <span className="hidden max-w-36 truncate sm:block">{user?.full_name.split(" ")[0]}</span>
        <ChevronDown className="size-4 text-muted" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className="z-50 min-w-56 rounded-xl border border-line bg-white p-1 shadow-xl">
          <div className="px-3 py-2 text-xs text-muted">{user?.email}</div>
          <DropdownMenu.Item onSelect={() => navigate("/perfil")} className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm outline-none data-[highlighted]:bg-pale">
            <UserIcon className="size-4" /> Meu perfil
          </DropdownMenu.Item>
          <DropdownMenu.Item onSelect={() => navigate("/perfil")} className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm outline-none data-[highlighted]:bg-pale">
            <ShieldCheck className="size-4" /> Segurança e 2FA {!user?.totp_enabled && <span className="ml-auto size-2 rounded-full bg-amber-500" />}
          </DropdownMenu.Item>
          <DropdownMenu.Item onSelect={onAddCompany} className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm outline-none data-[highlighted]:bg-pale">
            <Building2 className="size-4" /> Adicionar empresa
          </DropdownMenu.Item>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <DropdownMenu.Item onSelect={() => signOut()} className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-red outline-none data-[highlighted]:bg-red-50">
            <LogOut className="size-4" /> Sair
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function BalancePill() {
  const { organization } = useAuth();
  const { data } = useQuery({
    queryKey: ["wallet", organization?.id],
    queryFn: () => api<{ balance_cents: number; credit_limit_cents: number }>("/wallet/"),
    enabled: !!organization,
  });
  // Plano pós-pago: depois que o crédito pré-pago acaba, mostra o consumo que vai para a fatura.
  const postpaid = !!data && data.credit_limit_cents > 0 && data.balance_cents < 0;
  return (
    <Link href="/carteira" className="flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5 text-sm hover:border-brand">
      <Wallet className="size-4 text-brand" aria-hidden />
      <span className="hidden text-muted sm:inline">{postpaid ? "A faturar" : "Saldo"}</span>
      <strong className="font-semibold">{data ? money(postpaid ? Math.max(-data.balance_cents, 0) : data.balance_cents) : "…"}</strong>
    </Link>
  );
}

/** Aviso de fim do teste e de fatura vencida, no topo de todas as telas. */
function BillingBanner() {
  const { data } = useBilling();
  const [location] = useLocation();
  if (!data?.applies || location === "/planos") return null;
  const sub = data.subscription;
  let text: string | null = null;
  let tone = "bg-brand-50 text-graphite";
  if (sub.status === "trialing") {
    const days = daysUntil(sub.trial_ends_at);
    if (days > 7) return null;
    text = days === 0 ? `Seu teste do ${sub.plan.name} termina hoje.` : `Faltam ${days} dia${days > 1 ? "s" : ""} do seu teste do ${sub.plan.name}.`;
  } else if (sub.status === "past_due") {
    text = "Você tem uma fatura vencida. Pague para não ter os recursos suspensos.";
    tone = "bg-warn-50 text-[#6b4e00]";
  } else if (sub.status === "suspended") {
    text = "Assinatura suspensa por falta de pagamento. Pague a fatura para liberar os recursos.";
    tone = "bg-red-50 text-red";
  }
  if (!text) return null;
  return (
    <div className={clsx("no-print flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-4 py-2 text-center text-sm", tone)}>
      <span>{text}</span>
      <Link href="/planos" className="font-semibold underline">
        {sub.status === "trialing" ? "Ver planos" : "Ver fatura"}
      </Link>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const sidebar = (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
      <div className="flex items-center justify-between px-1 pt-1">
        <Link href="/" onClick={() => setOpen(false)}>
          <Logo light />
        </Link>
        <button className="rounded-lg p-1 text-white lg:hidden" onClick={() => setOpen(false)} aria-label="Fechar menu">
          <X className="size-5" />
        </button>
      </div>
      <OrgCard />
      <NavItems onNavigate={() => setOpen(false)} />
      <div className="mt-auto rounded-xl bg-white/5 p-3 text-xs text-[#a1a1aa]">
        Precisa de ajuda?{" "}
        <a className="font-semibold text-mint" href="https://wa.me/5584986276144" target="_blank" rel="noopener noreferrer">
          Fale no WhatsApp
        </a>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[240px_1fr]">
      <a href="#conteudo" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-white focus:p-2">
        Pular para o conteúdo
      </a>
      <aside className="sticky top-0 hidden h-dvh bg-graphite lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-graphite/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 bg-graphite">{sidebar}</aside>
        </div>
      )}
      <div className="min-w-0">
        <header className="no-print sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-line bg-white/90 px-4 backdrop-blur sm:px-6">
          <button className="rounded-lg p-2 text-ink lg:hidden" onClick={() => setOpen(true)} aria-label="Abrir menu">
            <Menu className="size-5" />
          </button>
          <div className="ml-auto flex min-w-0 items-center gap-2 sm:gap-3">
            <CompanySelect onAdd={() => setAdding(true)} />
            <BalancePill />
            <UserMenu onAddCompany={() => setAdding(true)} />
          </div>
        </header>
        <BillingBanner />
        <main id="conteudo" className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
          {children}
          <LegalFooter className="no-print mt-12 border-t border-line pt-6" />
        </main>
        <AddCompanyModal open={adding} onOpenChange={setAdding} />
      </div>
    </div>
  );
}
