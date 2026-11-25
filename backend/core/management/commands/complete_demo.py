"""Complementa exclusivamente matriz/filial fictícias, sem chamar provedores."""

import secrets
from datetime import datetime, time, timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from audit.service import record
from billing.models import Invoice, InvoiceItem
from billing.service import add_months
from comunicacao.models import ComunicacaoVenda
from consultas.models import Consulta, Product
from contratos import service as contracts
from contratos.models import Documento, Modelo
from crm.models import Interacao, Lead, Tarefa
from estoque import service as stock
from estoque.models import Avaliacao, AvaliacaoFoto, Vehicle, VehicleDocument
from financeiro import service as finance
from financeiro.models import Conta, Lancamento
from financiamento.models import Ficha, Proposta
from fiscal.models import FiscalSettings, NotaFiscal
from organizations.models import ClientCompany, Membership, Organization, Role
from pessoas.models import Pessoa
from posvenda.models import Ocorrencia
from renave.models import RenaveOperation, StockVehicle
from vault.crypto import encrypt_bytes
from vault.models import Certificate
from vendas import service as sales
from vendas.models import Meta, RegraComissao, Venda
from vitrine.models import Anuncio, Site
from wallet import service as wallet
from wallet.models import TopUp

from .seed_demo import Command as SeedCommand

MARK = "DEMO COMPLETA — "
IDS = ("00000000000000", "00000000000001")


class Command(BaseCommand):
    help = "Preenche os módulos das duas lojas de demonstração sem duplicar ou apagar cadastros."

    def add_arguments(self, parser):
        parser.add_argument("--owner-email", required=True)
        parser.add_argument("--no-images", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        owner = User.objects.filter(email__iexact=options["owner_email"], is_active=True).first()
        orgs = list(Organization.objects.select_for_update().filter(cnpj__in=IDS).order_by("pk"))
        if not owner or len(orgs) != 2 or any("Demonstração" not in o.legal_name for o in orgs):
            raise CommandError("É preciso ter a matriz e a filial demonstrativas e uma conta proprietária ativa.")
        if any(not Membership.objects.filter(user=owner, organization=o, role="owner", is_active=True).exists() for o in orgs):
            raise CommandError("A conta deve ser proprietária das duas lojas demonstrativas.")
        for org in orgs:
            self.populate(org, owner, options["no_images"])
            self.stdout.write(
                str(
                    {
                        "loja": str(org),
                        "veiculos": org.vehicles.count(),
                        "vendas": org.vendas.count(),
                        "clientes": org.pessoas.count(),
                        "leads": org.leads.count(),
                        "financeiro": org.lancamentos.count(),
                        "contratos": org.documentos.count(),
                        "avaliacoes": org.avaliacoes.count(),
                        "garantias": org.garantias.count(),
                        "ocorrencias": org.ocorrencias.count(),
                        "fichas": org.fichas.count(),
                    }
                )
            )

    def populate(self, org, owner, no_images):
        today = timezone.localdate()
        suffix = "f" if org.parent_id else "m"
        for field, value in {
            "street": "Avenida Exemplo",
            "number": "100",
            "district": "Centro",
            "city": "Natal",
            "uf": "RN",
            "city_ibge": "2408102",
            "zip_code": "59000000",
            "tax_regime": "1",
            "state_registration": "ISENTO",
        }.items():
            if not getattr(org, field):
                setattr(org, field, value)
        org.save()
        for i in range(2):
            ClientCompany.objects.get_or_create(
                organization=org,
                document=f"0000000000000{i + 2}",
                defaults={"name": MARK + f"Cliente empresa {i + 1}", "email": f"empresa-{i}@example.invalid"},
            )
        if not Certificate.objects.filter(organization=org, subject="DEMONSTRAÇÃO LOCAL — SEM CERTIFICADO A1").exists():
            cert = Certificate(
                organization=org,
                holder_document=org.cnpj,
                holder_name="DEMO — SEM VALIDADE",
                subject="DEMONSTRAÇÃO LOCAL — SEM CERTIFICADO A1",
                serial="DEMO",
                fingerprint="DEMO",
                not_before=timezone.now() - timedelta(days=366),
                not_after=timezone.now() - timedelta(days=1),
                is_active=False,
                uploaded_by=owner,
                carven_sync_error="Exemplo inativo. Não contém certificado digital nem foi sincronizado.",
            )
            cert.pfx_encrypted = encrypt_bytes(b"EXEMPLO LOCAL: NAO E UM CERTIFICADO DIGITAL", cert.aad)
            cert.password_encrypted = encrypt_bytes(b"", cert.aad)
            cert.save()
        finance.ensure_setup(org)
        bank, _ = Conta.objects.get_or_create(
            organization=org, name=MARK + "Banco", defaults={"bank": "Banco fictício", "opening_balance_cents": 150000000}
        )
        Conta.objects.get_or_create(organization=org, name=MARK + "Cartão", defaults={"kind": "cartao"})
        sellers = []
        for i, name in enumerate(["Ana", "Bruno", "Camila"]):
            seller, created = User.objects.get_or_create(
                email=f"equipe-{suffix}-{i}@example.invalid",
                defaults={"full_name": f"{name} — Demo {suffix.upper()}", "email_verified": True},
            )
            if created:
                seller.set_unusable_password()
                seller.save()
            Membership.objects.get_or_create(user=seller, organization=org, defaults={"role": Role.SELLER})
            for month in range(3):
                Meta.objects.get_or_create(
                    organization=org,
                    seller=seller,
                    month=add_months(today.replace(day=1), -month),
                    defaults={"units": 5, "revenue_cents": 50000000},
                )
            sellers.append(seller)
        RegraComissao.objects.get_or_create(organization=org, defaults={"mode": "sobra", "value": 1000, "min_cents": 30000})
        people = []
        for i, name in enumerate(
            [
                "Cliente Alice",
                "Cliente Bernardo",
                "Cliente Clara",
                "Cliente Daniel",
                "Cliente Elisa",
                "Cliente Felipe",
                "Cliente Gabriela",
                "Cliente Henrique",
                "Fornecedor Oficina",
                "Fornecedor Estética",
            ]
        ):
            person, _ = Pessoa.objects.get_or_create(
                organization=org,
                nome=MARK + name,
                defaults={
                    "email": f"contato-{suffix}-{i}@example.invalid",
                    "cidade": "Natal",
                    "uf": "RN",
                    "logradouro": "Rua Fictícia",
                    "numero": str(i + 10),
                    "bairro": "Centro",
                    "cep": "59000000",
                    "is_cliente": i < 8,
                    "is_fornecedor": i >= 8,
                    "observacoes": "Fictício; não contactar. CPF e telefone omitidos para não representar terceiros reais.",
                },
            )
            people.append(person)
        catalog = [
            ("Fiat", "Cronos", 2023, 7900000),
            ("Chevrolet", "Spin", 2022, 9500000),
            ("Hyundai", "Creta", 2023, 12500000),
            ("Volkswagen", "Nivus", 2022, 11600000),
            ("Honda", "City", 2023, 10900000),
            ("Renault", "Duster", 2021, 8800000),
            ("Nissan", "Versa", 2022, 9200000),
            ("Toyota", "Yaris", 2023, 9900000),
            ("Fiat", "Pulse", 2023, 10800000),
            ("Peugeot", "2008", 2022, 9800000),
            ("Chevrolet", "Montana", 2024, 12800000),
            ("Volkswagen", "Saveiro", 2023, 10200000),
        ]
        vehicles = []
        closed = []
        for i, (brand, model, year, price) in enumerate(catalog):
            plate = f"DX{suffix.upper()}{i:04d}"
            day = today - timedelta(days=[7, 12, 18, 48, 70, 95, 15, 20, 3, 8, 10, 30][i])
            vehicle, created = Vehicle.objects.get_or_create(
                organization=org,
                placa=plate,
                defaults={
                    "marca": brand,
                    "modelo": model,
                    "versao": "Versão ilustrativa",
                    "ano_fabricacao": year,
                    "ano_modelo": year,
                    "cor": "Branco",
                    "cambio": "Automático",
                    "combustivel": "Flex",
                    "km": 22000 + i * 3800,
                    "portas": 4,
                    "opcionais": ["Ar-condicionado", "Direção elétrica", "Multimídia"],
                    "status": "preparacao" if i == 9 else "disponivel",
                    "ownership": "consignado" if i in (4, 8) else "proprio",
                    "consignor": people[7] if i in (4, 8) else None,
                    "consignment_mode": "comissao" if i in (4, 8) else "",
                    "consignment_value": 800 if i in (4, 8) else 0,
                    "consignment_until": today + timedelta(days=40) if i in (4, 8) else None,
                    "supplier": people[6],
                    "purchase_price_cents": 0 if i in (4, 8) else price - 1400000,
                    "price_cents": price,
                    "min_price_cents": price - 200000,
                    "entry_date": day - timedelta(days=15),
                    "purchase_date": day - timedelta(days=15),
                    "location": "Pátio demonstrativo",
                    "keys": "Principal e reserva",
                    "published": i != 9,
                    "featured": i in (7, 8),
                    "descricao": "DADOS FICTÍCIOS. Veículo indisponível para compra real.",
                },
            )
            if created:
                if vehicle.ownership == "proprio":
                    finance.create(
                        org,
                        kind="pagar",
                        origin="compra",
                        description=MARK + f"Compra {plate}",
                        amount_cents=vehicle.purchase_price_cents,
                        due_date=vehicle.purchase_date,
                        category_code="compra_veiculo",
                        paid=i < 6,
                        conta=bank,
                        vehicle=vehicle,
                        pessoa=people[6],
                    )
                stock.add_cost(
                    vehicle,
                    category="mecanica",
                    description=MARK + "Revisão",
                    amount_cents=150000,
                    date=day - timedelta(days=5),
                    supplier=people[8],
                    paid=i % 2 == 0,
                    user=owner,
                )
                stock.add_cost(
                    vehicle,
                    category="estetica",
                    description=MARK + "Higienização",
                    amount_cents=30000,
                    date=day - timedelta(days=4),
                    supplier=people[9],
                    paid=True,
                    user=owner,
                )
            if not no_images and not vehicle.photos.exists():
                SeedCommand().illustration(org, vehicle, i, "Branco")
            if not vehicle.documents.filter(name=MARK + "Checklist de vistoria").exists():
                doc = VehicleDocument(organization=org, vehicle=vehicle, kind="outro", name=MARK + "Checklist de vistoria")
                doc.file.save(
                    "checklist-demonstrativo.txt",
                    ContentFile(
                        f"DEMONSTRAÇÃO SEM VALIDADE DOCUMENTAL\n{vehicle.title}\nMotor: OK\nPneus: revisar\nNenhuma consulta oficial realizada.".encode()
                    ),
                    save=True,
                )
            if i < 6:
                sale, sale_created = Venda.objects.get_or_create(
                    organization=org,
                    vehicle=vehicle,
                    notes=MARK + "Venda fechada",
                    defaults={"cliente": people[i], "seller": sellers[i % 3], "price_cents": price - 100000},
                )
                if sale_created:
                    sales.set_payments(
                        sale,
                        [
                            {"method": "pix", "amount_cents": 2000000},
                            {
                                "method": "financiamento" if i % 2 else "boleto",
                                "amount_cents": sale.price_cents - 2000000,
                                "installments": 1 if i % 2 else 3,
                                "bank": "Banco fictício",
                                "first_due": day + timedelta(days=30),
                            },
                        ],
                    )
                    sale = sales.close(sale, user=owner, closed_at=day)
                    Venda.objects.filter(pk=sale.pk).update(
                        created_at=timezone.make_aware(datetime.combine(day - timedelta(days=2), time(10)))
                    )
                closed.append(sale)
            elif i in (6, 7, 10):
                sale, sale_created = Venda.objects.get_or_create(
                    organization=org,
                    vehicle=vehicle,
                    notes=MARK + "Negociação",
                    defaults={"cliente": people[i % 8], "seller": sellers[i % 3], "price_cents": price - 50000},
                )
                if sale_created and i == 6:
                    sales.reserve(sale, amount_cents=150000, until=today + timedelta(days=4), user=owner)
                elif sale_created and i == 10:
                    sales.cancel(sale, reason="Cliente fictício adiou a compra", user=owner)
            vehicles.append(vehicle)
        # As capas também faltavam nos três veículos originalmente criados na filial.
        if not no_images:
            for i, v in enumerate(org.vehicles.filter(photos__isnull=True).distinct()):
                SeedCommand().illustration(org, v, i, "Branco")
        for i, status in enumerate(["aberta", "aprovada", "recusada", "comprada"]):
            av, _ = Avaliacao.objects.get_or_create(
                organization=org,
                placa=f"AX{suffix.upper()}{i:04d}",
                defaults={
                    "cliente": people[i],
                    "evaluator": sellers[i % 3],
                    "marca": "Fiat",
                    "modelo": "Palio",
                    "ano_fabricacao": 2017,
                    "ano_modelo": 2018,
                    "km": 85000,
                    "cor": "Prata",
                    "status": status,
                    "vehicle": vehicles[11] if status == "comprada" else None,
                    "offer_cents": 3500000,
                    "fipe_price_cents": 4000000,
                    "estimated_repairs_cents": 150000,
                    "checklist": {"motor": "ok", "cambio": "ok", "pneus": "atencao", "lataria": "ok"},
                    "notes": MARK + "Avaliação sem consulta externa",
                },
            )
            if not no_images and not av.photos.exists():
                photo = vehicles[0].photos.first()
                with photo.image.open("rb") as image:
                    avphoto = AvaliacaoFoto(organization=org, avaliacao=av, label="Ilustração demonstrativa")
                    avphoto.image.save("avaliacao-demo.png", ContentFile(image.read()), save=True)
        for i in range(12):
            lead, _ = Lead.objects.get_or_create(
                organization=org,
                name=MARK + f"Atendimento {i + 1}",
                defaults={
                    "source": ["site", "whatsapp", "instagram", "olx", "indicacao", "loja"][i % 6],
                    "stage": ["novo", "contato", "visita", "proposta", "ganho", "perdido"][i % 6],
                    "vehicle": vehicles[i],
                    "pessoa": people[i % 8],
                    "owner": sellers[i % 3],
                    "interest": vehicles[i].title,
                    "budget_cents": vehicles[i].price_cents,
                    "message": "Atendimento fictício para testes.",
                    "lost_reason": "Cliente demonstrativo adiou a compra" if i % 6 == 5 else "",
                    "position": i,
                },
            )
            Interacao.objects.get_or_create(lead=lead, kind="nota", text=MARK + "Preferência registrada", defaults={"user": sellers[i % 3]})
            Tarefa.objects.get_or_create(
                organization=org,
                title=MARK + f"Retorno {i + 1}",
                defaults={
                    "lead": lead,
                    "owner": sellers[i % 3],
                    "due_at": timezone.now() + timedelta(days=i % 5 - 2),
                    "done_at": timezone.now() if i % 4 == 0 else None,
                },
            )
        for i, status in enumerate(["analise", "aprovada", "recusada", "paga"]):
            ficha, _ = Ficha.objects.get_or_create(
                organization=org,
                notes=MARK + f"Ficha {i + 1}",
                defaults={
                    "cliente": people[i],
                    "vehicle": vehicles[i + 6],
                    "occupation": "clt",
                    "employer": "Empresa fictícia",
                    "job_title": "Analista de demonstração",
                    "mother_name": "Pessoa fictícia",
                    "monthly_income_cents": 900000,
                    "vehicle_price_cents": vehicles[i + 6].price_cents,
                    "down_payment_cents": 3000000,
                    "term_months": 48,
                },
            )
            proposta, _ = Proposta.objects.get_or_create(
                organization=org,
                ficha=ficha,
                bank="Banco fictício",
                defaults={
                    "status": status,
                    "monthly_rate_bp": 149,
                    "term_months": 48,
                    "financed_cents": ficha.financed_cents,
                    "installment_cents": ficha.financed_cents // 36,
                    "dealer_return_cents": 120000,
                    "notes": "SIMULAÇÃO. Não submetida a banco; nenhuma aprovação de crédito real.",
                },
            )
            if status == "paga" and not proposta.return_entry_id:
                proposta.return_entry = finance.create(
                    org,
                    kind="receber",
                    description=MARK + "Retorno de financiamento",
                    amount_cents=120000,
                    due_date=today - timedelta(days=3),
                    category_code="retorno_financiamento",
                    paid=True,
                    conta=bank,
                )[0]
                proposta.save(update_fields=["return_entry"])
        for i, status in enumerate(["aberta", "andamento", "resolvida", "negada"]):
            sale = closed[i]
            issue, created = Ocorrencia.objects.get_or_create(
                organization=org,
                garantia=sale.garantia,
                description=MARK + f"Ocorrência {i + 1}",
                defaults={
                    "status": status,
                    "cost_cents": 90000 if i < 3 else 0,
                    "resolution": "Reparo concluído (simulação)" if i == 2 else "Acompanhamento fictício",
                },
            )
            if created and issue.cost_cents:
                issue.lancamento = finance.create(
                    org,
                    kind="pagar",
                    origin="garantia",
                    description=issue.description,
                    amount_cents=issue.cost_cents,
                    due_date=today + timedelta(days=2),
                    paid=i == 2,
                    category_code="garantia",
                    conta=bank,
                    vehicle=sale.vehicle,
                    venda=sale,
                )[0]
                issue.save(update_fields=["lancamento"])
        for offset in range(-2, 2):
            month = add_months(today.replace(day=1), offset)
            for code, amount in [("aluguel", 450000), ("pessoal", 1200000), ("marketing", 150000), ("impostos", 85000)]:
                desc = MARK + f"{code} {month:%m/%Y}"
                if not org.lancamentos.filter(description=desc).exists():
                    entries = finance.create(
                        org,
                        kind="pagar",
                        description=desc,
                        amount_cents=amount,
                        due_date=month + timedelta(days=9),
                        category_code=code,
                        paid=offset < 0,
                        conta=bank,
                    )
                    if offset < 0:
                        Lancamento.objects.filter(pk__in=[e.pk for e in entries]).update(paid_at=month + timedelta(days=9))
        # Metade das comissões gera contas a pagar; as demais continuam a apurar no relatório.
        for sale in closed[:3]:
            desc = MARK + f"Comissão {sale.vehicle.placa}"
            if sale.commission_cents and not org.lancamentos.filter(description=desc).exists():
                finance.create(
                    org,
                    kind="pagar",
                    origin="comissao",
                    description=desc,
                    amount_cents=sale.commission_cents,
                    due_date=today + timedelta(days=5),
                    category_code="comissao",
                    venda=sale,
                )
                sale.commission_paid = True
                sale.save(update_fields=["commission_paid"])
        contracts.ensure_defaults(org)
        Modelo.objects.get_or_create(
            organization=org,
            kind="compra",
            title=MARK + "Modelo de compra",
            defaults={
                "body": "DOCUMENTO FICTÍCIO — SEM VALIDADE JURÍDICA\nCompra demonstrativa de {{veiculo.descricao}} de {{cliente.nome}} pela {{loja.razao_social}}."
            },
        )
        for model in org.modelos_contrato.all():
            sale = closed[0]
            title = MARK + model.title
            if not Documento.objects.filter(organization=org, title=title).exists():
                doc = contracts.generate(model, user=owner, venda=sale)
                doc.title = title[:160]
                doc.content = "DOCUMENTO FICTÍCIO — SEM VALIDADE JURÍDICA\n\n" + doc.content
                doc.save(update_fields=["title", "content"])
        slug = "filial-exemplo-demonstracao" if org.parent_id else "revenda-demonstracao"
        site, _ = Site.objects.get_or_create(
            organization=org,
            defaults={
                "slug": slug,
                "title": str(org),
                "is_published": True,
                "about": "Demonstração fictícia; nenhum veículo anunciado está à venda.",
                "email": "loja@example.invalid",
                "address": "Natal/RN — endereço fictício",
                "feed_token": secrets.token_urlsafe(24),
            },
        )
        if not site.feed_token:
            site.feed_token = secrets.token_urlsafe(24)
            site.save(update_fields=["feed_token"])
        for i, v in enumerate(vehicles[7:10]):
            Anuncio.objects.get_or_create(
                organization=org,
                vehicle=v,
                portal=["olx", "webmotors", "mercadolivre"][i],
                defaults={
                    "status": "ativo" if i == 0 else "pausado",
                    "message": "Exemplo local de feed; nenhuma publicação enviada a portal.",
                },
            )
        self.local_integrations(org, owner, vehicles, people, today)
        record("demo.complementada", actor=owner, organization=org, target=org)

    def local_integrations(self, org, owner, vehicles, people, today):
        FiscalSettings.objects.get_or_create(
            organization=org, defaults={"enviar_chave_renave": False, "informacao_complementar": "DEMONSTRAÇÃO LOCAL — NÃO TRANSMITIR"}
        )
        for i, v in enumerate(vehicles[7:10]):
            rv, _ = StockVehicle.objects.get_or_create(
                organization=org,
                placa=v.placa,
                defaults={
                    "owner_document": org.cnpj,
                    "renavam": "",
                    "state": "NEGADO",
                    "situacao": "DEMONSTRAÇÃO LOCAL — nenhum registro oficial",
                    "marca_modelo": v.title[:120],
                    "ano_fabricacao": v.ano_fabricacao,
                    "ano_modelo": v.ano_modelo,
                    "entry_date": today,
                    "entry_value_cents": v.purchase_price_cents,
                    "raw": {"demo": True, "message": "Exemplo visual. Não consultado nem transmitido ao RENAVE."},
                },
            )
            if not v.renave_id:
                v.renave = rv
                v.save(update_fields=["renave"])
            RenaveOperation.objects.get_or_create(
                organization=org,
                vehicle=rv,
                kind="entrada_compra",
                message=MARK + "Exemplo não transmitido",
                defaults={"user": owner, "success": False, "price_cents": 0, "response": {"demo": True}},
            )
            nota, created = NotaFiscal.objects.get_or_create(
                organization=org,
                ambiente="2",
                serie=999,
                numero=900001 + i,
                defaults={
                    "user": owner,
                    "vehicle": rv,
                    "tipo": "1",
                    "status": "error",
                    "message": MARK + "Sem transmissão ou validade fiscal",
                    "destinatario_nome": people[i].nome,
                    "destinatario_documento": "00000000000",
                    "total_cents": v.price_cents,
                    "payload_encrypted": b"",
                },
            )
            if created:
                nota.set_payload({"demo": True, "message": "Sem validade fiscal. Não transmitir."})
                nota.save(update_fields=["payload_encrypted"])
            cv, created = ComunicacaoVenda.objects.get_or_create(
                organization=org,
                placa=v.placa,
                message=MARK + "Não transmitida",
                defaults={
                    "user": owner,
                    "vehicle": rv,
                    "renavam": "",
                    "comprador_nome": people[i].nome,
                    "valor_cents": v.price_cents,
                    "data_venda": today,
                    "situacao": 5,
                    "payload_encrypted": b"",
                },
            )
            if created:
                cv.set_payload({"demo": True, "message": "Exemplo local, sem comunicação oficial."})
                cv.save(update_fields=["payload_encrypted"])
        product, _ = Product.objects.get_or_create(
            code="demo-local",
            defaults={
                "sku": "DEMO-LOCAL",
                "name": "Consulta fictícia de demonstração",
                "input_type": "PLACA",
                "category": "cadastro",
                "price_cents": 0,
                "is_active": False,
            },
        )
        if product:
            consulta, created = Consulta.objects.get_or_create(
                organization=org,
                product=product,
                input_value=vehicles[7].placa,
                message=MARK + "Consulta local",
                defaults={
                    "user": owner,
                    "sku": product.sku,
                    "input_type": "PLACA",
                    "purpose": "compra",
                    "status": "success",
                    "price_cents": 0,
                    "completed_at": timezone.now(),
                },
            )
            if created:
                consulta.set_result(
                    {
                        "demo": True,
                        "aviso": "DADOS FICTÍCIOS. Nenhuma fonte consultada.",
                        "veiculo": {"marca": vehicles[7].marca, "modelo": vehicles[7].modelo},
                    }
                )
                consulta.save(update_fields=["result_encrypted"])
        wallet.credit(org, 50000, "Crédito fictício para demonstração — sem pagamento", key=f"demo-completa:{org.pk}")
        for status in ("pending", "paid"):
            TopUp.objects.get_or_create(
                organization=org,
                provider="demo",
                provider_reference=f"DEMO-{org.pk}-{status}",
                defaults={
                    "amount_cents": 10000,
                    "status": status,
                    "paid_at": timezone.now() if status == "paid" else None,
                    "requested_by": owner,
                },
            )
        # Histórico visual sem links, gateway ou títulos abertos que gerem cobrança/suspensão.
        if not org.parent_id:
            for status in ("paid", "canceled"):
                desc = MARK + f"Fatura {status}"
                if not InvoiceItem.objects.filter(invoice__organization=org, description__startswith=desc).exists():
                    inv = Invoice.objects.create(
                        organization=org,
                        subscription=org.subscription,
                        kind="renewal",
                        status=status,
                        total_cents=26990,
                        due_date=today,
                        provider="demo",
                        paid_at=timezone.now() if status == "paid" else None,
                        canceled_at=timezone.now() if status == "canceled" else None,
                    )
                    InvoiceItem.objects.create(
                        invoice=inv, kind="adjustment", description=desc + " — sem pagamento real", total_cents=26990
                    )
