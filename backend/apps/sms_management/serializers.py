from rest_framework import serializers

from .models import SMSBundle, SMSMessageBatch, SMSMessageLog, SMSPlatformConfiguration, SMSPurchase, SMSWalletTransaction


class SMSBundleSerializer(serializers.ModelSerializer):
    unit_price_minor = serializers.SerializerMethodField()

    class Meta:
        model = SMSBundle
        fields = ("id", "name", "credits", "price_minor", "unit_price_minor", "is_active", "display_order")

    def get_unit_price_minor(self, obj):
        return obj.price_minor // obj.credits if obj.credits else 0


class SMSMessageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSMessageLog
        fields = ("id", "phone", "message", "segments", "free_credits", "paid_credits", "status", "provider_message_id", "last_error", "sent_at", "delivered_at", "created_at")


class SMSBatchSerializer(serializers.ModelSerializer):
    messages = SMSMessageLogSerializer(many=True, read_only=True)

    class Meta:
        model = SMSMessageBatch
        fields = ("id", "status", "recipient_count", "total_segments", "free_credits", "paid_credits", "messages", "created_at")


class SMSPurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSPurchase
        fields = ("id", "bundle_name", "credits", "amount_minor", "currency", "provider", "reference", "authorization_url", "status", "created_at", "paid_at")


class SMSWalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSWalletTransaction
        fields = ("id", "kind", "credits", "description", "reference_key", "created_at", "metadata")


class SMSPlatformConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSPlatformConfiguration
        fields = ("monthly_free_allowance", "provider_cost_per_credit_minor", "low_balance_threshold", "updated_at")

    def validate_monthly_free_allowance(self, value):
        if value > 10000:
            raise serializers.ValidationError("Monthly free allowance cannot exceed 10,000 credits.")
        return value

    def validate_provider_cost_per_credit_minor(self, value):
        if value <= 0:
            raise serializers.ValidationError("Provider cost must be greater than zero.")
        return value


class SMSBundleManageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSBundle
        fields = ("id", "name", "credits", "price_minor", "is_active", "display_order")
        read_only_fields = ("id",)

    def validate(self, attrs):
        credits = attrs.get("credits", getattr(self.instance, "credits", 0))
        price = attrs.get("price_minor", getattr(self.instance, "price_minor", 0))
        if credits <= 0:
            raise serializers.ValidationError({"credits": "Enter a bundle with at least one SMS credit."})
        if price <= 0:
            raise serializers.ValidationError({"price_minor": "Enter a price greater than zero, in kobo."})
        return attrs


class SMSSendSerializer(serializers.Serializer):
    recipients = serializers.ListField(child=serializers.CharField(max_length=32), min_length=1, max_length=200)
    message = serializers.CharField(max_length=5000, trim_whitespace=True)

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("Enter a message before sending.")
        return value.strip()


class SMSPurchaseInitSerializer(serializers.Serializer):
    bundle = serializers.IntegerField(min_value=1)
    provider = serializers.ChoiceField(choices=("flutterwave", "paystack"), default="flutterwave")


class SMSDateRangeSerializer(serializers.Serializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs.get("start") and attrs.get("end") and attrs["start"] > attrs["end"]:
            raise serializers.ValidationError({"end": "End date must be on or after start date."})
        return attrs
