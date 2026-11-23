"""Fluxos de gestão da loja: estoque, avaliação, vendas, financeiro, contratos, CRM, site, financiamento, pós-venda e multi-loja."""

from datetime import timedelta
from io import BytesIO

import httpx
import pytest
import respx
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from billing import entitlements
from billing import service as billing
from billing.models import Plan
from estoque.models import Avaliacao, Vehicle
from financeiro.models import Lancamento
from organizations.models import Membership, Organization, Role
from pessoas.models import Pessoa
from vendas.models import RegraComissao, Venda
from wallet import service as wallet

from .conftest import OTHER_CNPJ

TODAY = timezone.localdate


def use_plan(org, code):
    entitlements.get_subscription(org)
    billing.grant_plan(org.subscription, Plan.objects.get(code=code), "monthly")


@pytest.fixture
def premium(org):
    use_plan(org, "premium")
    return org


@pytest.fixture
def cliente(org):
    return Pessoa.objects.create(
        organization=org,
        nome="Maria Compradora",
        documento="52998224725",
        email="maria@x.com",
        telefone="84999990000",
        cep="59000000",
        logradouro="Rua A",
        numero="10",
        bairro="Centro",
        cidade="Natal",
        cidade_ibge="2408102",
        uf="RN",
    )


def make_vehicle(api, **kw):
    body = {
        "marca": "Chevrolet",
        "modelo": "Onix",
        "ano_fabricacao": 2021,
        "ano_modelo": 2022,
        "placa": "ABC1D23",
        "price_cents": 6000000,
        "purchase_price_cents": 5000000,
        **kw,
    }
    r = api.post("/api/estoque/veiculos", body, format="json")
    assert r.status_code == 201, r.json()
    return r.json()["id"]


def image_file(name="foto.png"):
    buf = BytesIO()
    Image.new("RGB", (2400, 1200), "green").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


# --- estoque ---------------------------------------------------------------------------------


def test_cadastro_de_veiculo_e_limite_do_plano(api, org):
    use_plan(org, "gratis")
    plan = Plan.objects.get(code="gratis")
    plan.vehicle_limit = 2
    plan.save()
    make_vehicle(api, placa="AAA1A11")
    make_vehicle(api, placa="AAA1A12")
    r = api.post("/api/estoque/veiculos", {"marca": "Fiat", "modelo": "Uno"}, format="json")
    assert r.status_code == 402 and r.json()["error"]["code"] == "plan_limit"


def test_placa_invalida_e_consignado_exige_plano(api, org):
    use_plan(org, "essencial")
    assert api.post("/api/estoque/veiculos", {"marca": "Fiat", "modelo": "Uno", "placa": "XX"}, format="json").status_code == 400
    dono = Pessoa.objects.create(organization=org, nome="Dono")
    r = api.post(
        "/api/estoque/veiculos",
        {
            "marca": "Fiat",
            "modelo": "Uno",
            "ownership": "consignado",
            "consignor": str(dono.public_id),
            "consignment_mode": "comissao",
            "consignment_value": 800,
        },
        format="json",
    )
    assert r.status_code == 402 and r.json()["error"]["feature"] == "consignacao"


def test_fotos_sao_reduzidas_e_documento_so_por_api(api, premium, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    vid = make_vehicle(api)
    r = api.post(f"/api/estoque/veiculos/{vid}/photos", {"files": [image_file(), image_file("b.png")]}, format="multipart")
    assert r.status_code == 201 and len(r.json()) == 2
    v = Vehicle.objects.get(public_id=vid)
    with Image.open(v.photos.first().image.path) as img:
        assert max(img.size) <= 1600 and img.format == "JPEG"
    bad = SimpleUploadedFile("x.png", b"nao e imagem", content_type="image/png")
    assert api.post(f"/api/estoque/veiculos/{vid}/photos", {"files": [bad]}, format="multipart").status_code == 422

    pdf = SimpleUploadedFile("crlv.pdf", b"%PDF-1.4 teste", content_type="application/pdf")
    r = api.post(f"/api/estoque/veiculos/{vid}/documents", {"file": pdf, "kind": "crlv"}, format="multipart")
    assert r.status_code == 201
    assert r.json()["url"].startswith("/api/estoque/veiculos/")
    assert api.get(r.json()["url"]).status_code == 200
    assert APIClient().get(r.json()["url"]).status_code in (401, 403)


def test_custo_gera_conta_a_pagar_e_entra_na_margem(api, premium):
    vid = make_vehicle(api)
    r = api.post(
        f"/api/estoque/veiculos/{vid}/costs",
        {"category": "funilaria", "description": "Para-choque", "amount_cents": 80000, "date": TODAY().isoformat()},
        format="json",
    )
    assert r.status_code == 201
    lanc = Lancamento.objects.get(origin="custo")
    assert lanc.kind == "pagar" and lanc.amount_cents == 80000
    detail = api.get(f"/api/estoque/veiculos/{vid}").json()
    assert detail["summary"]["total_cost_cents"] == 5080000
    assert detail["summary"]["expected_profit_cents"] == 6000000 - 5080000


def test_gratis_nao_lanca_custos(api, org):
    use_plan(org, "gratis")
    vid = make_vehicle(api)
    r = api.post(
        f"/api/estoque/veiculos/{vid}/costs",
        {"category": "outros", "description": "x", "amount_cents": 100, "date": TODAY().isoformat()},
        format="json",
    )
    assert r.status_code == 402


def test_isolamento_entre_lojas(api, premium, user):
    vid = make_vehicle(api)
    other = Organization.objects.create(cnpj=OTHER_CNPJ, legal_name="Outra", uf="RN", city="Natal")
    Membership.objects.create(user=user, organization=other, role=Role.OWNER)
    c = APIClient()
    c.force_authenticate(user)
    c.credentials(HTTP_X_ORGANIZATION=str(other.public_id))
    assert c.get(f"/api/estoque/veiculos/{vid}").status_code == 404
    pessoa = Pessoa.objects.create(organization=premium, nome="Cliente da loja 1")
    r = c.post("/api/vendas/", {"vehicle": vid, "cliente": str(pessoa.public_id), "price_cents": 100}, format="json")
    assert r.status_code == 400  # não aponta para dados de outra loja


# --- placa e FIPE ----------------------------------------------------------------------------

PLACA_RESP = {
    "MARCA": "CHEVROLET",
    "MODELO": "ONIX 1.0",
    "ano": "2021",
    "anoModelo": "2022",
    "cor": "Branca",
    "fipe": {"dados": [{"codigo_fipe": "004462-3", "texto_valor": "R$ 72.500,00", "score": 90}]},
}


@respx.mock
def test_consulta_de_placa_usa_franquia_e_depois_cobra(api, org):
    use_plan(org, "essencial")
    plan = Plan.objects.get(code="essencial")
    plan.plate_queries_included = 1
    plan.save()
    route = respx.get(url__regex=r"https://wdapi2\.com\.br/consulta/.*").mock(return_value=httpx.Response(200, json=PLACA_RESP))
    r = api.get("/api/estoque/veiculos/plate/ABC1D23")
    assert r.status_code == 200 and r.json()["marca"] == "Chevrolet" and r.json()["fipe"]["price_cents"] == 7250000
    assert api.get("/api/estoque/veiculos/plate/ABC1D23").json()["cached"] is True  # mesma placa não conta de novo
    # Essencial é pós-pago: acima da franquia a consulta vai para a fatura do mês.
    assert api.get("/api/estoque/veiculos/plate/BCD2E34").json()["charged_cents"] == 50
    assert wallet.get_wallet(org).balance_cents == -50
    # Grátis é pré-pago: franquia esgotada e carteira vazia bloqueiam.
    use_plan(org, "gratis")
    wallet.credit(org, 50, "zera", key="z")
    gratis = Plan.objects.get(code="gratis")
    gratis.plate_queries_included = 0
    gratis.save()
    assert api.get("/api/estoque/veiculos/plate/CDE3F45").status_code == 402
    assert route.call_count == 2
    from integrations.models import IntegrationCall

    assert all("placa_test" not in c.path for c in IntegrationCall.objects.filter(provider="placa"))


@respx.mock
def test_fipe_por_marca_modelo_ano(api, org):
    respx.get("https://fipe.parallelum.com.br/api/v2/cars/brands/23/models/5585/years/2022-1").mock(
        return_value=httpx.Response(
            200, json={"codeFipe": "004462-3", "price": "R$ 72.500,00", "referenceMonth": "novembro de 2026", "model": "Onix"}
        )
    )
    r = api.get("/api/estoque/fipe/carro/marcas/23/modelos/5585/anos/2022-1")
    assert r.status_code == 200 and r.json()["price_cents"] == 7250000


# --- avaliação e compra ------------------------------------------------------------------------


def test_avaliacao_aprovada_vira_veiculo_e_conta_a_pagar(api, premium, cliente):
    r = api.post(
        "/api/estoque/avaliacoes",
        {
            "marca": "Fiat",
            "modelo": "Argo",
            "placa": "QWE1R23",
            "km": 40000,
            "cliente": str(cliente.public_id),
            "fipe_price_cents": 6000000,
            "estimated_repairs_cents": 200000,
            "offer_cents": 4500000,
            "checklist": {"pneus": "ok", "motor": "atencao"},
        },
        format="json",
    )
    assert r.status_code == 201, r.json()
    av = r.json()
    assert av["max_offer_cents"] == 6000000 * 85 // 100 - 200000
    assert api.post(f"/api/estoque/avaliacoes/{av['id']}/buy").status_code == 400  # precisa aprovar
    assert api.post(f"/api/estoque/avaliacoes/{av['id']}/approve", {"offer_cents": 4400000}, format="json").status_code == 200
    r = api.post(f"/api/estoque/avaliacoes/{av['id']}/buy", {"paid": True}, format="json")
    assert r.status_code == 201
    v = Vehicle.objects.get(public_id=r.json()["vehicle_id"])
    assert v.purchase_price_cents == 4400000 and v.supplier == cliente and v.status == Vehicle.Status.PREPARACAO
    compra = Lancamento.objects.get(origin="compra")
    assert compra.amount_cents == 4400000 and compra.paid_at is not None
    assert api.post(f"/api/estoque/avaliacoes/{av['id']}/buy").status_code == 400


# --- vendas ------------------------------------------------------------------------------------


def _venda(api, vid, cliente, price=6000000):
    r = api.post("/api/vendas/", {"vehicle": vid, "cliente": str(cliente.public_id), "price_cents": price}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()["id"]


def test_venda_completa_com_troca_financiamento_e_comissao(api, premium, cliente, user):
    RegraComissao.objects.create(organization=premium, mode="sobra", value=1000)
    vid = make_vehicle(api)
    api.post(
        f"/api/estoque/veiculos/{vid}/costs",
        {"category": "mecanica", "description": "Revisão", "amount_cents": 100000, "date": TODAY().isoformat()},
        format="json",
    )
    av = Avaliacao.objects.create(
        organization=premium, marca="VW", modelo="Gol", status=Avaliacao.Status.APROVADA, offer_cents=2000000, cliente=cliente
    )
    venda_id = _venda(api, vid, cliente)

    r = api.post(f"/api/vendas/{venda_id}/reserve", {"amount_cents": 500000}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "reservada"
    assert Vehicle.objects.get(public_id=vid).status == Vehicle.Status.RESERVADO

    items = [
        {"method": "troca", "amount_cents": 2000000, "trade_in": str(av.public_id)},
        {"method": "financiamento", "amount_cents": 3000000, "bank": "Banco X"},
        {"method": "pix", "amount_cents": 400000},
    ]
    r = api.put(f"/api/vendas/{venda_id}/payments", {"items": items}, format="json")
    assert r.status_code == 200 and r.json()["paid_total_cents"] == 5900000
    r = api.post(f"/api/vendas/{venda_id}/close")
    assert r.status_code == 422 and r.json()["error"]["code"] == "payments_mismatch"

    items[2]["amount_cents"] = 500000
    api.put(f"/api/vendas/{venda_id}/payments", {"items": items}, format="json")
    r = api.post(f"/api/vendas/{venda_id}/close")
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["status"] == "fechada"
    assert body["cost_cents"] == 5100000 and body["profit_cents"] == 900000
    assert body["commission_cents"] == 90000  # 10% da sobra
    assert body["garantia_ate"] == (TODAY() + timedelta(days=90)).isoformat()

    v = Vehicle.objects.get(public_id=vid)
    assert v.status == Vehicle.Status.VENDIDO and v.sold_at == TODAY()
    troca = Vehicle.objects.get(avaliacao=av)
    assert troca.purchase_price_cents == 2000000 and not Lancamento.objects.filter(origin="compra", vehicle=troca).exists()
    venda = Venda.objects.get(public_id=venda_id)
    rec = venda.lancamentos.filter(kind="receber")
    assert {(lanc.description.split(" —")[0], lanc.amount_cents, bool(lanc.paid_at)) for lanc in rec} == {
        ("Sinal", 500000, True),
        ("Financiamento Banco X", 3000000, False),
        ("Pix", 500000, True),
    }

    # comissões do mês: relatório e fechamento
    rel = api.get("/api/vendas/comissoes").json()["rows"]
    assert rel[0]["commission_pending_cents"] == 90000
    assert api.post("/api/vendas/comissoes", {}, format="json").json()["sellers"] == 1
    assert Lancamento.objects.get(origin="comissao").amount_cents == 90000

    # cancelar com comissão paga é bloqueado
    assert api.post(f"/api/vendas/{venda_id}/cancel", {"reason": "Cliente desistiu"}, format="json").status_code == 422


def test_cancelar_venda_devolve_carro_e_cancela_recebiveis(api, premium, cliente):
    vid = make_vehicle(api)
    venda_id = _venda(api, vid, cliente)
    api.put(
        f"/api/vendas/{venda_id}/payments", {"items": [{"method": "boleto", "amount_cents": 6000000, "installments": 3}]}, format="json"
    )
    assert api.post(f"/api/vendas/{venda_id}/close").status_code == 200
    venda = Venda.objects.get(public_id=venda_id)
    assert venda.lancamentos.filter(kind="receber").count() == 3
    r = api.post(f"/api/vendas/{venda_id}/cancel", {"reason": "Desistência no prazo"}, format="json")
    assert r.status_code == 200 and r.json()["canceled_entries"] == 3
    assert Vehicle.objects.get(public_id=vid).status == Vehicle.Status.DISPONIVEL
    assert not hasattr(Venda.objects.get(pk=venda.pk), "garantia") or not Venda.objects.get(pk=venda.pk).garantia


def test_consignado_gera_repasse_ao_dono(api, premium, cliente):
    dono = Pessoa.objects.create(organization=premium, nome="Dono do carro")
    vid = make_vehicle(
        api,
        ownership="consignado",
        consignor=str(dono.public_id),
        consignment_mode="comissao",
        consignment_value=1000,
        purchase_price_cents=0,
    )
    venda_id = _venda(api, vid, cliente, price=5000000)
    api.put(f"/api/vendas/{venda_id}/payments", {"items": [{"method": "pix", "amount_cents": 5000000}]}, format="json")
    body = api.post(f"/api/vendas/{venda_id}/close").json()
    assert body["consignor_payout_cents"] == 4500000 and body["profit_cents"] == 500000
    repasse = Lancamento.objects.get(origin="consignacao")
    assert repasse.amount_cents == 4500000 and repasse.pessoa == dono


def test_vendedor_ve_so_as_proprias_vendas(api, premium, cliente, user):
    vid = make_vehicle(api)
    _venda(api, vid, cliente)
    Membership.objects.filter(user=user, organization=premium).update(role=Role.SELLER)
    assert api.get("/api/vendas/").json()["count"] == 1  # é dele
    Venda.objects.update(seller=None)
    assert api.get("/api/vendas/").json()["count"] == 0
    assert api.post(f"/api/estoque/veiculos/{vid}/costs", {}, format="json").status_code == 403


# --- financeiro --------------------------------------------------------------------------------


def test_lancamento_parcelado_baixa_e_dre(api, premium):
    r = api.post(
        "/api/financeiro/lancamentos",
        {"kind": "pagar", "description": "Aluguel", "amount_cents": 100001, "installments": 3, "due_date": TODAY().isoformat()},
        format="json",
    )
    assert r.status_code == 201 and [x["amount_cents"] for x in r.json()] == [33335, 33333, 33333]
    first = r.json()[0]["id"]
    assert api.post(f"/api/financeiro/lancamentos/{first}/pagar", {}, format="json").json()["status"] == "pago"
    resumo = api.get("/api/financeiro/resumo").json()
    assert resumo["pagar_aberto_cents"] == 66666 and resumo["saldo_cents"] == -33335
    dre = api.get("/api/financeiro/dre").json()
    assert dre["total_despesas_cents"] == 33335
    assert api.post(f"/api/financeiro/lancamentos/{first}/cancelar").status_code == 400  # pago: estorne antes
    assert api.post(f"/api/financeiro/lancamentos/{first}/estornar").json()["status"] in ("aberto", "vencido")
    assert len(api.get("/api/financeiro/fluxo").json()) >= 1


OFX = b"""OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>%s<TRNAMT>-1500.00<FITID>A1<MEMO>PAGTO FORNECEDOR
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>%s<TRNAMT>999.99<FITID>A2<MEMO>PIX RECEBIDO
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""


def test_conciliacao_ofx(api, premium):
    d = TODAY().strftime("%Y%m%d").encode()
    api.post(
        "/api/financeiro/lancamentos",
        {"kind": "pagar", "description": "Peças", "amount_cents": 150000, "due_date": TODAY().isoformat()},
        format="json",
    )
    upload = SimpleUploadedFile("extrato.ofx", OFX % (d, d), content_type="application/x-ofx")
    rows = api.post("/api/financeiro/conciliacao", {"file": upload}, format="multipart").json()
    assert rows[0]["match"] is not None and rows[1]["match"] is None
    pair = {"lancamento": rows[0]["match"]["id"], "fitid": "A1", "date": TODAY().isoformat()}
    assert api.post("/api/financeiro/conciliacao", {"confirm": True, "pairs": [pair]}, format="json").json()["reconciled"] == 1
    assert Lancamento.objects.get(bank_ref="A1").paid_at == TODAY()


# --- contratos ---------------------------------------------------------------------------------


def test_contrato_preenchido_com_dados_da_venda(api, premium, cliente):
    from contratos.service import extenso

    assert extenso(6_000_000) == "sessenta mil reais"
    assert extenso(1_234_550) == "doze mil trezentos e quarenta e cinco reais e cinquenta centavos"
    assert extenso(150_000_000) == "um milhão e quinhentos mil reais"
    assert extenso(100) == "um real"
    vid = make_vehicle(api)
    venda_id = _venda(api, vid, cliente)
    modelos = api.get("/api/contratos/modelos").json()
    cv = next(m for m in modelos if m["kind"] == "compra_venda")
    r = api.post("/api/contratos/documentos/generate", {"modelo": cv["id"], "venda": venda_id}, format="json")
    assert r.status_code == 201
    text = r.json()["content"]
    assert "Maria Compradora" in text and "529.982.247-25" in text and "ABC-1D23" in text and "R$ 60.000,00" in text
    assert "{{" not in text
    r = api.post(f"/api/contratos/documentos/{r.json()['id']}/sign", {"signers": [{"name": "Maria"}]}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "signature_off"


# --- CRM e site --------------------------------------------------------------------------------


def test_funil_de_leads(api, premium):
    r = api.post("/api/crm/leads", {"name": "João", "phone": "84988887777", "source": "instagram"}, format="json")
    assert r.status_code == 201
    lid = r.json()["id"]
    assert api.post(f"/api/crm/leads/{lid}/move", {"stage": "perdido"}, format="json").status_code == 400
    assert api.post(f"/api/crm/leads/{lid}/move", {"stage": "visita"}, format="json").json()["stage"] == "visita"
    api.post(f"/api/crm/leads/{lid}/interactions", {"kind": "ligacao", "text": "Vem sábado"}, format="json")
    kinds = [i["kind"] for i in api.get(f"/api/crm/leads/{lid}/interactions").json()]
    assert kinds[:2] == ["ligacao", "etapa"]
    r = api.post("/api/crm/tarefas", {"lead": lid, "title": "Ligar", "due_at": timezone.now().isoformat()}, format="json")
    assert r.status_code == 201
    assert api.post(f"/api/crm/leads/{lid}/convert").status_code == 201


def test_site_publico_contato_e_feed(api, premium, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    vid = make_vehicle(api, published=True)
    api.post(f"/api/estoque/veiculos/{vid}/status", {"status": "disponivel"}, format="json")
    assert api.put("/api/site/", {"slug": "admin", "title": "Loja"}, format="json").status_code == 400
    r = api.put(
        "/api/site/", {"slug": "loja-exemplo", "title": "Loja Exemplo", "is_published": True, "whatsapp": "84999999999"}, format="json"
    )
    assert r.status_code == 200 and r.json()["url"].startswith("https://loja-exemplo.")
    feed_url = r.json()["feed_url"]

    pub = APIClient()
    data = pub.get("/api/public/lojas/loja-exemplo/veiculos").json()
    assert len(data["results"]) == 1 and "purchase_price_cents" not in data["results"][0]
    detail = pub.get(f"/api/public/lojas/loja-exemplo/veiculos/{vid}").json()
    assert detail["final_placa"] == "3" and "placa" not in detail
    r = pub.post(
        "/api/public/lojas/loja-exemplo/contato", {"name": "Ana", "phone": "84911112222", "vehicle_id": vid, "consent": True}, format="json"
    )
    assert r.status_code == 201
    from crm.models import Lead

    assert Lead.objects.get(source="site").vehicle.public_id.hex == vid.replace("-", "")
    assert (
        pub.post(
            "/api/public/lojas/loja-exemplo/contato", {"name": "Bot", "phone": "1", "website": "x", "consent": True}, format="json"
        ).status_code
        == 204
    )

    path = feed_url.split("/api", 1)[1]
    xml = pub.get("/api" + path)
    assert xml.status_code == 200 and b"<marca>Chevrolet</marca>" in xml.content
    assert pub.get("/api/public/feed/loja-exemplo/errado.xml").status_code == 404

    use_plan(premium, "essencial")  # sem o recurso, o site sai do ar
    assert pub.get("/api/public/lojas/loja-exemplo").status_code == 404


# --- financiamento e pós-venda ------------------------------------------------------------------


def test_simulacao_e_retorno_da_financeira(api, premium, cliente):
    sim = api.post(
        "/api/financiamento/simular",
        {"price_cents": 6000000, "down_cents": 2000000, "monthly_rate_bp": 199, "months": 48, "fees_cents": 80000, "terms": [24, 48]},
        format="json",
    ).json()
    assert [s["months"] for s in sim] == [24, 48]
    s48 = sim[1]
    assert 125000 < s48["installment_cents"] < 140000
    assert s48["cet_monthly_bp"] > 199  # tarifas elevam o CET acima da taxa
    r = api.post(
        "/api/financiamento/fichas",
        {"cliente": str(cliente.public_id), "vehicle_price_cents": 6000000, "down_payment_cents": 2000000, "monthly_income_cents": 800000},
        format="json",
    )
    assert r.status_code == 201
    fid = r.json()["id"]
    p = api.post(
        f"/api/financiamento/fichas/{fid}/propostas",
        {"bank": "Banco X", "monthly_rate_bp": 199, "dealer_return_cents": 120000},
        format="json",
    ).json()
    api.patch(f"/api/financiamento/fichas/{fid}/propostas/{p['id']}", {"status": "paga"}, format="json")
    api.patch(f"/api/financiamento/fichas/{fid}/propostas/{p['id']}", {"notes": "ok"}, format="json")
    assert Lancamento.objects.filter(description__startswith="Retorno Banco X").count() == 1


def test_ocorrencia_de_garantia_gera_custo(api, premium, cliente):
    vid = make_vehicle(api)
    venda_id = _venda(api, vid, cliente)
    api.put(f"/api/vendas/{venda_id}/payments", {"items": [{"method": "pix", "amount_cents": 6000000}]}, format="json")
    api.post(f"/api/vendas/{venda_id}/close")
    g = api.get("/api/posvenda/garantias").json()["results"][0]
    r = api.post("/api/posvenda/ocorrencias", {"garantia": g["id"], "description": "Barulho no câmbio", "cost_cents": 35000}, format="json")
    assert r.status_code == 201
    assert Lancamento.objects.get(origin="garantia").amount_cents == 35000
    api.patch(f"/api/posvenda/ocorrencias/{r.json()['id']}", {"cost_cents": 40000, "status": "resolvida"}, format="json")
    assert Lancamento.objects.get(origin="garantia").amount_cents == 40000


def test_essencial_nao_tem_financiamento_nem_relatorios(api, org):
    use_plan(org, "essencial")
    assert api.get("/api/financiamento/fichas").status_code == 402
    assert api.get("/api/painel/relatorios").status_code == 402
    assert api.get("/api/painel/dashboard").status_code == 200


# --- painel, relatórios e multi-loja ----------------------------------------------------------


def test_painel_e_relatorio_csv(api, premium, cliente):
    vid = make_vehicle(api)
    Vehicle.objects.filter(public_id=vid).update(entry_date=TODAY() - timedelta(days=95))
    d = api.get("/api/painel/dashboard").json()
    assert d["stock"]["count"] == 1 and d["stock"]["stale_90"] == 1 and "finance" in d and "leads" in d
    venda_id = _venda(api, vid, cliente)
    api.put(f"/api/vendas/{venda_id}/payments", {"items": [{"method": "pix", "amount_cents": 6000000}]}, format="json")
    api.post(f"/api/vendas/{venda_id}/close")
    giro = api.get("/api/painel/relatorios?tipo=giro").json()
    assert giro["rows"][0]["units"] == 1 and giro["rows"][0]["avg_days"] == 95
    csv = api.get("/api/painel/relatorios?tipo=vendas&export=csv")
    assert csv.status_code == 200 and "60000,00" in csv.content.decode("utf-8")


def test_filial_herda_plano_cobra_loja_extra_e_recebe_transferencia(api, premium, user):
    r = api.post("/api/lojas/", {"cnpj": OTHER_CNPJ, "legal_name": "Filial Ltda", "uf": "RN", "city": "Mossoró"}, format="json")
    assert r.status_code == 201
    branch = Organization.objects.get(cnpj=OTHER_CNPJ)
    assert branch.parent == premium and entitlements.plan_for(branch).code == "premium"
    from billing.models import Subscription

    assert not Subscription.objects.filter(organization=branch).exists()

    vid = make_vehicle(api)
    r = api.post("/api/lojas/transferir", {"vehicle": vid, "target": str(branch.public_id)}, format="json")
    assert r.status_code == 200
    assert Vehicle.objects.get(public_id=vid).organization == branch

    sub = Subscription.objects.get(organization=premium)
    inv = billing.renew(sub, sub.next_billing_date)
    assert dict(inv.items.values_list("kind", "total_cents"))["extra_store"] == 4990

    bc = APIClient()
    bc.force_authenticate(user)
    bc.credentials(HTTP_X_ORGANIZATION=str(branch.public_id))
    assert bc.post("/api/billing/change-plan", {"plan": "essencial"}, format="json").status_code == 422


def test_essencial_nao_abre_filial(api, org):
    use_plan(org, "essencial")
    r = api.post("/api/lojas/", {"cnpj": OTHER_CNPJ, "legal_name": "Filial", "uf": "RN", "city": "Natal"}, format="json")
    assert r.status_code == 402
