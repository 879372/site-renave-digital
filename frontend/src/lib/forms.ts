import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { toast } from "sonner";

import { ApiError } from "./api";

/** Aplica erros de campo da API no formulário e mostra a mensagem geral. */
export function handleApiError<T extends FieldValues>(error: unknown, setError?: UseFormSetError<T>) {
  if (error instanceof ApiError) {
    if (error.fields && setError) {
      let applied = false;
      for (const [name, messages] of Object.entries(error.fields)) {
        const message = Array.isArray(messages) ? String(messages[0]) : String(messages);
        if (name === "non_field_errors") continue;
        setError(name as Path<T>, { message });
        applied = true;
      }
      if (applied) {
        toast.error("Confira os campos destacados.");
        return;
      }
    }
    toast.error(error.message);
    return;
  }
  toast.error("Falha de conexão. Verifique sua internet e tente novamente.");
}
