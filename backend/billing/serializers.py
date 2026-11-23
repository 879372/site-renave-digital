from rest_framework import serializers

from .models import Feature, Invoice, InvoiceItem, Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    feature_labels = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            "code",
            "name",
            "monthly_price_cents",
            "annual_price_cents",
            "vehicle_limit",
            "user_limit",
            "plate_queries_included",
            "features",
            "feature_labels",
            "postpaid",
            "extra_store_price_cents",
        ]

    def get_feature_labels(self, obj):
        return [Feature(f).label for f in obj.features if f in Feature.values]


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ["kind", "description", "quantity", "total_cents"]


class InvoiceSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    target_plan = serializers.SlugRelatedField(slug_field="code", read_only=True)
    items = InvoiceItemSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "kind",
            "kind_display",
            "status",
            "status_display",
            "total_cents",
            "due_date",
            "target_plan",
            "target_cycle",
            "payment_url",
            "paid_at",
            "created_at",
            "items",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    scheduled_plan = serializers.SlugRelatedField(slug_field="code", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "plan",
            "status",
            "status_display",
            "cycle",
            "trial_ends_at",
            "paid_through",
            "next_billing_date",
            "scheduled_plan",
            "scheduled_cycle",
        ]


class ChangePlanSerializer(serializers.Serializer):
    plan = serializers.SlugRelatedField(slug_field="code", queryset=Plan.objects.filter(is_active=True))
    cycle = serializers.ChoiceField(choices=Subscription.Cycle.choices, default=Subscription.Cycle.MONTHLY)
