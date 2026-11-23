import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, ExternalLink, Globe } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { PlanGate } from "@/components/PlanGate";
import { Button, Card, Field, Input, PageHeader, Spinner, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { maskPhone, onlyDigits } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

type Site = { slug: string; is_published: boolean; title: string; about: string; whatsapp: string; phone: string; email: string; address: string; instagram: string; accent_color: string; url: string; feed_url: string | null };

export function SitePage() {
  const { organization, can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["site", organization?.id], queryFn: async () => { const r = await api<Site | { configured: false }>("/site/"); return "slug" in r ? r : null; } });
  const [f, setF] = useState<Partial<Site>>({ accent_color: "#047857" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (q.data) setF(q.data);
    else if (q.data === null && organization) setF({ title: organization.name, slug: organization.name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40), accent_color: "#047857" });
  }, [q.data, organization]);
  const save = useMutation({
    mutationFn: () => api<Site>("/site/", { method: "PUT", body: { ...f, whatsapp: onlyDigits(f.whatsapp ?? ""), phone: onlyDigits(f.phone ?? "") } }),
    onSuccess: (s) => { qc.setQueryData(["site", organization?.id], s); setErrors({}); toast.success("Site salvo"); },
    onError: (e: any) => { const x: Record<string, string> = {}; Object.entries(e?.fields ?? {}).forEach(([k, v]) => (x[k] = Array.isArray(v) ? String(v[0]) : String(v))); setErrors(x); handleApiError(e); },
  });
  const rotate = useMutation({ mutationFn: () => api<Site>("/site/", { body: {} }), onSuccess: (s) => { qc.setQueryData(["site", organization?.id], s); toast.success("Novo link do feed gerado"); } });
  const manage = can("org.manage");
  const copy = (t: string) => navigator.clipboard.writeText(t).then(() => toast.success("Copiado"));
  const set = (k: keyof Site, v: unknown) => setF((x) => ({ ...x, [k]: v }));
  return (
    <>
      <PageHeader title="Site da loja" description="Vitrine pública com os carros publicados, botão de WhatsApp e formulário que vira lead." action={q.data?.is_published && <a href={q.data.url} target="_blank" rel="noopener noreferrer"><Button variant="secondary"><ExternalLink className="size-4" /> Ver site</Button></a>} />
      <PlanGate feature="vitrine" title="Site da loja">
        {q.isLoading ? <Spinner /> : (
          <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
            <Card title="Configuração">
              <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
                <Field label="Endereço do site" htmlFor="s-slug" error={errors.slug} hint="Letras minúsculas, números e hífen.">
                  <div className="flex items-center gap-2">
                    <Input id="s-slug" disabled={!manage} value={f.slug ?? ""} onChange={(e) => set("slug", e.target.value.toLowerCase())} className="max-w-56" />
                    <span className="text-sm text-muted">.revendadigital.kaibez.com.br</span>
                  </div>
                </Field>
                <Field label="Nome no site" htmlFor="s-t"><Input id="s-t" disabled={!manage} required value={f.title ?? ""} onChange={(e) => set("title", e.target.value)} /></Field>
                <Field label="Sobre a loja" htmlFor="s-a"><Textarea id="s-a" disabled={!manage} rows={3} value={f.about ?? ""} onChange={(e) => set("about", e.target.value)} /></Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="WhatsApp" htmlFor="s-w"><Input id="s-w" disabled={!manage} value={maskPhone(f.whatsapp ?? "")} onChange={(e) => set("whatsapp", e.target.value)} /></Field>
                  <Field label="Telefone" htmlFor="s-p"><Input id="s-p" disabled={!manage} value={maskPhone(f.phone ?? "")} onChange={(e) => set("phone", e.target.value)} /></Field>
                  <Field label="E-mail" htmlFor="s-e"><Input id="s-e" disabled={!manage} value={f.email ?? ""} onChange={(e) => set("email", e.target.value)} /></Field>
                  <Field label="Instagram" htmlFor="s-i"><Input id="s-i" disabled={!manage} value={f.instagram ?? ""} onChange={(e) => set("instagram", e.target.value)} placeholder="@sualoja" /></Field>
                  <Field label="Endereço" htmlFor="s-ad" className="sm:col-span-2"><Input id="s-ad" disabled={!manage} value={f.address ?? ""} onChange={(e) => set("address", e.target.value)} /></Field>
                  <Field label="Cor de destaque" htmlFor="s-c" error={errors.accent_color}><Input id="s-c" type="color" disabled={!manage} value={f.accent_color ?? "#047857"} onChange={(e) => set("accent_color", e.target.value)} className="h-10 w-20 p-1" /></Field>
                </div>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-brand" disabled={!manage} checked={!!f.is_published} onChange={(e) => set("is_published", e.target.checked)} /> Site no ar</label>
                {manage && <Button type="submit" loading={save.isPending}>Salvar</Button>}
              </form>
            </Card>
            <div className="space-y-6">
              <Card title="Endereço">
                {q.data ? (
                  <div className="space-y-2 text-sm">
                    <p className="flex items-center gap-2 break-all"><Globe className="size-4 shrink-0 text-muted" /> {q.data.url}</p>
                    <p className="text-muted">{q.data.is_published ? "No ar." : "Fora do ar: marque “Site no ar” para publicar."}</p>
                  </div>
                ) : <p className="text-sm text-muted">Salve a configuração para criar o site.</p>}
              </Card>
              <Card title="Feed para portais" description="Cadastre este link no integrador do portal (OLX, Webmotors, iCarros…). Ele lista os carros marcados para cada portal na ficha do veículo.">
                {q.data?.feed_url ? (
                  <div className="space-y-2">
                    <code className="block rounded-md bg-pale p-2 text-xs break-all">{q.data.feed_url}</code>
                    <div className="flex gap-2">
                      <Button size="sm" variant="secondary" onClick={() => copy(q.data!.feed_url!)}><Copy className="size-4" /> Copiar</Button>
                      {manage && <Button size="sm" variant="ghost" onClick={() => confirm("Gerar um novo link? O antigo para de funcionar nos portais.") && rotate.mutate()}>Gerar novo link</Button>}
                    </div>
                    <p className="text-xs text-muted">Para um portal específico, acrescente <code>?portal=olx</code> (ou webmotors, mercadolivre, icarros, mobiauto).</p>
                  </div>
                ) : <p className="text-sm text-muted">Disponível depois de salvar o site.</p>}
              </Card>
            </div>
          </div>
        )}
      </PlanGate>
    </>
  );
}
