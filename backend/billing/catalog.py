"""Catálogo inicial de planos. Os valores podem ser ajustados depois pelo backoffice."""

F = {
    "gratis": ["renave", "estoque"],
}
F["essencial"] = [*F["gratis"], "fiscal", "financeiro", "custos", "contratos", "avaliacao"]
F["profissional"] = [*F["essencial"], "crm", "comissoes", "consignacao", "vitrine", "assinatura"]
F["premium"] = [*F["profissional"], "financiamento", "multiloja", "relatorios", "posvenda", "conciliacao"]

PLANS = [
    {
        "code": "gratis",
        "name": "Grátis",
        "monthly_price_cents": 0,
        "annual_price_cents": 0,
        "vehicle_limit": 20,
        "user_limit": 1,
        "plate_queries_included": 10,
        "features": F["gratis"],
        "postpaid": False,
        "credit_limit_cents": 0,
        "extra_store_price_cents": 0,
        "sort_order": 0,
    },
    {
        "code": "essencial",
        "name": "Essencial",
        "monthly_price_cents": 9990,
        "annual_price_cents": 99900,
        "vehicle_limit": 40,
        "user_limit": 3,
        "plate_queries_included": 100,
        "features": F["essencial"],
        "postpaid": True,
        "credit_limit_cents": 50000,
        "extra_store_price_cents": 0,
        "sort_order": 1,
    },
    {
        "code": "profissional",
        "name": "Profissional",
        "monthly_price_cents": 15990,
        "annual_price_cents": 159900,
        "vehicle_limit": 100,
        "user_limit": 6,
        "plate_queries_included": 300,
        "features": F["profissional"],
        "postpaid": True,
        "credit_limit_cents": 100000,
        "extra_store_price_cents": 0,
        "sort_order": 2,
    },
    {
        "code": "premium",
        "name": "Premium",
        "monthly_price_cents": 26990,
        "annual_price_cents": 269900,
        "vehicle_limit": None,
        "user_limit": None,
        "plate_queries_included": 1000,
        "features": F["premium"],
        "postpaid": True,
        "credit_limit_cents": 200000,
        "extra_store_price_cents": 4990,
        "sort_order": 3,
    },
]

TRIAL_PLAN = "profissional"
TRIAL_DAYS = 14
FREE_PLAN = "gratis"
# Dias de tolerância após o vencimento antes de suspender a assinatura.
GRACE_DAYS = 5
# Prazo de pagamento das faturas geradas.
DUE_DAYS = 3
