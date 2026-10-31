from rest_framework import serializers
from decimal import Decimal

from .models import CreditPackage, CreditPayment, CreditTransaction, ReportCardBilling, ReconciliationIssue


class CreditPackageSerializer(serializers.ModelSerializer):
    price_naira = serializers.SerializerMethodField()
    price_per_credit_naira = serializers.SerializerMethodField()

    class Meta:
        model = CreditPackage
        fields = ("id", "name", "credits", "price_minor", "price_naira", "price_per_credit_naira", "description")

    def get_price_naira(self, obj):
        return f"{Decimal(obj.price_minor) / Decimal(100):,.2f}"

    def get_price_per_credit_naira(self, obj):
        return f"{Decimal(obj.price_minor) / Decimal(100) / Decimal(obj.credits):,.2f}"


class CreditPaymentSerializer(serializers.ModelSerializer):
    amount_naira = serializers.SerializerMethodField()

    class Meta:
        model = CreditPayment
        fields = ("reference", "package_name", "credits", "amount_minor", "amount_naira", "currency", "status", "authorization_url", "created_at", "verified_at")

    def get_amount_naira(self, obj):
        return f"{obj.amount_minor / 100:,.2f}"


class CreditTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditTransaction
        fields = ("id", "kind", "amount", "description", "payment", "report_card_billing", "reference_key", "created_at")


class ReportCardBillingSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    session_name = serializers.CharField(source="academic_session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)

    class Meta:
        model = ReportCardBilling
        fields = ("id", "student", "student_name", "academic_session", "session_name", "term", "term_name", "report_card", "revision", "charged_at", "legacy_waived")

    def get_student_name(self, obj):
        return obj.student.get_full_name()


class PurchaseSerializer(serializers.Serializer):
    package = serializers.IntegerField(min_value=1)


class AdjustmentSerializer(serializers.Serializer):
    school = serializers.IntegerField(min_value=1)
    amount = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)
    reference_key = serializers.CharField(max_length=140)


class IssueResolutionSerializer(serializers.Serializer):
    resolution = serializers.CharField(max_length=500)


class ReconciliationIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationIssue
        fields = ("id", "school", "payment", "kind", "description", "provider_reference", "status", "resolution", "created_at", "resolved_at")
