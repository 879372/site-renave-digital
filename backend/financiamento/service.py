"""Simulação de financiamento (Tabela Price) e cálculo do CET."""

from core.exceptions import BusinessError


def installment(principal_cents: int, monthly_rate: float, months: int) -> int:
    if months <= 0:
        raise BusinessError("Prazo inválido.")
    if monthly_rate <= 0:
        return round(principal_cents / months)
    factor = (1 + monthly_rate) ** months
    return round(principal_cents * monthly_rate * factor / (factor - 1))


def monthly_irr(received_cents: int, payment_cents: int, months: int) -> float:
    """Taxa mensal que iguala o valor recebido às parcelas (bisseção)."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        pv = sum(payment_cents / (1 + mid) ** k for k in range(1, months + 1))
        if pv > received_cents:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def simulate(*, price_cents: int, down_cents: int, monthly_rate_bp: int, months: int, fees_cents: int = 0, iof_pct_bp: int = 0) -> dict:
    """`monthly_rate_bp` e `iof_pct_bp` em centésimos de % (199 = 1,99% a.m.)."""
    if price_cents <= 0 or not 0 <= down_cents < price_cents:
        raise BusinessError("Informe o valor do carro e uma entrada menor que ele.")
    if not 1 <= months <= 96:
        raise BusinessError("Prazo entre 1 e 96 meses.")
    received = price_cents - down_cents
    iof = received * iof_pct_bp // 10000
    principal = received + fees_cents + iof
    pmt = installment(principal, monthly_rate_bp / 10000, months)
    cet_m = monthly_irr(received, pmt, months) if pmt * months > received else 0.0
    return {
        "financed_cents": received,
        "fees_cents": fees_cents,
        "iof_cents": iof,
        "principal_cents": principal,
        "installment_cents": pmt,
        "total_cents": pmt * months + down_cents,
        "interest_cents": pmt * months - received,
        "cet_monthly_bp": round(cet_m * 10000),
        "cet_annual_bp": round(((1 + cet_m) ** 12 - 1) * 10000),
    }
