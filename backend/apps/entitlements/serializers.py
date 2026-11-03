from rest_framework import serializers

from .models import ServiceEntitlement, ServicePlan


class ServicePlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePlan
        fields = ("id", "service_code", "name", "package_type", "student_capacity", "duration_days", "price_minor", "currency", "description")


class ServiceEntitlementSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True, default="")
    is_current = serializers.BooleanField(read_only=True)

    class Meta:
        model = ServiceEntitlement
        fields = (
            "id", "license_id", "school", "school_name", "service_code", "plan", "plan_name",
            "package_type", "student_capacity", "starts_on", "expires_on", "status",
            "payment_reference", "offline_grace_days", "is_current", "created_at",
        )
        read_only_fields = ("id", "license_id", "school_name", "plan_name", "is_current", "created_at", "offline_grace_days", "signed_license")

    def validate(self, attrs):
        plan = attrs.get("plan")
        service_code = attrs.get("service_code") or (self.instance.service_code if self.instance else None)
        if plan and service_code and plan.service_code != service_code:
            raise serializers.ValidationError({"plan": "Select a plan for the same service."})
        capacity = attrs.get("student_capacity", self.instance.student_capacity if self.instance else None)
        if plan and capacity and capacity > plan.student_capacity:
            raise serializers.ValidationError({"student_capacity": "Capacity cannot exceed the selected plan."})
        starts_on = attrs.get("starts_on", self.instance.starts_on if self.instance else None)
        expires_on = attrs.get("expires_on", self.instance.expires_on if self.instance else None)
        if starts_on and expires_on and expires_on < starts_on:
            raise serializers.ValidationError({"expires_on": "Expiry date must be on or after the start date."})
        return attrs
