# CBT Entitlements and Payment Fulfillment

## Current State

- ✅ Report-card credit Paystack flow works (purchase credits → store in billing DB)
- ✅ CBT app exists with models, serializers, views
- ✅ Entitlements app exists to track service access
- ❌ **CBT entitlements are NOT purchased or activated via Paystack**

## What Is Missing

The payment flow ends after Paystack credit purchase:

```
Paystack → Credit recorded in billing → ??? → No CBT entitlement created
```

**Paystack callback does NOT:**
- Check if payment was for CBT license (no product distinction in current billing)
- Create/activate CBT service entitlements
- Notify the school that CBT is now available

## Why This Matters

If you enable CBT package sales now:
- Schools pay for Offline CBT
- Payment appears to succeed
- CBT features remain locked → school complaints
- Support team has no way to activate manually
- Refund process is manual and error-prone

## Required Implementation Before CBT Sales

### 1. Enhance Billing Models

**Current issue:** Billing doesn't track what was purchased (report cards, CBT, etc.)

```python
# backend/apps/billing/models.py → Add product type
class CreditPackage(models.Model):
    product_type = models.CharField(
        max_length=20,
        choices=[
            ('report_cards', 'Report Card Credits'),
            ('cbt_license', 'Offline CBT License'),
        ],
        default='report_cards'
    )
    credit_quantity = models.PositiveIntegerField()  # e.g., "100 report cards" or "500 students"
```

### 2. Implement Paystack Webhook Fulfillment

**Current Paystack flow location:** `backend/apps/billing/views.py` → `PaystackWebhookView`

**Add fulfillment logic:**
```python
async def handle_payment_success(charge):
    school_id = charge['metadata']['school_id']
    product_type = charge['metadata']['product_type']
    
    if product_type == 'cbt_license':
        # Create CBT entitlement
        school = School.objects.get(id=school_id)
        entitlement = ServiceEntitlement.objects.create(
            school=school,
            service_code='offline_cbt',
            is_current=True,
            activated_at=now(),
            expires_at=now() + timedelta(days=365),
        )
        # Notify school
        send_email(school, f"CBT license activated for 1 year")
    
    elif product_type == 'report_cards':
        # Existing logic: add credits
        ...
```

### 3. Add Manual Entitlement Activation Endpoint

For admin/support to activate CBT when needed:

```python
# backend/apps/entitlements/views.py
class ManualEntitlementActivationView(generics.CreateAPIView):
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request):
        school_id = request.data['school_id']
        service_code = request.data['service_code']  # 'offline_cbt'
        
        school = School.objects.get(id=school_id)
        entitlement, created = ServiceEntitlement.objects.update_or_create(
            school=school,
            service_code=service_code,
            defaults={
                'is_current': True,
                'activated_at': now(),
                'expires_at': now() + timedelta(days=365),
            }
        )
        return Response({'activated': True, 'entitlement_id': entitlement.id})
```

### 4. Add CBT License Duration and Renewal

```python
# backend/apps/entitlements/models.py
class ServiceEntitlement(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    service_code = models.CharField(max_length=50)
    is_current = models.BooleanField(default=False)
    activated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    @property
    def days_remaining(self):
        return (self.expires_at - now()).days
    
    @property
    def is_expired(self):
        return now() > self.expires_at
```

### 5. Update CBT Exam Assignment to Check Entitlement

```python
# backend/apps/cbt/views.py → ExamListCreateView
def create(self, request, *args, **kwargs):
    # Check school has active CBT entitlement
    entitlement = ServiceEntitlement.objects.filter(
        school=self.school,
        service_code='offline_cbt',
        is_current=True,
        expires_at__gt=now(),
    ).first()
    
    if not entitlement:
        raise PermissionDenied("CBT license is not active or has expired")
    
    return super().create(request, *args, **kwargs)
```

### 6. Add CBT License Expiry Warnings

```python
# background task or cron job
@periodic_task(run_every=crontab(hour=9, minute=0))
def notify_expiring_cbt_licenses():
    expiring_soon = ServiceEntitlement.objects.filter(
        service_code='offline_cbt',
        is_current=True,
        expires_at__lte=now() + timedelta(days=14),
        expires_at__gt=now(),
    )
    for entitlement in expiring_soon:
        send_email(
            entitlement.school,
            f"Your Offline CBT license expires in {entitlement.days_remaining} days"
        )
```

## Implementation Timeline

1. **Week 1:** Enhance billing models, add product_type to CreditPackage
2. **Week 2:** Implement Paystack webhook fulfillment logic
3. **Week 3:** Add manual activation endpoint for support
4. **Week 4:** Update CBT views to check entitlements, add expiry warnings
5. **Week 5:** End-to-end testing: Paystack test payment → CBT activation
6. **Week 6:** QA and deployment to staging

## Testing Checklist

- [ ] Create Paystack test charge with `product_type: 'cbt_license'`
- [ ] Webhook fires and creates ServiceEntitlement
- [ ] School can now create and assign CBT exams
- [ ] CBT expires after configured duration
- [ ] Expiry warnings send 14 days before expiration
- [ ] Manual activation endpoint works (admin only)
- [ ] School cannot activate its own CBT (permission denied)

## Before Going Live

- [ ] CBT fulfillment tests pass in CI
- [ ] Paystack test mode works end-to-end
- [ ] Support team trained on manual activation
- [ ] Legal/commercial decides: CBT license pricing and duration (1 year? 1 month?)
- [ ] Revenue recognition: when should payment be recorded? (at purchase or at activation?)

## DO NOT SELL CBT UNTIL THIS IS COMPLETE

Current state is sufficient for internal testing and demo purposes. Selling CBT licenses now will result in:
- Schools unable to use purchased licenses
- Support burden for manual activation requests
- Refund requests and credibility loss
- Potential revenue disputes with Paystack

**Recommendation:** Block CBT package purchase in frontend until this fulfillment is implemented. Use feature flags if needed:

```javascript
// frontend/src/pages/BillingPage.jsx
const CBT_PACKAGES_AVAILABLE = false;  // Set to true after fulfillment is live

if (CBT_PACKAGES_AVAILABLE) {
  // Show CBT packages
}
```
