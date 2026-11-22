# EDUstacked SMS wallet and monitoring

## School SMS

School owners, administrators, principals, and school managers can open **SMS & messaging** from their school dashboard. The page shows the monthly free balance, purchased credits, message segments, recent messages, and (for owners, administrators, and principals) wallet activity and bundle checkout.

Each school receives 50 free SMS segments each calendar month. Unused free credits expire at month end. The free balance is consumed before purchased credits. Purchased credits remain available until used. A long SMS may count as multiple segments; GSM text allows up to 160 characters in a single segment, while Unicode text allows up to 70. Multipart messages have lower per-part limits.

The initial bundles are Basic (500 credits for ₦3,750), Growth (2,000 for ₦14,000), and Enterprise (5,000 for ₦32,500). The platform owner can change their names, amounts, prices, and availability in **Platform administration → SMS management**. Prices and provider costs are stored in kobo.

The school selects Flutterwave or Paystack for checkout. Credits are added only after the backend verifies the provider payment, either from the provider notification or the school returning to the SMS page. A browser success message alone never adds credits.

## Platform owner monitoring

Open `/platform/sms` while signed in as a platform superuser. Date filters control the analytics range. Bundle purchases represent verified cash collected; unconsumed prepaid value is reported as an outstanding liability; SMS expenditure and gross margin are reported separately. Provider charges use Termii-reported costs when available and configured estimates otherwise. A platform owner may pause or resume SMS for one school without suspending the school's workspace.

## Railway and Termii setup

Set these values only on the backend service (Railway), never in the frontend:

- `TERMII_API_KEY`: Termii API token.
- `TERMII_SENDER_ID`: Termii-approved sender ID.
- `TERMII_BASE_URL`: your account's Termii API base URL; defaults to `https://api.ng.termii.com`.
- `TERMII_CHANNEL`: usually `generic`, unless Termii enables a different channel for your account.
- `TERMII_WEBHOOK_SECRET`: optional secret configured for Termii signed delivery callbacks.
- `PAYSTACK_SECRET_KEY` and `PAYSTACK_WEBHOOK_SECRET`, if Paystack checkout is enabled.
- `FLUTTERWAVE_SECRET_KEY` and `FLUTTERWAVE_WEBHOOK_SECRET`, if Flutterwave checkout is enabled.
- `FRONTEND_BASE_URL`: public HTTPS frontend used for payment returns.

Configure the Termii delivery callback URL as `https://your-api-host/api/v1/sms/webhooks/termii/` and use the same webhook secret in Railway and Termii. The handler verifies `X-Termii-Signature`, tracks delivery state and provider cost, and refunds credits only for explicit final failure statuses. A timeout or delayed delivery callback does not trigger an automatic refund.

Set payment-provider webhook URLs to `https://your-api-host/api/v1/sms/webhooks/payment/paystack/` or `https://your-api-host/api/v1/sms/webhooks/payment/flutterwave/`, and set each provider's matching webhook secret in Railway. The confirmation endpoint remains available if a provider callback is delayed.

## Monthly allowance scheduling

The SMS page creates the current month allowance on first use. For schools that have not opened the SMS page, configure a monthly Railway cron/scheduled command to run:

```text
python manage.py issue_sms_monthly_allowances
```

The command may safely run more than once per month. The unique school/month constraint prevents duplicate allowance rows. No Redis or Celery worker is required for monthly allowances. Provider delivery updates use webhooks; automated reconciliation of ambiguous Termii timeouts is not yet scheduled and should be reviewed from the message records before any manual credit adjustment.

## Safety notes

- School identity is resolved from the signed-in user's authorized school membership and `X-School-ID`; request JSON cannot select another school's wallet.
- SMS send requests require idempotency keys and are throttled.
- Fee receipt/OTP messages also pass through the central SMS wallet sender.
- Keep all provider tokens and signing secrets in Railway backend variables.
