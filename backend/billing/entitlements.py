"""O que cada loja pode usar, conforme o plano.

A REVENDA DIGITAL é exclusiva para gestão de lojas de veículos: toda empresa
cadastrada tem uma assinatura (começa no teste e cai no Grátis).
"""

from core.exceptions import BusinessError

from .catalog import FREE_PLAN
from .models import Feature, Plan, Subscription


class PlanRequired(BusinessError):
    status_code = 402
    default_code = "plan_required"
    default_detail = "Este recurso não está disponível no seu plano."


class PlanLimitReached(BusinessError):
    status_code = 402
    default_code = "plan_limit"
    default_detail = "Você atingiu o limite do seu plano."


def applies(organization) -> bool:
    """Toda empresa está nos planos (mantido como função para o caso de exceções futuras)."""
    return True


def get_subscription(organization) -> Subscription | None:
    if not applies(organization):
        return None
    sub = Subscription.objects.select_related("plan").filter(organization=organization).first()
    if sub is None:
        from .service import start_trial

        sub = start_trial(organization)
    return sub


def effective_plan(sub: Subscription) -> Plan:
    """Assinatura suspensa por falta de pagamento usa os recursos do Grátis (os dados ficam guardados)."""
    if sub.status == Subscription.Status.SUSPENDED:
        return Plan.objects.get(code=FREE_PLAN)
    return sub.plan


def plan_for(organization) -> Plan | None:
    sub = get_subscription(organization)
    return effective_plan(sub) if sub else None


def has_feature(organization, feature: str) -> bool:
    plan = plan_for(organization)
    return True if plan is None else plan.has_feature(feature)


def cheapest_plan_with(feature: str) -> Plan | None:
    for plan in Plan.objects.filter(is_active=True).order_by("sort_order"):
        if plan.has_feature(feature):
            return plan
    return None


def require_feature(organization, feature: str) -> None:
    if has_feature(organization, feature):
        return
    needed = cheapest_plan_with(feature)
    label = Feature(feature).label if feature in Feature.values else feature
    msg = f"{label} está disponível a partir do plano {needed.name}." if needed else f"{label} não está disponível no seu plano."
    raise PlanRequired(msg, extra={"feature": feature, "required_plan": needed.code if needed else None})


def limit(organization, name: str) -> int | None:
    """Limite numérico do plano (`vehicles`, `users`, `plate_queries`). None = ilimitado."""
    plan = plan_for(organization)
    if plan is None:
        return None
    return {"vehicles": plan.vehicle_limit, "users": plan.user_limit, "plate_queries": plan.plate_queries_included}[name]


def check_limit(organization, name: str, current: int, label: str) -> None:
    """Lança PlanLimitReached se `current` já alcançou o limite."""
    cap = limit(organization, name)
    if cap is not None and current >= cap:
        raise PlanLimitReached(f"Seu plano permite até {cap} {label}. Mude de plano para continuar.", extra={"limit": name, "max": cap})


def included_in_plan(organization, service_code: str) -> bool:
    """Serviços que o plano já cobre e não devem ser debitados por uso."""
    if service_code == "fiscal.nfe":
        return applies(organization) and has_feature(organization, Feature.FISCAL)
    return False
