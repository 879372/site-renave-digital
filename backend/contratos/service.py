"""Modelos padrão, preenchimento de variáveis e envio para assinatura eletrônica.

O documento é texto puro (o front mostra com quebras de linha e imprime), então não há HTML
a escapar. Variáveis: {{loja.razao_social}}, {{cliente.nome}}, {{veiculo.placa}}, {{venda.valor}} etc.
"""

import re

from django.utils import timezone

from core.documents import only_digits
from core.exceptions import BusinessError

from .models import Documento, Modelo

VAR = re.compile(r"{{\s*([a-z_]+)\.([a-z_]+)\s*}}")


def _money(cents) -> str:
    if cents is None:
        return ""
    s = f"{cents / 100:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _doc(value: str) -> str:
    v = only_digits(value or "")
    if len(v) == 11:
        return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9:]}"
    if len(v) == 14:
        return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}"
    return v


def _plate(p: str) -> str:
    return f"{p[:3]}-{p[3:]}" if p and len(p) == 7 else p or ""


DEFAULTS = {
    Modelo.Kind.COMPRA_VENDA: (
        "Contrato de compra e venda de veículo",
        """CONTRATO PARTICULAR DE COMPRA E VENDA DE VEÍCULO

VENDEDORA: {{loja.razao_social}}, CNPJ {{loja.cnpj}}, com sede em {{loja.endereco}}.

COMPRADOR(A): {{cliente.nome}}, CPF/CNPJ {{cliente.documento}}, residente em {{cliente.endereco}}.

1. OBJETO. A VENDEDORA vende ao COMPRADOR o veículo {{veiculo.descricao}}, placa {{veiculo.placa}}, chassi {{veiculo.chassi}}, RENAVAM {{veiculo.renavam}}, cor {{veiculo.cor}}, com {{veiculo.km}} km.

2. PREÇO E PAGAMENTO. O preço é de {{venda.valor}} ({{venda.valor_extenso}}), pago da seguinte forma:
{{venda.pagamentos}}

3. ENTREGA. O veículo é entregue nesta data, no estado em que se encontra, vistoriado e aceito pelo COMPRADOR.

4. GARANTIA. A VENDEDORA garante motor e câmbio por 90 (noventa) dias a partir da entrega, nos termos do Código de Defesa do Consumidor, excluídos desgaste natural e mau uso.

5. TRANSFERÊNCIA. O COMPRADOR se compromete a transferir o veículo para o seu nome em até 30 (trinta) dias, respondendo por multas e encargos a partir desta data.

6. FORO. Fica eleito o foro da comarca de {{loja.cidade}} para dirimir dúvidas deste contrato.

{{loja.cidade}}, {{data.hoje}}.


_______________________________
{{loja.razao_social}}


_______________________________
{{cliente.nome}}
""",
    ),
    Modelo.Kind.RECIBO: (
        "Recibo de pagamento",
        """RECIBO

Recebemos de {{cliente.nome}}, CPF/CNPJ {{cliente.documento}}, a quantia de {{venda.valor}} ({{venda.valor_extenso}}), referente à compra do veículo {{veiculo.descricao}}, placa {{veiculo.placa}}.

{{loja.cidade}}, {{data.hoje}}.


_______________________________
{{loja.razao_social}} — CNPJ {{loja.cnpj}}
""",
    ),
    Modelo.Kind.GARANTIA: (
        "Termo de garantia",
        """TERMO DE GARANTIA

{{loja.razao_social}}, CNPJ {{loja.cnpj}}, garante ao(à) Sr(a). {{cliente.nome}} o veículo {{veiculo.descricao}}, placa {{veiculo.placa}}, com {{veiculo.km}} km na entrega, pelo prazo de 90 (noventa) dias a partir de {{data.hoje}}.

COBERTURA: motor (partes internas lubrificadas) e câmbio.
NÃO COBRE: desgaste natural (embreagem, freios, pneus, suspensão, bateria), mau uso, falta de manutenção, alterações feitas por terceiros.

Para acionar a garantia, procure a loja antes de qualquer reparo.

{{loja.cidade}}, {{data.hoje}}.


_______________________________
{{loja.razao_social}}


_______________________________
{{cliente.nome}}
""",
    ),
    Modelo.Kind.CONSIGNACAO: (
        "Contrato de consignação",
        """CONTRATO DE CONSIGNAÇÃO DE VEÍCULO

CONSIGNANTE: {{cliente.nome}}, CPF/CNPJ {{cliente.documento}}, residente em {{cliente.endereco}}.
CONSIGNATÁRIA: {{loja.razao_social}}, CNPJ {{loja.cnpj}}.

1. O CONSIGNANTE entrega à CONSIGNATÁRIA, para venda, o veículo {{veiculo.descricao}}, placa {{veiculo.placa}}, RENAVAM {{veiculo.renavam}}, com {{veiculo.km}} km.
2. Preço mínimo de venda: {{veiculo.preco}}. Remuneração da CONSIGNATÁRIA: {{consignacao.condicao}}.
3. Vendido o veículo, a CONSIGNATÁRIA repassa o valor devido ao CONSIGNANTE em até 5 (cinco) dias úteis.
4. Prazo da consignação: até {{consignacao.prazo}}. O CONSIGNANTE pode retirar o veículo a qualquer tempo, ressarcindo despesas autorizadas.
5. Multas e débitos anteriores à entrega são de responsabilidade do CONSIGNANTE.

{{loja.cidade}}, {{data.hoje}}.


_______________________________
{{cliente.nome}}


_______________________________
{{loja.razao_social}}
""",
    ),
    Modelo.Kind.PROCURACAO: (
        "Procuração para transferência",
        """PROCURAÇÃO

OUTORGANTE: {{cliente.nome}}, CPF/CNPJ {{cliente.documento}}, residente em {{cliente.endereco}}.
OUTORGADA: {{loja.razao_social}}, CNPJ {{loja.cnpj}}.

PODERES: representar o OUTORGANTE perante o DETRAN, SENATRAN e demais órgãos de trânsito para tratar da transferência, licenciamento e regularização do veículo {{veiculo.descricao}}, placa {{veiculo.placa}}, chassi {{veiculo.chassi}}, RENAVAM {{veiculo.renavam}}, podendo assinar documentos, pagar taxas e receber documentos.

{{loja.cidade}}, {{data.hoje}}.


_______________________________
{{cliente.nome}}
(firma reconhecida)
""",
    ),
}


def ensure_defaults(organization) -> None:
    existing = set(Modelo.objects.filter(organization=organization).values_list("kind", flat=True))
    Modelo.objects.bulk_create(
        [Modelo(organization=organization, kind=k, title=t, body=b) for k, (t, b) in DEFAULTS.items() if k not in existing]
    )


UNITS = [
    "",
    "um",
    "dois",
    "três",
    "quatro",
    "cinco",
    "seis",
    "sete",
    "oito",
    "nove",
    "dez",
    "onze",
    "doze",
    "treze",
    "quatorze",
    "quinze",
    "dezesseis",
    "dezessete",
    "dezoito",
    "dezenove",
]
TENS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
HUNDREDS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos", "novecentos"]


def _below_1000(n: int) -> str:
    if n == 100:
        return "cem"
    parts = []
    h, rest = divmod(n, 100)
    if h:
        parts.append(HUNDREDS[h])
    if rest < 20:
        if rest:
            parts.append(UNITS[rest])
    else:
        t, u = divmod(rest, 10)
        parts.append(TENS[t] + (f" e {UNITS[u]}" if u else ""))
    return " e ".join(parts)


def extenso(cents: int) -> str:
    """Valor por extenso em reais (até 999 milhões), na forma usada em contratos."""
    reais, cent = divmod(int(cents or 0), 100)
    millions, rest = divmod(reais, 1_000_000)
    thousands, units = divmod(rest, 1000)
    groups = []  # (texto, valor do grupo)
    if millions:
        groups.append((f"{_below_1000(millions)} {'milhão' if millions == 1 else 'milhões'}", millions))
    if thousands:
        groups.append(("mil" if thousands == 1 else f"{_below_1000(thousands)} mil", thousands))
    if units:
        groups.append((_below_1000(units), units))
    text = ""
    for i, (words, value) in enumerate(groups):
        if i == 0:
            text = words
        else:
            # "e" antes do último grupo quando ele é menor que 100 ou uma centena redonda; senão, só espaço.
            text += (" e " if value < 100 or value % 100 == 0 else " ") + words
    if text:
        text += " de reais" if reais % 1_000_000 == 0 else (" real" if reais == 1 else " reais")
    if cent:
        text += (" e " if text else "") + _below_1000(cent) + (" centavo" if cent == 1 else " centavos")
    return text or "zero reais"


def build_context(organization, *, venda=None, vehicle=None, pessoa=None) -> dict:
    vehicle = vehicle or (venda.vehicle if venda else None)
    pessoa = pessoa or (venda.cliente if venda else None) or (vehicle.consignor if vehicle and vehicle.consignor_id else None)
    org = organization
    org_addr = ", ".join(p for p in [f"{org.street}, {org.number}".strip(", "), org.district, f"{org.city}/{org.uf}"] if p)
    ctx = {
        "loja": {
            "razao_social": org.legal_name,
            "nome": org.trade_name or org.legal_name,
            "cnpj": _doc(org.cnpj),
            "endereco": org_addr,
            "cidade": org.city,
            "telefone": org.phone,
        },
        "data": {"hoje": timezone.localdate().strftime("%d/%m/%Y")},
        "cliente": {},
        "veiculo": {},
        "venda": {},
        "consignacao": {},
    }
    if pessoa:
        ctx["cliente"] = {
            "nome": pessoa.nome,
            "documento": _doc(pessoa.documento),
            "endereco": pessoa.endereco_completo,
            "telefone": pessoa.telefone,
            "email": pessoa.email,
            "rg": pessoa.rg_ie,
        }
    if vehicle:
        ctx["veiculo"] = {
            "descricao": vehicle.title,
            "marca": vehicle.marca,
            "modelo": vehicle.modelo,
            "placa": _plate(vehicle.placa),
            "chassi": vehicle.chassi,
            "renavam": vehicle.renavam,
            "cor": vehicle.cor,
            "km": f"{vehicle.km:,}".replace(",", ".") if vehicle.km is not None else "",
            "ano": f"{vehicle.ano_fabricacao or ''}/{vehicle.ano_modelo or ''}",
            "preco": _money(vehicle.price_cents),
        }
        if vehicle.ownership == "consignado":
            cond = (
                f"valor líquido garantido de {_money(vehicle.consignment_value)} ao consignante"
                if vehicle.consignment_mode == "liquido"
                else f"comissão de {vehicle.consignment_value / 100:.2f}% sobre o valor de venda".replace(".", ",")
            )
            ctx["consignacao"] = {
                "condicao": cond,
                "prazo": vehicle.consignment_until.strftime("%d/%m/%Y") if vehicle.consignment_until else "prazo indeterminado",
            }
    if venda:
        pays = "\n".join(
            f"- {p.get_method_display()}: {_money(p.amount_cents)}"
            + (f" em {p.installments}x" if p.installments > 1 else "")
            + (f" ({p.bank})" if p.bank else "")
            for p in venda.pagamentos.all()
        )
        ctx["venda"] = {
            "valor": _money(venda.price_cents),
            "valor_extenso": extenso(venda.price_cents),
            "pagamentos": pays or "- à vista",
            "data": (venda.closed_at or timezone.localdate()).strftime("%d/%m/%Y"),
            "vendedor": venda.seller.full_name if venda.seller_id else "",
        }
    return ctx


def render(body: str, ctx: dict) -> str:
    def sub(m):
        value = ctx.get(m.group(1), {}).get(m.group(2))
        return str(value) if value not in (None, "") else "________"

    return VAR.sub(sub, body)


def generate(modelo: Modelo, *, user=None, venda=None, vehicle=None, pessoa=None) -> Documento:
    ctx = build_context(modelo.organization, venda=venda, vehicle=vehicle, pessoa=pessoa)
    vehicle = vehicle or (venda.vehicle if venda else None)
    pessoa = pessoa or (venda.cliente if venda else None)
    title = modelo.title + (f" — {vehicle.title}" if vehicle else "")
    return Documento.objects.create(
        organization=modelo.organization,
        modelo=modelo,
        kind=modelo.kind,
        title=title[:160],
        content=render(modelo.body, ctx),
        vehicle=vehicle,
        venda=venda,
        pessoa=pessoa,
        created_by=user,
    )


def send_for_signature(doc: Documento, signers: list[dict]) -> Documento:
    from integrations.zapsign import ZapSignClient

    client = ZapSignClient(doc.organization)
    if not client.configured:
        raise BusinessError("Assinatura eletrônica não configurada. Imprima o documento para assinar.", code="signature_off")
    if doc.signature_status in (Documento.Signature.PENDING, Documento.Signature.SIGNED):
        raise BusinessError("Este documento já foi enviado para assinatura.")
    if not signers:
        raise BusinessError("Informe quem assina.")
    data = client.create_document(name=doc.title, text=doc.content, signers=signers, external_id=str(doc.public_id))
    doc.signature_status = Documento.Signature.PENDING
    doc.signature_provider_id = data.get("token", "")
    doc.signature_links = [{"name": s.get("name"), "email": s.get("email"), "url": s.get("sign_url")} for s in data.get("signers", [])]
    doc.save(update_fields=["signature_status", "signature_provider_id", "signature_links", "updated_at"])
    return doc
