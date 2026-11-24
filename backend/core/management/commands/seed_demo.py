"""Loja demonstrativa isolada; sem gateways, mensagens ou documentos fiscais reais."""

import secrets
from datetime import timedelta
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from accounts.models import User
from audit.service import record
from billing.models import Plan, Subscription
from contratos import service as contracts
from contratos.models import Modelo
from crm.models import Interacao, Lead, Tarefa
from estoque import service as stock
from estoque.models import Avaliacao, Vehicle, VehiclePhoto
from financeiro import service as finance
from financeiro.models import Conta
from financiamento.models import Ficha, Proposta
from organizations.models import Membership, Organization, Role
from pessoas.models import Pessoa
from posvenda.models import Ocorrencia
from vendas import service as sales
from vendas.models import Meta, RegraComissao, Venda
from vitrine.models import Anuncio, Site

DEMO_CNPJ = "00000000000000"  # deliberadamente inválido: não representa empresa real
DEMO_NAME = "Revenda Exemplo — Demonstração"


class Command(BaseCommand):
    help = "Cria uma loja fictícia completa e vincula a uma conta existente, sem mudar sua senha."

    def add_arguments(self, parser):
        parser.add_argument("--owner-email", required=True)
        parser.add_argument("--no-images", action="store_true", help="Não grava ilustrações no storage.")

    @transaction.atomic
    def handle(self, *args, **options):
        owner = User.objects.filter(email__iexact=options["owner_email"], is_active=True).first()
        if not owner:
            raise CommandError("A conta proprietária precisa existir e estar ativa.")
        existing = Organization.objects.filter(cnpj=DEMO_CNPJ).first()
        if existing:
            if existing.legal_name != DEMO_NAME:
                raise CommandError("Identificador ocupado por outra empresa; nada foi alterado.")
            Membership.objects.get_or_create(user=owner, organization=existing, defaults={"role": Role.OWNER})
            site = Site.objects.filter(organization=existing).first()
            if site and not site.feed_token:
                site.feed_token = secrets.token_urlsafe(24)
                site.save(update_fields=["feed_token"])
            self.stdout.write(f"Demonstração já existente: {existing.public_id}. Nenhum dado duplicado.")
            return
        premium = Plan.objects.get(code="premium")
        org = Organization.objects.create(
            cnpj=DEMO_CNPJ,
            legal_name=DEMO_NAME,
            trade_name=DEMO_NAME,
            email="loja@example.invalid",
            city="Natal",
            uf="RN",
            street="Avenida Demonstração",
            number="100",
            district="Centro",
            city_ibge="2408102",
            zip_code="59000000",
        )
        Membership.objects.create(user=owner, organization=org, role=Role.OWNER)
        # Cortesia local: sem renovação agendada, gateway ou crédito para integrações pagas.
        Subscription.objects.create(organization=org, plan=premium, status="active", next_billing_date=None)
        today = timezone.localdate()
        sellers = []
        for i, name in enumerate(["Ana Costa", "Bruno Lima", "Camila Alves"]):
            seller, created = User.objects.get_or_create(
                email=f"vendedor{i + 1}.revenda-demo@example.invalid", defaults={"full_name": f"{name} (Demo)", "email_verified": True}
            )
            if not created:
                raise CommandError("Usuário demonstrativo já existe fora desta loja; operação revertida.")
            seller.set_unusable_password()
            seller.save()
            Membership.objects.create(user=seller, organization=org, role=Role.SELLER)
            Meta.objects.create(organization=org, seller=seller, month=today.replace(day=1), units=4, revenue_cents=40000000)
            sellers.append(seller)
        finance.ensure_setup(org)
        bank = Conta.objects.create(organization=org, name="Banco demonstrativo", bank="Banco fictício", opening_balance_cents=25000000)
        Conta.objects.create(organization=org, name="Recebíveis de cartão (Demo)", kind="cartao")
        people = []
        for i, name in enumerate(
            [
                "Lucas Martins",
                "Mariana Souza",
                "Pedro Oliveira",
                "Juliana Rocha",
                "Rafael Santos",
                "Beatriz Lima",
                "Felipe Gomes",
                "Carolina Ribeiro",
                "Oficina Exemplo",
                "Estética Exemplo",
            ]
        ):
            people.append(
                Pessoa.objects.create(
                    organization=org,
                    nome=f"{name} (Demo)",
                    email=f"pessoa{i + 1}@example.invalid",
                    cidade="Natal",
                    uf="RN",
                    logradouro="Rua Exemplo",
                    numero=str(i + 10),
                    is_cliente=i < 8,
                    is_fornecedor=i >= 8,
                    observacoes="DADOS FICTÍCIOS — demonstração, sem contato real.",
                )
            )
        RegraComissao.objects.create(organization=org, mode="sobra", value=1000, min_cents=30000)
        catalog = [
            ("Chevrolet", "Onix", "LT 1.0", 2022, 6890000, "Branco"),
            ("Hyundai", "HB20", "Comfort 1.0", 2023, 7490000, "Prata"),
            ("Volkswagen", "Polo", "TSI automático", 2024, 9690000, "Cinza"),
            ("Fiat", "Argo", "Drive 1.0", 2022, 6590000, "Vermelho"),
            ("Toyota", "Corolla", "XEi 2.0", 2022, 13990000, "Preto"),
            ("Jeep", "Renegade", "Longitude", 2021, 10590000, "Branco"),
            ("Honda", "Civic", "EXL 2.0", 2020, 12490000, "Prata"),
            ("Nissan", "Kicks", "SV CVT", 2022, 9990000, "Azul"),
            ("Fiat", "Strada", "Freedom", 2023, 10990000, "Branco"),
            ("Volkswagen", "T-Cross", "Comfortline", 2023, 12990000, "Cinza"),
            ("Renault", "Kwid", "Zen", 2023, 5290000, "Branco"),
            ("Chevrolet", "Tracker", "Premier", 2022, 11990000, "Azul"),
            ("Toyota", "Hilux", "SRV diesel", 2021, 23990000, "Prata"),
            ("Peugeot", "208", "Allure", 2023, 7790000, "Vermelho"),
            ("Honda", "HR-V", "EX CVT", 2021, 11490000, "Cinza"),
            ("Fiat", "Mobi", "Like", 2022, 4790000, "Branco"),
        ]
        vehicles = []
        for i, (brand, model, version, year, price, color) in enumerate(catalog):
            v = Vehicle.objects.create(
                organization=org,
                placa=f"DEM{i:04d}",
                marca=brand,
                modelo=model,
                versao=version,
                ano_fabricacao=year,
                ano_modelo=year,
                cor=color,
                combustivel="Diesel" if model == "Hilux" else "Flex",
                cambio="Automático" if i % 3 else "Manual",
                km=18000 + i * 3600,
                portas=4,
                status="preparacao" if i in [10, 11] else "disponivel",
                purchase_price_cents=price - 1100000,
                price_cents=price,
                min_price_cents=price - 200000,
                supplier=people[6],
                entry_date=today - timedelta(days=12 + i * 4),
                purchase_date=today - timedelta(days=12 + i * 4),
                published=i not in [10, 11],
                featured=i < 3,
                location="Pátio principal (Demo)",
                keys="Principal e reserva",
                opcionais=["Ar-condicionado", "Direção elétrica", "Vidros elétricos", "Central multimídia"],
                descricao="VEÍCULO FICTÍCIO DE DEMONSTRAÇÃO. Valores ilustrativos; não disponível para compra.",
            )
            if i in [5, 6]:
                v.ownership = "consignado"
                v.consignor = people[7]
                v.consignment_mode = "comissao"
                v.consignment_value = 800
                v.consignment_until = today + timedelta(days=45)
                v.purchase_price_cents = 0
                v.save()
            else:
                finance.create(
                    org,
                    kind="pagar",
                    origin="compra",
                    description=f"Compra simulada — {v.title}",
                    amount_cents=v.purchase_price_cents,
                    due_date=v.purchase_date,
                    paid=i < 12,
                    category_code="compra_veiculo",
                    vehicle=v,
                    pessoa=people[6],
                    conta=bank,
                )
            stock.add_cost(
                v,
                category="mecanica",
                description="Revisão preventiva (Demo)",
                amount_cents=120000 + i * 1500,
                date=today - timedelta(days=9),
                supplier=people[8],
                paid=i % 2 == 0,
                user=owner,
            )
            stock.add_cost(
                v,
                category="estetica",
                description="Higienização (Demo)",
                amount_cents=25000,
                date=today - timedelta(days=7),
                supplier=people[9],
                paid=True,
                user=owner,
            )
            if not options["no_images"]:
                self.illustration(org, v, i, color)
            vehicles.append(v)
        leads = []
        for i in range(18):
            stage = ["novo", "contato", "visita", "proposta", "ganho", "perdido"][i % 6]
            lead = Lead.objects.create(
                organization=org,
                name=f"{people[i % 8].nome} — atendimento {i + 1}",
                email=f"lead{i + 1}@example.invalid",
                source=["site", "whatsapp", "instagram", "olx", "indicacao", "loja"][i % 6],
                stage=stage,
                vehicle=vehicles[i % 16],
                interest=vehicles[i % 16].title,
                budget_cents=vehicles[i % 16].price_cents,
                owner=sellers[i % 3],
                pessoa=people[i % 8],
                position=i,
                message="Atendimento fictício para apresentar o funil.",
                lost_reason="Adiou a compra (simulação)" if stage == "perdido" else "",
            )
            Interacao.objects.create(
                lead=lead, user=sellers[i % 3], kind="nota", text="Cliente demonstrativo: prefere visita no fim de semana."
            )
            Tarefa.objects.create(
                organization=org,
                lead=lead,
                owner=sellers[i % 3],
                title=f"Retorno demonstrativo — {vehicles[i % 16].modelo}",
                due_at=timezone.now() + timedelta(days=i % 5 - 2),
                done_at=timezone.now() if i % 4 == 0 else None,
            )
            leads.append(lead)
        closed = []
        for i in [0, 1, 2, 5, 7, 8]:
            v = vehicles[i]
            sale = Venda.objects.create(
                organization=org,
                vehicle=v,
                cliente=people[i % 8],
                seller=sellers[i % 3],
                lead=leads[i],
                price_cents=v.price_cents - 100000,
                notes="Venda fictícia de demonstração; sem RENAVE ou NF-e.",
            )
            sales.set_payments(
                sale,
                [
                    {"method": "pix", "amount_cents": 2000000},
                    {
                        "method": "financiamento" if i % 2 else "boleto",
                        "amount_cents": sale.price_cents - 2000000,
                        "installments": 1 if i % 2 else 3,
                        "first_due": today + timedelta(days=i - 4),
                        "bank": "Banco demonstrativo",
                    },
                ],
            )
            sale = sales.close(sale, user=owner, closed_at=today - timedelta(days=i + 1))
            closed.append(sale)
        sales.pay_commissions(org, today.replace(day=1), today, user=owner)
        for i in [3, 4, 6]:
            sale = Venda.objects.create(
                organization=org,
                vehicle=vehicles[i],
                cliente=people[i],
                seller=sellers[i % 3],
                price_cents=vehicles[i].price_cents,
                notes="Negociação demonstrativa em andamento.",
            )
            if i == 3:
                sales.reserve(sale, amount_cents=100000, until=today + timedelta(days=3), user=owner)
        for i in range(4):
            Avaliacao.objects.create(
                organization=org,
                cliente=people[i],
                evaluator=sellers[i % 3],
                marca="Volkswagen",
                modelo=["Gol", "Fox", "Virtus", "Voyage"][i],
                ano_fabricacao=2019 + i,
                ano_modelo=2019 + i,
                placa=f"AVA{i:04d}",
                km=65000 + i * 9000,
                status=["aberta", "aprovada", "recusada", "aberta"][i],
                offer_cents=4200000 + i * 500000,
                fipe_price_cents=4800000 + i * 500000,
                estimated_repairs_cents=180000,
                checklist={"motor": "ok", "cambio": "ok", "pneus": "atencao", "pintura": "ok"},
                notes="Avaliação ilustrativa. FIPE informada manualmente, sem consulta externa.",
            )
        for i, status in enumerate(["analise", "aprovada", "recusada"]):
            ficha = Ficha.objects.create(
                organization=org,
                cliente=people[i + 3],
                vehicle=vehicles[i + 3],
                occupation="clt",
                employer="Empresa fictícia",
                job_title="Analista (Demo)",
                monthly_income_cents=850000,
                vehicle_price_cents=vehicles[i + 3].price_cents,
                down_payment_cents=2500000,
                term_months=48,
                notes="Simulação de apresentação; não enviada a instituição financeira.",
            )
            Proposta.objects.create(
                organization=org,
                ficha=ficha,
                bank="Banco demonstrativo",
                status=status,
                financed_cents=ficha.financed_cents,
                term_months=48,
                monthly_rate_bp=149,
                installment_cents=ficha.financed_cents // 36,
                notes="Resultado fictício. Nenhuma análise bancária realizada.",
            )
        for sale in closed[:2]:
            entry = finance.create(
                org,
                kind="pagar",
                origin="garantia",
                description="Reparo em garantia (Demo)",
                amount_cents=85000,
                due_date=today + timedelta(days=4),
                category_code="garantia",
                vehicle=sale.vehicle,
                venda=sale,
            )[0]
            Ocorrencia.objects.create(
                organization=org,
                garantia=sale.garantia,
                description="Ruído na suspensão (simulação)",
                status="andamento",
                cost_cents=85000,
                lancamento=entry,
                resolution="Aguardando peça na oficina demonstrativa.",
            )
        for month in range(3):
            for code, amount in [("aluguel", 450000), ("pessoal", 1200000), ("marketing", 180000), ("impostos", 95000)]:
                finance.create(
                    org,
                    kind="pagar",
                    description=f"{code.title()} — demonstração",
                    amount_cents=amount,
                    due_date=today + timedelta(days=month * 30 - 15),
                    category_code=code,
                    paid=month == 0,
                    conta=bank,
                )
        contracts.ensure_defaults(org)
        for sale in closed[:3]:
            for kind in ["compra_venda", "garantia", "recibo"]:
                doc = contracts.generate(Modelo.objects.get(organization=org, kind=kind), user=owner, venda=sale)
                doc.content = "DOCUMENTO FICTÍCIO — SEM VALIDADE JURÍDICA\n\n" + doc.content
                doc.save(update_fields=["content"])
        # Rota por caminho funciona sem exigir DNS wildcard para cada loja.
        Site.objects.create(
            organization=org,
            slug="revenda-demonstracao",
            feed_token=secrets.token_urlsafe(24),
            title=DEMO_NAME,
            is_published=True,
            about="Loja fictícia para demonstrar a plataforma. Veículos e valores ilustrativos, sem oferta comercial.",
            email="loja@example.invalid",
            address="Natal/RN — endereço fictício",
            accent_color="#047857",
        )
        for v in vehicles[4:7]:
            Anuncio.objects.create(organization=org, vehicle=v, portal="olx", status="pausado", message="Exemplo; não enviado ao portal.")
        branch = Organization.objects.create(
            cnpj="00000000000001",
            legal_name="Filial Exemplo — Demonstração",
            trade_name="Filial Exemplo — Demonstração",
            parent=org,
            city="Parnamirim",
            uf="RN",
            email="filial@example.invalid",
        )
        Membership.objects.create(user=owner, organization=branch, role=Role.OWNER)
        for i, source in enumerate(vehicles[12:15]):
            Vehicle.objects.create(
                organization=branch,
                placa=f"FIL{i:04d}",
                marca=source.marca,
                modelo=source.modelo,
                ano_fabricacao=source.ano_fabricacao,
                ano_modelo=source.ano_modelo,
                price_cents=source.price_cents,
                purchase_price_cents=source.purchase_price_cents,
                status="disponivel",
                entry_date=today - timedelta(days=10),
                location="Pátio da filial (Demo)",
                descricao="DADOS FICTÍCIOS — demonstração de multi-loja.",
            )
        finance.ensure_setup(branch)
        record("demo.criada", actor=owner, organization=org, target=org)
        self.stdout.write(
            self.style.SUCCESS(f"Demonstração criada: {org.public_id}; {len(vehicles)} veículos, {len(closed)} vendas fechadas, 18 leads.")
        )

    def illustration(self, org, vehicle, index, color):
        image = Image.new("RGB", (1000, 650), "#182220")
        draw = ImageDraw.Draw(image)
        colors = {"Branco": "#e4e7e7", "Prata": "#aab5bf", "Cinza": "#737e89", "Vermelho": "#bd4149", "Preto": "#41464d", "Azul": "#4976a8"}
        draw.ellipse((100, 400, 900, 550), fill="#101715")
        draw.polygon([(150, 420), (200, 310), (340, 285), (430, 205), (640, 205), (755, 300), (855, 330), (890, 420)], fill=colors[color])
        draw.polygon([(365, 287), (445, 223), (627, 223), (704, 287)], fill="#243e43")
        for x in [310, 745]:
            draw.ellipse((x - 63, 370, x + 63, 496), fill="#111718")
            draw.ellipse((x - 33, 400, x + 33, 466), fill="#a6b3b3")
        draw.text((35, 35), "REVENDA DIGITAL | DEMONSTRACAO", fill="#6ee7b7")
        draw.text((35, 565), f"{vehicle.marca} {vehicle.modelo} {vehicle.ano_modelo} | IMAGEM ILUSTRATIVA", fill="#e4eeee")
        buf = BytesIO()
        image.save(buf, format="PNG")
        photo = VehiclePhoto(organization=org, vehicle=vehicle, position=0)
        photo.image.save(f"demo-{index}.png", ContentFile(buf.getvalue()), save=True)
