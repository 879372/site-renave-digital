"""Cadastra o catálogo inicial de produtos (preços de venda ajustáveis no admin)."""

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from consultas.models import Product

C = Product.Category
CATALOG = [
    # sku, nome, descrição, categoria, entrada, preço (centavos), destaque, ordem, itens
    (
        "veicular-lojista-total",
        "Lojista Total",
        "O pacote completo para decidir a compra do veículo.",
        C.COMPLETA,
        "PLACA",
        8990,
        True,
        1,
        ["Dados cadastrais e restrições", "Leilão e sinistro", "Roubo e furto", "Gravame", "FIPE"],
    ),
    (
        "veicular-completa-sf",
        "Veicular Completa",
        "Cadastro, restrições e situação do veículo na base nacional.",
        C.COMPLETA,
        "PLACA",
        4990,
        True,
        2,
        ["Base nacional e estadual", "Restrições administrativas e judiciais", "Débitos informados"],
    ),
    (
        "veicular-leilao-base-3-cf",
        "Leilão",
        "Histórico de passagem por leilão.",
        C.RESTRICOES,
        "PLACA",
        2490,
        True,
        3,
        ["Leilões encontrados", "Lote e condição"],
    ),
    (
        "veicular-indicio-sinistro-sf",
        "Indício de sinistro",
        "Indícios de sinistro com perda parcial ou total.",
        C.RESTRICOES,
        "PLACA",
        1990,
        False,
        4,
        [],
    ),
    (
        "veicular-indicio-roubo-furto-cf",
        "Roubo e furto",
        "Indicador de registro de roubo ou furto.",
        C.RESTRICOES,
        "PLACA",
        1490,
        False,
        5,
        [],
    ),
    ("veicular-gravame-cf", "Gravame", "Alienação fiduciária e financiamentos ativos.", C.RESTRICOES, "PLACA", 1490, False, 6, []),
    ("veicular-renajud-cf", "Renajud", "Restrições judiciais no RENAJUD.", C.RESTRICOES, "PLACA", 1490, False, 7, []),
    ("veicular-renainf-cf", "Renainf (infrações)", "Infrações de trânsito registradas.", C.DEBITOS, "PLACA", 1490, False, 8, []),
    (
        "veicular-historico-km-cf",
        "Histórico de KM",
        "Registros de quilometragem para checar adulteração.",
        C.HISTORICO,
        "PLACA",
        1990,
        False,
        9,
        [],
    ),
    (
        "veicular-historico-proprietario-cf",
        "Histórico de proprietários",
        "Quantidade e histórico de donos.",
        C.HISTORICO,
        "PLACA",
        2490,
        False,
        10,
        [],
    ),
    ("veicular-recall-placa-sf", "Recall", "Recalls pendentes do fabricante.", C.HISTORICO, "PLACA", 790, False, 11, []),
    ("historico-fipe-sf", "FIPE + histórico", "Valor FIPE atual e evolução do preço.", C.PRECO, "PLACA", 590, False, 12, []),
    (
        "veicular-base-nacional-cf",
        "Base nacional",
        "Dados cadastrais do veículo na base nacional.",
        C.CADASTRO,
        "PLACA",
        1290,
        False,
        13,
        [],
    ),
    (
        "veicular-agregados-chassi-sf",
        "Veicular simples por chassi",
        "Dados do veículo a partir do chassi.",
        C.CADASTRO,
        "CHASSI",
        990,
        False,
        14,
        [],
    ),
    ("veicular-dados-renavam-cf", "RENAVAM pela placa", "Número do RENAVAM a partir da placa.", C.CADASTRO, "PLACA", 990, False, 15, []),
    (
        "veicular-comunicado-venda-cf",
        "Comunicado de venda",
        "Verifica se há comunicação de venda registrada.",
        C.CADASTRO,
        "PLACA",
        1290,
        False,
        16,
        [],
    ),
    (
        "empresa-cadastro-basico-cf",
        "Dados cadastrais por CNPJ",
        "Situação cadastral de empresas (vendedor PJ).",
        C.EMPRESA,
        "CNPJ",
        590,
        False,
        17,
        [],
    ),
]


class Command(BaseCommand):
    help = "Cria/atualiza os produtos de consulta padrão (ativos)."

    def handle(self, *args, **options):
        for sku, name, desc, cat, inp, price, featured, order, items in CATALOG:
            Product.objects.update_or_create(
                sku=sku,
                defaults=dict(
                    code=slugify(name),
                    name=name,
                    description=desc,
                    category=cat,
                    input_type=inp,
                    price_cents=price,
                    is_featured=featured,
                    sort_order=order,
                    highlights=items,
                    is_active=True,
                ),
            )
        self.stdout.write(self.style.SUCCESS(f"{len(CATALOG)} produtos cadastrados."))
