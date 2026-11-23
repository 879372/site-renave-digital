"""Painel da loja e relatórios avançados (Premium)."""

import csv
from datetime import date, timedelta

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.entitlements import has_feature
from billing.permissions import PlanFeaturePermission
from billing.service import add_months
from crm.models import Lead
from estoque.models import Vehicle
from organizations.tenancy import OrganizationPermission
from vendas.models import Venda


def _orgs(request):
    """Lojas consideradas: a ativa, ou todas do grupo (?grupo=1, Premium)."""
    org = request.organization
    if request.query_params.get("grupo") == "1" and has_feature(org, "multiloja"):
        root = org.parent or org
        from organizations.models import Membership

        ids = [root.pk, *root.branches.values_list("pk", flat=True)]
        allowed = set(
            Membership.objects.filter(user=request.user, is_active=True, organization_id__in=ids).values_list("organization_id", flat=True)
        )
        return [i for i in ids if i in allowed]
    return [org.pk]


class DashboardView(APIView):
    permission_classes = [OrganizationPermission]
    required_perm = "view"

    def get(self, request):
        org = request.organization
        orgs = _orgs(request)
        today = timezone.localdate()
        month_start = today.replace(day=1)
        active = Vehicle.objects.filter(organization_id__in=orgs, status__in=Vehicle.ACTIVE)
        stock_value = active.aggregate(v=Sum("price_cents"))["v"] or 0
        stock_cost = sum(v.total_cost() for v in active.prefetch_related("costs"))
        ages = [(today - v.entry_date).days for v in active.only("entry_date") if v.entry_date]
        stale = active.filter(entry_date__lte=today - timedelta(days=60)).order_by("entry_date")[:8]
        sales_month = Venda.objects.filter(organization_id__in=orgs, status=Venda.Status.FECHADA, closed_at__gte=month_start)
        agg = sales_month.aggregate(n=Count("id"), revenue=Sum("price_cents"), profit=Sum("profit_cents"))

        six = add_months(month_start, -5)
        series = (
            Venda.objects.filter(organization_id__in=orgs, status=Venda.Status.FECHADA, closed_at__gte=six)
            .annotate(m=TruncMonth("closed_at"))
            .values("m")
            .annotate(n=Count("id"), revenue=Sum("price_cents"), profit=Sum("profit_cents"))
            .order_by("m")
        )
        by_month = {row["m"].strftime("%Y-%m"): row for row in series}
        chart = []
        for i in range(6):
            m = add_months(six, i)
            row = by_month.get(m.strftime("%Y-%m"), {})
            chart.append(
                {
                    "month": m.isoformat(),
                    "units": row.get("n", 0),
                    "revenue_cents": row.get("revenue") or 0,
                    "profit_cents": row.get("profit") or 0,
                }
            )

        body = {
            "stock": {
                "count": active.count(),
                "available": active.filter(status=Vehicle.Status.DISPONIVEL).count(),
                "preparing": active.filter(status=Vehicle.Status.PREPARACAO).count(),
                "reserved": active.filter(status=Vehicle.Status.RESERVADO).count(),
                "value_cents": stock_value,
                "cost_cents": stock_cost,
                "avg_age_days": round(sum(ages) / len(ages)) if ages else 0,
                "stale_60": active.filter(entry_date__lte=today - timedelta(days=60)).count(),
                "stale_90": active.filter(entry_date__lte=today - timedelta(days=90)).count(),
                "no_photos": active.filter(photos__isnull=True).count(),
            },
            "sales_month": {"units": agg["n"] or 0, "revenue_cents": agg["revenue"] or 0, "profit_cents": agg["profit"] or 0},
            "chart": chart,
            "stale": [
                {
                    "id": str(v.public_id),
                    "title": v.title,
                    "placa": v.placa,
                    "days": (today - v.entry_date).days,
                    "price_cents": v.price_cents,
                }
                for v in stale
            ],
            "open_proposals": Venda.objects.filter(
                organization_id__in=orgs, status__in=[Venda.Status.PROPOSTA, Venda.Status.RESERVADA]
            ).count(),
        }
        if has_feature(org, "financeiro"):
            from financeiro import service as fin

            body["finance"] = fin.summary(org)
        if has_feature(org, "crm"):
            body["leads"] = {
                "new": Lead.objects.filter(organization_id__in=orgs, stage=Lead.Stage.NOVO).count(),
                "open": Lead.objects.filter(organization_id__in=orgs).exclude(stage__in=[Lead.Stage.GANHO, Lead.Stage.PERDIDO]).count(),
                "tasks_today": org.tarefas.filter(done_at__isnull=True, due_at__date__lte=today).count(),
            }
        if has_feature(org, "posvenda"):
            body["warranties_active"] = org.garantias.filter(ends_on__gte=today).count()
        return Response(body)


class RelatoriosView(APIView):
    """?tipo=giro|vendedores|origens|estoque|vendas · ?from=&to= · ?export=csv"""

    permission_classes = [OrganizationPermission, PlanFeaturePermission]
    required_perm = "view"
    required_feature = "relatorios"

    def get(self, request):
        p = request.query_params
        today = timezone.localdate()
        try:
            start = date.fromisoformat(p["from"]) if p.get("from") else add_months(today.replace(day=1), -5)
            end = date.fromisoformat(p["to"]) if p.get("to") else today
        except ValueError:
            raise ValidationError({"from": "Data inválida (AAAA-MM-DD)."})
        orgs = _orgs(request)
        kind = p.get("tipo", "giro")
        builder = {
            "giro": self.giro,
            "vendedores": self.vendedores,
            "origens": self.origens,
            "estoque": self.estoque,
            "vendas": self.vendas,
        }.get(kind)
        if builder is None:
            raise ValidationError({"tipo": "Relatório inválido."})
        columns, rows = builder(orgs, start, end)
        if p.get("export") == "csv":
            resp = HttpResponse(content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="relatorio-{kind}-{start}-{end}.csv"'
            resp.write("﻿")
            writer = csv.writer(resp, delimiter=";")
            writer.writerow([c["label"] for c in columns])
            for r in rows:
                writer.writerow([self._csv(r.get(c["key"]), c.get("type")) for c in columns])
            return resp
        return Response({"columns": columns, "rows": rows, "from": start.isoformat(), "to": end.isoformat()})

    @staticmethod
    def _csv(value, typ):
        if value is None:
            return ""
        if typ == "money":
            return f"{value / 100:.2f}".replace(".", ",")
        return value

    def _sales(self, orgs, start, end):
        return Venda.objects.filter(organization_id__in=orgs, status=Venda.Status.FECHADA, closed_at__range=(start, end))

    def giro(self, orgs, start, end):
        rows = (
            self._sales(orgs, start, end)
            .values(marca=F("vehicle__marca"), modelo=F("vehicle__modelo"))
            .annotate(
                units=Count("id"),
                revenue=Sum("price_cents"),
                profit=Sum("profit_cents"),
                avg_days=Avg(F("closed_at") - F("vehicle__entry_date")),
            )
            .order_by("-units")
        )
        out = []
        for r in rows:
            avg = r["avg_days"]
            out.append(
                {
                    **r,
                    "avg_days": avg.days if hasattr(avg, "days") else avg,
                    "margin_pct": round(r["profit"] * 100 / r["revenue"], 1) if r["revenue"] else None,
                }
            )
        return (
            [
                {"key": "marca", "label": "Marca"},
                {"key": "modelo", "label": "Modelo"},
                {"key": "units", "label": "Vendidos"},
                {"key": "avg_days", "label": "Dias médios em estoque"},
                {"key": "revenue", "label": "Faturamento", "type": "money"},
                {"key": "profit", "label": "Lucro", "type": "money"},
                {"key": "margin_pct", "label": "Margem %"},
            ],
            out,
        )

    def vendedores(self, orgs, start, end):
        rows = (
            self._sales(orgs, start, end)
            .values(vendedor=F("seller__full_name"))
            .annotate(units=Count("id"), revenue=Sum("price_cents"), profit=Sum("profit_cents"), commission=Sum("commission_cents"))
            .order_by("-profit")
        )
        out = [
            {**r, "vendedor": r["vendedor"] or "Sem vendedor", "avg_profit": r["profit"] // r["units"] if r["units"] else 0} for r in rows
        ]
        return (
            [
                {"key": "vendedor", "label": "Vendedor"},
                {"key": "units", "label": "Vendas"},
                {"key": "revenue", "label": "Faturamento", "type": "money"},
                {"key": "profit", "label": "Lucro", "type": "money"},
                {"key": "avg_profit", "label": "Lucro médio por carro", "type": "money"},
                {"key": "commission", "label": "Comissões", "type": "money"},
            ],
            out,
        )

    def origens(self, orgs, start, end):
        leads = Lead.objects.filter(organization_id__in=orgs, created_at__date__range=(start, end))
        rows = leads.values("source").annotate(total=Count("id"), won=Count("id", filter=Q(stage=Lead.Stage.GANHO))).order_by("-total")
        labels = dict(Lead.Source.choices)
        out = [
            {
                "origem": labels.get(r["source"], r["source"]),
                "total": r["total"],
                "won": r["won"],
                "conversion_pct": round(r["won"] * 100 / r["total"], 1) if r["total"] else 0,
            }
            for r in rows
        ]
        return (
            [
                {"key": "origem", "label": "Origem"},
                {"key": "total", "label": "Leads"},
                {"key": "won", "label": "Vendas"},
                {"key": "conversion_pct", "label": "Conversão %"},
            ],
            out,
        )

    def estoque(self, orgs, start, end):
        today = timezone.localdate()
        out = []
        for v in (
            Vehicle.objects.filter(organization_id__in=orgs, status__in=Vehicle.ACTIVE).prefetch_related("costs").order_by("entry_date")
        ):
            cost = v.total_cost()
            out.append(
                {
                    "veiculo": v.title,
                    "placa": v.placa,
                    "situacao": v.get_status_display(),
                    "dias": (today - v.entry_date).days if v.entry_date else None,
                    "custo": cost,
                    "preco": v.price_cents,
                    "fipe": v.fipe_price_cents,
                    "lucro_previsto": v.price_cents - cost - v.consignor_payout(v.price_cents) if v.price_cents else None,
                }
            )
        return (
            [
                {"key": "veiculo", "label": "Veículo"},
                {"key": "placa", "label": "Placa"},
                {"key": "situacao", "label": "Situação"},
                {"key": "dias", "label": "Dias em estoque"},
                {"key": "custo", "label": "Custo total", "type": "money"},
                {"key": "preco", "label": "Preço anunciado", "type": "money"},
                {"key": "fipe", "label": "FIPE", "type": "money"},
                {"key": "lucro_previsto", "label": "Lucro previsto", "type": "money"},
            ],
            out,
        )

    def vendas(self, orgs, start, end):
        out = [
            {
                "data": v.closed_at.isoformat(),
                "veiculo": v.vehicle.title,
                "placa": v.vehicle.placa,
                "cliente": v.cliente.nome,
                "vendedor": v.seller.full_name if v.seller_id else "",
                "valor": v.price_cents,
                "custo": v.cost_cents,
                "lucro": v.profit_cents,
                "comissao": v.commission_cents,
            }
            for v in self._sales(orgs, start, end).select_related("vehicle", "cliente", "seller").order_by("closed_at")
        ]
        return (
            [
                {"key": "data", "label": "Data"},
                {"key": "veiculo", "label": "Veículo"},
                {"key": "placa", "label": "Placa"},
                {"key": "cliente", "label": "Cliente"},
                {"key": "vendedor", "label": "Vendedor"},
                {"key": "valor", "label": "Valor", "type": "money"},
                {"key": "custo", "label": "Custo", "type": "money"},
                {"key": "lucro", "label": "Lucro", "type": "money"},
                {"key": "comissao", "label": "Comissão", "type": "money"},
            ],
            out,
        )
