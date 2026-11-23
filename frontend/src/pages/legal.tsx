import { ArrowLeft, Printer } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "wouter";

import { Logo } from "@/components/AppShell";
import { LegalFooter } from "@/components/LegalFooter";
import { Button } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { LEGAL } from "@/lib/legal";

function LegalLayout({ title, children }: { title: string; children: ReactNode }) {
  const { status } = useAuth();
  return (
    <div className="min-h-dvh bg-white">
      <header className="no-print border-b border-line">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4">
          <Link href="/">
            <Logo />
          </Link>
          <Button variant="ghost" size="sm" onClick={() => window.print()}>
            <Printer className="size-4" /> Imprimir
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Link href={status === "authenticated" ? "/" : "/entrar"} className="no-print mb-6 inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink">
          <ArrowLeft className="size-4" /> Voltar
        </Link>
        <h1 className="text-4xl font-semibold">{title}</h1>
        <p className="mt-2 text-sm text-muted">Versão vigente: {LEGAL.version.split("-").reverse().join("/")}</p>
        <article className="legal mt-8 space-y-4 text-[15px] leading-7 text-ink [&_h2]:mt-10 [&_h2]:font-display [&_h2]:text-2xl [&_h2]:font-semibold [&_h3]:mt-6 [&_h3]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_p]:text-muted [&_li]:text-muted">
          {children}
        </article>
        <LegalFooter className="mt-16" />
      </main>
    </div>
  );
}

export function TermsPage() {
  return (
    <LegalLayout title="Termos de Uso">
      <p>
        Estes Termos regulam o uso da plataforma {LEGAL.brand} ("Plataforma"), mantida por {LEGAL.companyName}, inscrita no CNPJ {LEGAL.cnpj}, com sede em {LEGAL.address} ("nós"). Ao criar uma conta ou usar a Plataforma, você declara que leu e concorda com estes Termos e com a{" "}
        <Link href="/politica-de-privacidade" className="font-semibold text-brand">
          Política de Privacidade
        </Link>
        .
      </p>

      <h2>1. O que a Plataforma oferece</h2>
      <ul>
        <li>Consultas de informações veiculares e cadastrais, a partir de bases de dados de terceiros;</li>
        <li>Gestão do estoque no RENAVE (Registro Nacional de Veículos em Estoque) por meio de integradora autorizada;</li>
        <li>Comunicação eletrônica de venda de veículos aos órgãos de trânsito;</li>
        <li>Emissão de Nota Fiscal Eletrônica (NF-e) de veículos.</li>
      </ul>
      <p>
        A Plataforma é uma ferramenta privada de tecnologia e <strong>não é órgão público</strong>. Não possui vínculo com Senatran, Serpro, Detrans ou Secretarias da Fazenda. A disponibilidade de cada serviço depende das integrações, das habilitações da sua empresa e da UF.
      </p>

      <h2>2. Cadastro e conta</h2>
      <ul>
        <li>A Plataforma é destinada a pessoas jurídicas que revendem veículos (lojas e revendas multimarcas) e a seus representantes maiores de 18 anos.</li>
        <li>Você deve informar dados verdadeiros e mantê-los atualizados. O titular da conta responde pelos atos praticados pelos usuários que convidar.</li>
        <li>As credenciais são pessoais e intransferíveis. Recomendamos ativar a verificação em duas etapas. Avise-nos imediatamente sobre qualquer uso não autorizado.</li>
      </ul>

      <h2>3. Uso das consultas</h2>
      <p>
        As consultas podem retornar dados pessoais de terceiros (por exemplo, proprietários de veículos). Ao consultar, você declara uma finalidade legítima — como avaliação de compra, venda, financiamento ou regularização documental — e se compromete a:
      </p>
      <ul>
        <li>usar as informações apenas para a finalidade declarada, conforme a Lei nº 13.709/2018 (LGPD);</li>
        <li>não revender, divulgar, compartilhar ou formar bancos de dados com as informações obtidas;</li>
        <li>não usar a Plataforma para assédio, discriminação, fraude ou qualquer finalidade ilícita.</li>
      </ul>
      <p>
        As informações refletem o conteúdo das bases consultadas no momento da pesquisa. Não garantimos que estejam completas ou livres de erros das fontes, e elas não substituem documentos oficiais emitidos pelos órgãos competentes.
      </p>

      <h2>4. RENAVE, comunicação de venda e NF-e</h2>
      <ul>
        <li>As operações são realizadas com o certificado digital ICP-Brasil da sua empresa, que você nos confia para essa finalidade. Ele é armazenado com criptografia e usado apenas quando você solicita uma operação.</li>
        <li>Você é responsável pela veracidade dos dados informados e pelas obrigações fiscais e de trânsito decorrentes. Parâmetros fiscais (CFOP, CSOSN, NCM etc.) devem ser validados pelo seu contador.</li>
        <li>Credenciamento, habilitação e autorizações dependem exclusivamente dos órgãos competentes.</li>
      </ul>

      <h2>5. Créditos, preços e estornos</h2>
      <ul>
        <li>Os serviços são pagos com créditos pré-pagos. Os preços vigentes ficam disponíveis na Carteira antes de cada operação.</li>
        <li>Quando a fonte não retorna resultado e não cobra a tentativa, o valor é estornado automaticamente aos seus créditos.</li>
        <li>Créditos não utilizados podem ser restituídos mediante solicitação, descontadas taxas de pagamento comprovadas.</li>
      </ul>

      <h2>6. Disponibilidade</h2>
      <p>
        Empregamos esforços razoáveis para manter a Plataforma disponível, mas ela depende de serviços de terceiros e de órgãos públicos, que podem ficar indisponíveis. Manutenções programadas serão comunicadas sempre que possível.
      </p>

      <h2>7. Suspensão e encerramento</h2>
      <p>
        Podemos suspender ou encerrar contas em caso de violação destes Termos, uso indevido de dados, suspeita de fraude ou determinação legal. Você pode encerrar sua conta a qualquer momento em Meu perfil → Privacidade e dados.
      </p>

      <h2>8. Responsabilidade</h2>
      <p>
        Não respondemos por decisões comerciais tomadas com base nas consultas, por indisponibilidade de serviços de terceiros ou por danos decorrentes de uso em desacordo com estes Termos, ressalvados os direitos previstos no Código de Defesa do Consumidor quando aplicável.
      </p>

      <h2>9. Propriedade intelectual</h2>
      <p>A marca, o software e os conteúdos da Plataforma são protegidos. É vedado copiar, fazer engenharia reversa ou acessar a Plataforma por meios automatizados não autorizados.</p>

      <h2>10. Alterações</h2>
      <p>Podemos atualizar estes Termos. Mudanças relevantes serão informadas na Plataforma e poderão exigir novo aceite para continuar o uso.</p>

      <h2>11. Contato e foro</h2>
      <p>
        Dúvidas: WhatsApp {LEGAL.supportWhatsapp}. Fica eleito o foro da comarca de {LEGAL.forum}, salvo disposição legal em contrário.
      </p>
    </LegalLayout>
  );
}

export function PrivacyPage() {
  return (
    <LegalLayout title="Política de Privacidade">
      <p>
        Esta Política explica como {LEGAL.companyName} (CNPJ {LEGAL.cnpj}), responsável pela plataforma {LEGAL.brand}, trata dados pessoais, em conformidade com a Lei Geral de Proteção de Dados (Lei nº 13.709/2018 — LGPD).
      </p>

      <h2>1. Quem é o controlador e o Encarregado</h2>
      <p>
        Controlador: {LEGAL.companyName}, {LEGAL.address}. Encarregado pelo tratamento de dados (DPO): {LEGAL.dpoName}, e-mail{" "}
        <a href={`mailto:${LEGAL.dpoEmail}`} className="font-semibold text-brand">
          {LEGAL.dpoEmail}
        </a>
        .
      </p>

      <h2>2. Dados que tratamos</h2>
      <h3>Dos usuários da Plataforma</h3>
      <ul>
        <li>Cadastro: nome, CPF, e-mail, telefone, senha (guardada apenas como hash irreversível);</li>
        <li>Empresa: CNPJ, razão social, endereço, inscrição estadual e dados fiscais;</li>
        <li>Certificado digital A1 e sua senha, armazenados com criptografia;</li>
        <li>Registros de acesso: IP, data, hora e ações realizadas (obrigatórios pelo Marco Civil da Internet, art. 15);</li>
        <li>Financeiro: recargas e consumo de créditos.</li>
      </ul>
      <h3>De terceiros, informados ou consultados por você</h3>
      <ul>
        <li>Compradores e vendedores de veículos (nome, CPF/CNPJ, endereço) para RENAVE, comunicação de venda e NF-e;</li>
        <li>Dados retornados pelas consultas veiculares, que podem incluir dados de proprietários.</li>
      </ul>

      <h2>3. Finalidades e bases legais</h2>
      <ul>
        <li><strong>Prestar os serviços contratados</strong> (cadastro, consultas, RENAVE, NF-e) — execução de contrato (art. 7º, V);</li>
        <li><strong>Cumprir obrigações legais e regulatórias</strong> (guarda de registros de acesso, documentos fiscais, operações de trânsito) — art. 7º, II;</li>
        <li><strong>Segurança e prevenção a fraudes</strong>, como verificação em duas etapas e bloqueio de tentativas — legítimo interesse (art. 7º, IX) e art. 11, II, "g";</li>
        <li><strong>Consultas veiculares</strong> realizadas pelos clientes com finalidade declarada — legítimo interesse do cliente e proteção do crédito (art. 7º, IX e X);</li>
        <li><strong>Comunicações comerciais</strong> — somente com seu consentimento, que pode ser retirado a qualquer momento (art. 7º, I).</li>
      </ul>

      <h2>4. Compartilhamento</h2>
      <p>Compartilhamos dados somente no necessário para executar o serviço solicitado, com:</p>
      <ul>
        <li>parceiros tecnológicos contratados (provedores de bases de dados veiculares, integradora autorizada do RENAVE e emissor de documentos fiscais), sob contratos com obrigações de confidencialidade e segurança;</li>
        <li>órgãos públicos (Senatran, Serpro, Detrans, Secretarias da Fazenda), quando a operação exige;</li>
        <li>infraestrutura de hospedagem e processamento de pagamentos;</li>
        <li>autoridades, mediante obrigação legal ou ordem judicial.</li>
      </ul>
      <p>Não vendemos dados pessoais.</p>

      <h2>5. Transferência internacional</h2>
      <p>Alguns fornecedores de infraestrutura podem processar dados fora do Brasil. Nesses casos, adotamos as salvaguardas do art. 33 da LGPD, como cláusulas contratuais específicas.</p>

      <h2>6. Por quanto tempo guardamos</h2>
      <ul>
        <li>Dados da conta: enquanto ela estiver ativa;</li>
        <li>Registros de acesso: 6 meses, no mínimo (Marco Civil da Internet);</li>
        <li>Documentos fiscais e registros de operações: 5 anos (legislação tributária) ou prazo maior exigido por lei;</li>
        <li>Resultados de consultas: pelo período necessário à finalidade e à defesa em eventuais processos.</li>
      </ul>
      <p>Encerrada a conta, os dados são eliminados ou anonimizados, exceto os que precisamos guardar por obrigação legal.</p>

      <h2>7. Segurança</h2>
      <p>
        Usamos conexão criptografada (HTTPS), criptografia dos dados sensíveis armazenados (certificados, resultados de consultas e dados de compradores), senhas com hash Argon2, verificação em duas etapas, controle de acesso por perfil, trilha de auditoria e monitoramento. Em caso de incidente de segurança relevante, comunicaremos os titulares e a ANPD conforme o art. 48 da LGPD.
      </p>

      <h2>8. Cookies e armazenamento local</h2>
      <p>
        A Plataforma usa apenas um cookie estritamente necessário para manter sua sessão (seguro e inacessível a scripts) e o armazenamento local do navegador para lembrar a empresa selecionada. Não usamos cookies de publicidade nem de rastreamento de terceiros.
      </p>

      <h2>9. Seus direitos</h2>
      <p>Conforme o art. 18 da LGPD, você pode:</p>
      <ul>
        <li>confirmar a existência de tratamento e acessar seus dados;</li>
        <li>corrigir dados incompletos, inexatos ou desatualizados;</li>
        <li>solicitar anonimização, bloqueio ou eliminação de dados desnecessários;</li>
        <li>solicitar a portabilidade dos dados;</li>
        <li>obter informação sobre compartilhamentos;</li>
        <li>revogar o consentimento e se opor a tratamentos;</li>
        <li>peticionar à Autoridade Nacional de Proteção de Dados (ANPD).</li>
      </ul>
      <p>
        Na Plataforma, em <strong>Meu perfil → Privacidade e dados</strong>, você baixa seus dados e exclui sua conta. Para os demais pedidos, escreva para{" "}
        <a href={`mailto:${LEGAL.dpoEmail}`} className="font-semibold text-brand">
          {LEGAL.dpoEmail}
        </a>
        . Respondemos em até 15 dias.
      </p>
      <p>
        Se você é titular de dados consultados por um cliente da Plataforma (por exemplo, proprietário de um veículo), também pode exercer seus direitos pelo mesmo e-mail.
      </p>

      <h2>10. Alterações</h2>
      <p>Esta Política pode ser atualizada. A versão vigente fica sempre nesta página, e mudanças relevantes serão comunicadas na Plataforma.</p>
    </LegalLayout>
  );
}
