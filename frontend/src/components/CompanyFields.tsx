import { CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";
import type { FieldValues, Path, PathValue, UseFormReturn } from "react-hook-form";

import { Field, Input, Select } from "@/components/ui";
import { maskDocument, UFS } from "@/lib/format";
import { lookupCompany } from "@/lib/lookup";

type CompanyForm = { cnpj: string; legal_name: string; trade_name?: string; kind: string; uf: string; city: string };

/** Campos de empresa com preenchimento automático (razão social, fantasia, UF e cidade) a partir do CNPJ. */
export function CompanyFields<T extends FieldValues & CompanyForm>({ form }: { form: UseFormReturn<T> }) {
  const { register, setValue, formState } = form;
  const e = formState.errors as Record<string, { message?: string } | undefined>;
  const [state, setState] = useState<"idle" | "loading" | "found" | "missing">("idle");
  const set = (name: keyof CompanyForm, value: string) =>
    setValue(name as Path<T>, value as PathValue<T, Path<T>>, { shouldValidate: true, shouldDirty: true });

  const onCnpj = async (raw: string) => {
    const masked = maskDocument(raw);
    set("cnpj", masked);
    const digits = masked.replace(/[^0-9A-Za-z]/g, "");
    if (digits.length !== 14) {
      setState("idle");
      return;
    }
    setState("loading");
    const info = await lookupCompany(digits);
    if (!info) {
      setState("missing");
      return;
    }
    set("legal_name", info.legal_name);
    if (info.trade_name) set("trade_name", info.trade_name);
    if (info.uf) set("uf", info.uf);
    if (info.city) set("city", info.city);
    setState("found");
  };

  return (
    <>
      <Field
        label="CNPJ"
        htmlFor="cnpj"
        error={e.cnpj?.message}
        hint={
          state === "found"
            ? undefined
            : state === "missing"
              ? "Não encontramos este CNPJ na Receita. Preencha os dados abaixo."
              : "Digite o CNPJ e preenchemos os dados da empresa para você."
        }
      >
        <div className="relative">
          <Input
            id="cnpj"
            inputMode="text"
            placeholder="00.000.000/0000-00"
            autoComplete="off"
            aria-invalid={!!e.cnpj}
            {...register("cnpj" as Path<T>, { onChange: (ev) => onCnpj(ev.target.value) })}
          />
          <span className="absolute top-1/2 right-3 -translate-y-1/2">
            {state === "loading" && <Loader2 className="size-4 animate-spin text-muted" aria-label="Buscando dados" />}
            {state === "found" && <CheckCircle2 className="size-4 text-green" aria-label="Dados encontrados" />}
          </span>
        </div>
      </Field>
      <Field label="Razão social" htmlFor="legal_name" error={e.legal_name?.message}>
        <Input id="legal_name" placeholder="Nome registrado na Receita Federal" autoComplete="organization" aria-invalid={!!e.legal_name} {...register("legal_name" as Path<T>)} />
      </Field>
      <Field label="Nome fantasia (opcional)" htmlFor="trade_name">
        <Input id="trade_name" placeholder="Como sua loja é conhecida" {...register("trade_name" as Path<T>)} />
      </Field>
      <Field label="Tipo de negócio" htmlFor="kind">
        <Select id="kind" {...register("kind" as Path<T>)}>
          <option value="revenda">Loja / revenda</option>
          <option value="concessionaria">Concessionária</option>
          <option value="despachante">Despachante</option>
          <option value="contador">Contador</option>
        </Select>
      </Field>
      <div className="grid grid-cols-[110px_1fr] gap-4">
        <Field label="UF" htmlFor="uf" error={e.uf?.message}>
          <Select id="uf" aria-invalid={!!e.uf} {...register("uf" as Path<T>)}>
            <option value="">UF</option>
            {UFS.map((u) => (
              <option key={u}>{u}</option>
            ))}
          </Select>
        </Field>
        <Field label="Cidade" htmlFor="city" error={e.city?.message}>
          <Input id="city" placeholder="Cidade da empresa" autoComplete="address-level2" aria-invalid={!!e.city} {...register("city" as Path<T>)} />
        </Field>
      </div>
    </>
  );
}
