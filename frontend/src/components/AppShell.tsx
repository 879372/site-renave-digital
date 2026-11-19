import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Building2,
  Car,
  ChevronDown,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  ScrollText,
  Search,
  Send,
  ShieldCheck,
  User as UserIcon,
  Wallet,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useLocation } from "wouter";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { document, money, ROLE_LABEL } from "@/lib/format";

import { AddCompanyModal } from "./AddCompanyModal";
import { LegalFooter } from "./LegalFooter";

const NAV = [
  { href: "/", label: "Painel", icon: LayoutDashboard },
  { href: "/consultas", label: "Consultas", icon: Search },
  { href: "/estoque", label: "Estoque RENAVE", icon: Car },
  { href: "/comunicacao-venda", label: "Comunicação de venda", icon: Send },
  { href: "/notas", label: "Notas fiscais", icon: FileText },
  { href: "/carteira", label: "Carteira", icon: Wallet },
  { href: "/empresa", label: "Empresa", icon: Building2 },
  { href: "/auditoria", label: "Auditoria", icon: ScrollText, perm: "audit.view" },
];

export function Logo({ light }: { light?: boolean }) {
  return (
    <span className="flex items-center gap-2.5 leading-none">
      <img src="/simbolo.svg" alt="" width={36} height={36} />
      <span className={clsx("font-display text-lg font-extrabold tracking-tight", light ? "text-white" : "text-navy")}>
        RENAVE <span className={light ? "text-yellow" : "text-blue"}>DIGITAL</span>
      </span>
    </span>
  );
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  const [location] = useLocation();
  const { can } = useAuth();
  return (
    <nav className="flex flex-col gap-1" aria-label="Principal">
      {NAV.filter((n) => !n.perm || can(n.perm)).map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? location === "/" : location.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={clsx(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] font-medium transition",
              active ? "bg-white/10 text-white" : "text-[#c7d0ed] hover:bg-white/5 hover:text-white",
            )}
            aria-current={active ? "page" : undefined}
          >
            <Icon className={clsx("size-[18px]", active && "text-yellow")} aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function OrgCard() {
  const { organization } = useAuth();
  if (!organization) return null;
  return (
    <div className="rounded-xl border border-white/15 bg-white/5 px-3 py-2.5 text-white">
      <span className="block truncate text-sm font-semibold">{organization.name}</span>
      <span className="block text-xs text-[#c7d0ed]">
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
    <label className="flex min-w-0 items-center gap-2 rounded-full border border-line bg-white py-1 pr-1 pl-3 text-sm hover:border-blue">
      <Building2 className="size-4 shrink-0 text-blue" aria-hidden />
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
      <DropdownMenu.Trigger className="flex items-center gap-2 rounded-full border border-line bg-white py-1 pr-3 pl-1 text-sm font-semibold hover:border-blue">
        <span className="grid size-8 place-items-center rounded-full bg-navy text-xs text-white">
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
            <ShieldCheck className="size-4" /> Segurança e 2FA {!user?.totp_enabled && <span className="ml-auto size-2 rounded-full bg-yellow" />}
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
  const { data } = useQuery({ queryKey: ["wallet", organization?.id], queryFn: () => api<{ balance_cents: number }>("/wallet/"), enabled: !!organization });
  return (
    <Link href="/carteira" className="flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5 text-sm hover:border-blue">
      <Wallet className="size-4 text-blue" aria-hidden />
      <span className="hidden text-muted sm:inline">Saldo</span>
      <strong className="font-semibold">{data ? money(data.balance_cents) : "…"}</strong>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const sidebar = (
    <div className="flex h-full flex-col gap-6 p-4">
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
      <div className="mt-auto rounded-xl bg-white/5 p-3 text-xs text-[#c7d0ed]">
        Precisa de ajuda?{" "}
        <a className="font-semibold text-yellow" href="https://wa.me/5584986276144" target="_blank" rel="noopener noreferrer">
          Fale no WhatsApp
        </a>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[260px_1fr]">
      <a href="#conteudo" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-white focus:p-2">
        Pular para o conteúdo
      </a>
      <aside className="sticky top-0 hidden h-dvh bg-navy lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 bg-navy">{sidebar}</aside>
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
        <main id="conteudo" className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
          {children}
          <LegalFooter className="no-print mt-12 border-t border-line pt-6" />
        </main>
        <AddCompanyModal open={adding} onOpenChange={setAdding} />
      </div>
    </div>
  );
}
