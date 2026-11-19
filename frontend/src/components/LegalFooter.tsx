import { Link } from "wouter";

import { LEGAL } from "@/lib/legal";

export function LegalFooter({ className = "" }: { className?: string }) {
  return (
    <nav aria-label="Documentos legais" className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted ${className}`}>
      <span>© {new Date().getFullYear()} {LEGAL.brand}</span>
      <Link href="/termos-de-uso" className="hover:text-ink hover:underline">
        Termos de uso
      </Link>
      <Link href="/politica-de-privacidade" className="hover:text-ink hover:underline">
        Política de privacidade
      </Link>
      <a href={`mailto:${LEGAL.dpoEmail}`} className="hover:text-ink hover:underline">
        Encarregado de dados (LGPD)
      </a>
    </nav>
  );
}
