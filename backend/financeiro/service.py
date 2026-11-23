"""Regras do financeiro: categorias padrão, lançamentos parcelados, baixa, fluxo de caixa e DRE."""

from collections import defaultdict
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from billing.service import add_months
from core.exceptions import BusinessError

from .models import Categoria, Conta, Lancamento

K = Lancamento.Kind

SYSTEM_CATEGORIES = [
    ("venda_veiculo", "Venda de veículos", Categoria.Kind.RECEITA),
    ("retorno_financiamento", "Retorno de financiamento", Categoria.Kind.RECEITA),
    ("outras_receitas", "Outras receitas", Categoria.Kind.RECEITA),
    ("compra_veiculo", "Compra de veículos", Categoria.Kind.DESPESA),
    ("custo_veiculo", "Preparação de veículos", Categoria.Kind.DESPESA),
    ("comissao", "Comissões de vendedores", Categoria.Kind.DESPESA),
    ("consignacao", "Repasse de consignados", Categoria.Kind.DESPESA),
    ("garantia", "Garantia e pós-venda", Categoria.Kind.DESPESA),
    ("aluguel", "Aluguel e condomínio", Categoria.Kind.DESPESA),
    ("pessoal", "Salários e encargos", Categoria.Kind.DESPESA),
    ("marketing", "Anúncios e marketing", Categoria.Kind.DESPESA),
    ("impostos", "Impostos e taxas", Categoria.Kind.DESPESA),
    ("outras_despesas", "Outras despesas", Categoria.Kind.DESPESA),
]


def ensure_setup(organization) -> None:
    """Cria categorias do sistema e o caixa na primeira vez que a loja usa o financeiro."""
    existing = set(Categoria.objects.filter(organization=organization).exclude(system_code="").values_list("system_code", flat=True))
    Categoria.objects.bulk_create(
        [Categoria(organization=organization, system_code=c, name=n, kind=k) for c, n, k in SYSTEM_CATEGORIES if c not in existing],
        ignore_conflicts=True,
    )
    if not Conta.objects.filter(organization=organization).exists():
        Conta.objects.create(organization=organization, name="Caixa da loja", kind=Conta.Kind.CAIXA)


def category(organization, code: str) -> Categoria:
    ensure_setup(organization)
    return Categoria.objects.get(organization=organization, system_code=code)


def default_account(organization) -> Conta:
    ensure_setup(organization)
    return Conta.objects.filter(organization=organization, is_active=True).order_by("id").first()


def create(
    organization,
    *,
    kind: str,
    description: str,
    amount_cents: int,
    due_date: date,
    installments: int = 1,
    category_code: str | None = None,
    categoria: Categoria | None = None,
    origin: str = Lancamento.Origin.MANUAL,
    paid: bool = False,
    conta: Conta | None = None,
    **links,
) -> list[Lancamento]:
    """Cria um lançamento (ou parcelas mensais). O resto da divisão vai na primeira parcela."""
    if amount_cents <= 0:
        raise BusinessError("O valor precisa ser maior que zero.")
    installments = max(1, min(int(installments or 1), 120))
    if categoria is None and category_code:
        categoria = category(organization, category_code)
    base, rest = divmod(amount_cents, installments)
    today = timezone.localdate()
    items = []
    for i in range(installments):
        value = base + (rest if i == 0 else 0)
        due = add_months(due_date, i)
        label = description if installments == 1 else f"{description} ({i + 1}/{installments})"
        items.append(
            Lancamento(
                organization=organization,
                kind=kind,
                origin=origin,
                description=label[:200],
                categoria=categoria,
                amount_cents=value,
                due_date=due,
                installment=i + 1,
                installments=installments,
                paid_at=today if paid else None,
                paid_cents=value if paid else None,
                conta=(conta or default_account(organization)) if paid else conta,
                **links,
            )
        )
    return Lancamento.objects.bulk_create(items)


def pay(lanc: Lancamento, *, paid_at: date | None = None, paid_cents: int | None = None, conta: Conta | None = None) -> Lancamento:
    if lanc.canceled:
        raise BusinessError("Lançamento cancelado não pode ser baixado.")
    lanc.paid_at = paid_at or timezone.localdate()
    lanc.paid_cents = lanc.amount_cents if paid_cents is None else paid_cents
    lanc.conta = conta or lanc.conta or default_account(lanc.organization)
    lanc.save(update_fields=["paid_at", "paid_cents", "conta", "updated_at"])
    return lanc


def unpay(lanc: Lancamento) -> Lancamento:
    lanc.paid_at = None
    lanc.paid_cents = None
    lanc.bank_ref = ""
    lanc.save(update_fields=["paid_at", "paid_cents", "bank_ref", "updated_at"])
    return lanc


def cancel_open(qs) -> int:
    return qs.filter(paid_at__isnull=True, canceled=False).update(canceled=True, updated_at=timezone.now())


def account_balances(organization) -> list[dict]:
    ensure_setup(organization)
    rows = []
    for conta in Conta.objects.filter(organization=organization):
        moves = conta.lancamentos.filter(paid_at__isnull=False, canceled=False)
        inflow = moves.filter(kind=K.RECEBER).aggregate(v=Sum("paid_cents"))["v"] or 0
        outflow = moves.filter(kind=K.PAGAR).aggregate(v=Sum("paid_cents"))["v"] or 0
        rows.append(
            {
                "id": str(conta.public_id),
                "name": conta.name,
                "kind": conta.kind,
                "balance_cents": conta.opening_balance_cents + inflow - outflow,
                "is_active": conta.is_active,
            }
        )
    return rows


def summary(organization) -> dict:
    today = timezone.localdate()
    open_qs = Lancamento.objects.filter(organization=organization, paid_at__isnull=True, canceled=False)

    def total(qs):
        return qs.aggregate(v=Sum("amount_cents"))["v"] or 0

    return {
        "receber_aberto_cents": total(open_qs.filter(kind=K.RECEBER)),
        "pagar_aberto_cents": total(open_qs.filter(kind=K.PAGAR)),
        "receber_vencido_cents": total(open_qs.filter(kind=K.RECEBER, due_date__lt=today)),
        "pagar_vencido_cents": total(open_qs.filter(kind=K.PAGAR, due_date__lt=today)),
        "pagar_7d_cents": total(open_qs.filter(kind=K.PAGAR, due_date__gte=today, due_date__lte=today + timedelta(days=7))),
        "receber_7d_cents": total(open_qs.filter(kind=K.RECEBER, due_date__gte=today, due_date__lte=today + timedelta(days=7))),
        "saldo_cents": sum(r["balance_cents"] for r in account_balances(organization)),
    }


def cash_flow(organization, start: date, end: date) -> list[dict]:
    """Por dia: realizado (pago) e previsto (em aberto pelo vencimento)."""
    days: dict[date, dict] = defaultdict(lambda: {"in_paid": 0, "out_paid": 0, "in_open": 0, "out_open": 0})
    base = Lancamento.objects.filter(organization=organization, canceled=False)
    for lanc in base.filter(paid_at__range=(start, end)):
        days[lanc.paid_at]["in_paid" if lanc.kind == K.RECEBER else "out_paid"] += lanc.paid_cents or 0
    for lanc in base.filter(paid_at__isnull=True, due_date__range=(start, end)):
        days[lanc.due_date]["in_open" if lanc.kind == K.RECEBER else "out_open"] += lanc.amount_cents
    return [{"date": d.isoformat(), **v} for d, v in sorted(days.items())]


def dre(organization, month: date) -> dict:
    """DRE simplificada do mês, por competência de pagamento (regime de caixa)."""
    start = month.replace(day=1)
    end = add_months(start, 1) - timedelta(days=1)
    qs = Lancamento.objects.filter(organization=organization, canceled=False, paid_at__range=(start, end))
    lines = defaultdict(int)
    for row in qs.values("kind", "categoria__name").annotate(v=Sum("paid_cents")):
        name = row["categoria__name"] or ("Outras receitas" if row["kind"] == K.RECEBER else "Outras despesas")
        lines[(row["kind"], name)] += row["v"] or 0
    receitas = [{"name": n, "cents": v} for (k, n), v in lines.items() if k == K.RECEBER]
    despesas = [{"name": n, "cents": v} for (k, n), v in lines.items() if k == K.PAGAR]
    total_in = sum(x["cents"] for x in receitas)
    total_out = sum(x["cents"] for x in despesas)
    from vendas.models import Venda

    vendas = Venda.objects.filter(organization=organization, status=Venda.Status.FECHADA, closed_at__range=(start, end))
    return {
        "month": start.isoformat(),
        "receitas": sorted(receitas, key=lambda x: -x["cents"]),
        "despesas": sorted(despesas, key=lambda x: -x["cents"]),
        "total_receitas_cents": total_in,
        "total_despesas_cents": total_out,
        "resultado_cents": total_in - total_out,
        "vendas": vendas.count(),
        "lucro_bruto_vendas_cents": vendas.aggregate(v=Sum("profit_cents"))["v"] or 0,
    }


@transaction.atomic
def reconcile(organization, transactions: list[dict]) -> list[dict]:
    """Sugere, para cada transação do extrato, o lançamento em aberto de mesmo valor com vencimento mais próximo."""
    results = []
    used: set[int] = set()
    for tx in transactions:
        amount = abs(tx["amount_cents"])
        kind = K.RECEBER if tx["amount_cents"] > 0 else K.PAGAR
        already = Lancamento.objects.filter(organization=organization, bank_ref=tx["fitid"]).first() if tx.get("fitid") else None
        match = None
        if not already:
            window = (tx["date"] - timedelta(days=10), tx["date"] + timedelta(days=10))
            candidates = (
                Lancamento.objects.filter(
                    organization=organization, kind=kind, amount_cents=amount, paid_at__isnull=True, canceled=False, due_date__range=window
                )
                .exclude(pk__in=used)
                .order_by("due_date")
            )
            match = min(candidates, key=lambda c: abs((c.due_date - tx["date"]).days), default=None)
            if match:
                used.add(match.pk)
        results.append(
            {
                **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in tx.items()},
                "already_reconciled": bool(already),
                "match": {"id": str(match.public_id), "description": match.description, "due_date": match.due_date.isoformat()}
                if match
                else None,
            }
        )
    return results


def search(qs, term: str):
    return qs.filter(Q(description__icontains=term) | Q(pessoa__nome__icontains=term))
