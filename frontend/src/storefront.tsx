/**
 * Site público da loja. Abre em <slug>.revendadigital.kaibez.com.br (ou /loja/<slug> no desenvolvimento).
 * Só usa as rotas públicas da API: nada de sessão, cookies de login ou dados internos.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Car, Instagram, MapPin, MessageCircle, Phone, Search } from "lucide-react";
import { useState, type CSSProperties } from "react";
import { Link, Route, Switch, useParams } from "wouter";

import { Button, Field, Input, Spinner, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { maskPhone, money, onlyDigits } from "@/lib/format";

export { storefrontSlug } from "./storefront-slug";

type Site = { slug: string; title: string; name: string; about: string; whatsapp: string; phone: string; email: string; address: string; instagram: string; accent_color: string; logo_url: string | null };
type Item = { id: string; title: string; marca: string; modelo: string; versao: string; ano_fabricacao: number; ano_modelo: number; km: number | null; cor: string; cambio: string; combustivel: string; price_cents: number | null; reserved: boolean; featured: boolean; cover: string | null; photos?: string[]; opcionais?: string[]; descricao?: string; final_placa?: string };

const pub = <T,>(path: string, opts: Parameters<typeof api>[1] = {}) => api<T>(`/public/lojas/${path}`, { ...opts, auth: false });

export function Storefront({ slug }: { slug: string }) {
  const site = useQuery({ queryKey: ["pub-site", slug], queryFn: () => pub<Site>(slug), retry: false });
  const base = window.location.pathname.startsWith("/loja/") ? `/loja/${slug}` : "";
  if (site.isLoading) return <Spinner />;
  if (!site.data) return <div className="grid min-h-dvh place-items-center p-6 text-center"><div><Car className="mx-auto size-10 text-muted" /><p className="mt-3 font-semibold">Site não encontrado</p><p className="text-sm text-muted">Esta loja não está com o site no ar.</p></div></div>;
  const s = site.data;
  document.title = s.title;
  const style = { "--accent": s.accent_color } as CSSProperties;
  const wa = onlyDigits(s.whatsapp);
  return (
    <div style={style} className="min-h-dvh bg-[#f7f7f8]">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4">
          <Link href={base || "/"} className="flex items-center gap-3">
            {s.logo_url ? <img src={s.logo_url} alt="" className="h-10 w-10 rounded-lg object-cover" /> : <span className="grid size-10 place-items-center rounded-lg text-white" style={{ background: s.accent_color }}><Car className="size-5" /></span>}
            <span className="text-lg font-semibold">{s.title}</span>
          </Link>
          {wa && <a href={`https://wa.me/55${wa}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white" style={{ background: s.accent_color }}><MessageCircle className="size-4" /> WhatsApp</a>}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Switch>
          <Route path={`${base}/veiculo/:id`}>{() => <Detail slug={slug} site={s} base={base} />}</Route>
          <Route>{() => <List slug={slug} base={base} site={s} />}</Route>
        </Switch>
      </main>
      <footer className="border-t border-line bg-white">
        <div className="mx-auto grid max-w-6xl gap-4 px-4 py-6 text-sm text-muted sm:grid-cols-3">
          <p>{s.about || s.name}</p>
          <div className="space-y-1">
            {s.address && <p className="flex items-center gap-2"><MapPin className="size-4" /> {s.address}</p>}
            {s.phone && <p className="flex items-center gap-2"><Phone className="size-4" /> {maskPhone(s.phone)}</p>}
            {s.instagram && <a className="flex items-center gap-2" href={`https://instagram.com/${s.instagram.replace("@", "")}`} target="_blank" rel="noopener noreferrer"><Instagram className="size-4" /> {s.instagram}</a>}
          </div>
          <p className="sm:text-right">Site feito com REVENDA DIGITAL</p>
        </div>
      </footer>
    </div>
  );
}

function List({ slug, base, site }: { slug: string; base: string; site: Site }) {
  const [q, setQ] = useState("");
  const [marca, setMarca] = useState("");
  const data = useQuery({ queryKey: ["pub-list", slug, q, marca], queryFn: () => pub<{ brands: string[]; results: Item[] }>(`${slug}/veiculos`, { params: { q, marca } }) });
  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold">Nosso estoque</h1>
        <div className="flex gap-2">
          <div className="relative"><Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar modelo" className="h-10 w-56 pl-9" aria-label="Buscar modelo" /></div>
          <select value={marca} onChange={(e) => setMarca(e.target.value)} className="h-10 rounded-lg border border-line bg-white px-3 text-sm" aria-label="Marca"><option value="">Todas as marcas</option>{data.data?.brands.map((b) => <option key={b}>{b}</option>)}</select>
        </div>
      </div>
      {data.isLoading ? <Spinner /> : !data.data?.results.length ? <p className="py-16 text-center text-muted">Nenhum carro encontrado.</p> : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.data.results.map((v) => (
            <Link key={v.id} href={`${base}/veiculo/${v.id}`} className="overflow-hidden rounded-xl border border-line bg-white transition hover:shadow-md">
              {v.cover ? <img src={v.cover} alt={v.title} className="aspect-[4/3] w-full object-cover" loading="lazy" /> : <div className="grid aspect-[4/3] place-items-center bg-pale"><Car className="size-8 text-muted" /></div>}
              <div className="p-4">
                <p className="font-semibold">{v.marca} {v.modelo}</p>
                <p className="text-sm text-muted">{[v.versao, `${v.ano_fabricacao}/${v.ano_modelo}`, v.km != null && `${v.km.toLocaleString("pt-BR")} km`].filter(Boolean).join(" · ")}</p>
                <p className="mt-2 text-lg font-semibold" style={{ color: site.accent_color }}>{v.price_cents ? money(v.price_cents) : "Consulte"}</p>
                {v.reserved && <span className="text-xs text-muted">Reservado</span>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}

function Detail({ slug, site, base }: { slug: string; site: Site; base: string }) {
  const { id } = useParams<{ id: string }>();
  const v = useQuery({ queryKey: ["pub-item", slug, id], queryFn: () => pub<Item>(`${slug}/veiculos/${id}`) });
  const [photo, setPhoto] = useState(0);
  const [f, setF] = useState({ name: "", phone: "", email: "", message: "", consent: false, website: "" });
  const [sent, setSent] = useState(false);
  const contact = useMutation({ mutationFn: () => pub(`${slug}/contato`, { body: { ...f, phone: onlyDigits(f.phone), vehicle_id: id } }), onSuccess: () => setSent(true) });
  if (v.isLoading) return <Spinner />;
  const item = v.data;
  if (!item) return <p className="py-16 text-center text-muted">Carro não encontrado ou já vendido.</p>;
  const wa = onlyDigits(site.whatsapp);
  const waText = encodeURIComponent(`Olá! Tenho interesse no ${item.title}.`);
  return (
    <>
      <Link href={base || "/"} className="mb-4 inline-flex items-center gap-1 text-sm text-muted"><ArrowLeft className="size-4" /> Voltar ao estoque</Link>
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div>
          {item.photos?.length ? (
            <>
              <img src={item.photos[photo]} alt={item.title} className="aspect-[16/10] w-full rounded-xl object-cover" />
              <div className="mt-2 flex gap-2 overflow-x-auto">{item.photos.map((p, i) => <button key={p} onClick={() => setPhoto(i)} className={`shrink-0 overflow-hidden rounded-md border-2 ${i === photo ? "border-[var(--accent)]" : "border-transparent"}`}><img src={p} alt="" className="h-16 w-24 object-cover" /></button>)}</div>
            </>
          ) : <div className="grid aspect-[16/10] place-items-center rounded-xl bg-pale"><Car className="size-10 text-muted" /></div>}
          <div className="mt-6 rounded-xl border border-line bg-white p-5">
            <h2 className="mb-3 font-semibold">Detalhes</h2>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
              {[["Ano", `${item.ano_fabricacao}/${item.ano_modelo}`], ["Km", item.km != null ? item.km.toLocaleString("pt-BR") : "—"], ["Cor", item.cor], ["Câmbio", item.cambio], ["Combustível", item.combustivel], ["Final da placa", item.final_placa]].map(([k, val]) => <div key={k}><dt className="text-muted">{k}</dt><dd className="font-medium">{val || "—"}</dd></div>)}
            </dl>
            {!!item.opcionais?.length && <p className="mt-4 text-sm text-muted">{item.opcionais.join(" · ")}</p>}
            {item.descricao && <p className="mt-4 text-sm whitespace-pre-line">{item.descricao}</p>}
          </div>
        </div>
        <aside className="space-y-4">
          <div className="rounded-xl border border-line bg-white p-5">
            <h1 className="text-xl font-semibold">{item.marca} {item.modelo}</h1>
            <p className="text-sm text-muted">{item.versao}</p>
            <p className="mt-3 text-2xl font-semibold" style={{ color: site.accent_color }}>{item.price_cents ? money(item.price_cents) : "Consulte"}</p>
            {item.reserved && <p className="text-sm text-muted">Reservado no momento</p>}
            {wa && <a href={`https://wa.me/55${wa}?text=${waText}`} target="_blank" rel="noopener noreferrer" className="mt-4 flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-white" style={{ background: site.accent_color }}><MessageCircle className="size-4" /> Chamar no WhatsApp</a>}
          </div>
          <div className="rounded-xl border border-line bg-white p-5">
            {sent ? <p className="text-sm">Recebemos seu contato. A loja vai falar com você em breve.</p> : (
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); contact.mutate(); }}>
                <h2 className="font-semibold">Quero mais informações</h2>
                <Field label="Nome" htmlFor="ct-n"><Input placeholder="Seu nome" id="ct-n" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
                <Field label="Telefone / WhatsApp" htmlFor="ct-p"><Input placeholder="(84) 99999-9999" id="ct-p" required value={f.phone} onChange={(e) => setF({ ...f, phone: maskPhone(e.target.value) })} /></Field>
                <Field label="Mensagem (opcional)" htmlFor="ct-m"><Textarea placeholder="Aceita troca? Qual a menor entrada?" id="ct-m" rows={2} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} /></Field>
                <input tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} />
                <label className="flex items-start gap-2 text-xs text-muted"><input type="checkbox" required className="mt-0.5 size-4" checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} /> Autorizo a loja a entrar em contato sobre este veículo.</label>
                <Button type="submit" className="w-full" loading={contact.isPending}>Enviar</Button>
                {contact.isError && <p className="text-sm text-red">Não foi possível enviar. Tente pelo WhatsApp.</p>}
              </form>
            )}
          </div>
        </aside>
      </div>
    </>
  );
}
