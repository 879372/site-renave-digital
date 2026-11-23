import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { handleApiError } from "@/lib/forms";

import { CompanyFields } from "./CompanyFields";
import { Button, Modal } from "./ui";

const schema = z.object({
  cnpj: z.string().min(14, "Informe o CNPJ."),
  legal_name: z.string().min(3, "Informe a razão social."),
  trade_name: z.string().optional(),
  uf: z.string().length(2, "Selecione a UF."),
  city: z.string().min(2, "Informe a cidade."),
});
type Values = z.infer<typeof schema>;

export function AddCompanyModal({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { reload, setOrganization } = useAuth();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { uf: "" } });
  const submit = form.handleSubmit(async (values) => {
    try {
      const org = await api<{ id: string; name: string }>("/organizations/", { body: values });
      await reload();
      setOrganization(org.id);
      toast.success(`${org.name} adicionada. Você já está operando com ela.`);
      form.reset();
      onOpenChange(false);
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Adicionar empresa" description="Cadastre outro CNPJ seu para consultar, operar o RENAVE e emitir notas por ele.">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <CompanyFields form={form} />
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Adicionar empresa
        </Button>
      </form>
    </Modal>
  );
}
