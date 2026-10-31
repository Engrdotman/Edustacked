# EDUstacked report-card credits and billing

Module 10 adds one-time report-card credit purchases. It does not add subscriptions.

## Credit policy

- One credit is consumed on the first successful finalization for a unique school, student, session, and term.
- Drafts, review, approval, preview, download, and reprint are free. Correction revisions stay within the existing billable period and consume no additional credit. A new term/session is a new period.
- Finalization, the unique billable-period record, cached balance update, and immutable ledger debit run in one database transaction. PostgreSQL row locks on the school serialize balance changes; database uniqueness constraints guard duplicate billing periods and ledger references.
- Failed finalization writes no debit. Insufficient credits leaves an approved card available for later publication.
- A data migration grandfathered each existing finalized student/session/term as `legacy_waived=true`, without retroactive debit or balance changes.

## Packages and provider setup

Migration `0003_seed_credit_packages` creates the three active packages below. Prices are stored in kobo, and the billing screen shows both total and per-credit prices. Existing package rows outside these three are deactivated for new checkout, not deleted; historical payments and package references remain intact.

| Package | Credits | Price per credit | Total |
| --- | ---: | ---: | ---: |
| Starter | 100 | ₦300 | ₦30,000 |
| Growth | 300 | ₦150 | ₦45,000 |
| School | 500 | ₦100 | ₦50,000 |

The 300-credit rate is set to ₦150 so its total stays below the 500-credit package, while maintaining the larger-volume discount. Platform administrators can manage descriptions and active status in Django Admin. The server reads price and quantity from the package row; clients can submit only a package id.

Set `PAYSTACK_SECRET_KEY` in `backend/.env` or the deployment secret manager. Keep it server-side. The API initializes checkout in NGN kobo with an internal unique reference, then redirects to the returned Paystack authorization URL. A browser callback alone never grants credits. Callback verification and signed webhook events converge on the same idempotent fulfillment service.

Configure the public HTTPS webhook in Paystack's test/live dashboard:

```text
https://<api-host>/api/v1/billing/paystack/webhook/
```

The endpoint validates `x-paystack-signature` as HMAC-SHA512 over the raw body. Paystack's official docs cover [transaction initialization](https://paystack.com/docs/api/transaction/), [server-side verification](https://paystack.com/docs/payments/verify-payments/), and [webhook verification](https://paystack.com/docs/payments/webhooks/). Configure `FRONTEND_BASE_URL` to the HTTPS frontend origin. The callback route is `/app/billing?reference=<reference>`.

## APIs

School APIs use authentication and the selected authorized school in `X-School-ID`. School admins and accountants may view billing and purchase credits. Teachers, school managers, receptionists, and legacy members have no billing access. Platform manual adjustments and reconciliation issue resolution require a Django superuser.

| Endpoint | Purpose |
| --- | --- |
| `GET billing/credits/` | Own school's balance and credit rule |
| `GET billing/packages/` | Active packages |
| `POST billing/purchases/` | Initialize checkout using a package id |
| `GET billing/payments/` | Paginated own-school payment history |
| `GET/POST billing/payments/{reference}/` | Read status / verify a pending payment with Paystack |
| `GET billing/transactions/` | Paginated append-only credit ledger |
| `GET billing/report-card-records/` | Paginated charged and grandfathered periods |
| `POST billing/paystack/webhook/` | Public signed Paystack event receiver |
| `POST platform/billing/adjustments/` | Superuser adjustment with signed amount, reason, and unique reference |
| `GET platform/billing/issues/` | Open reversal/mismatch review issues |
| `POST platform/billing/issues/{id}/resolve/` | Superuser resolution note; does not change a balance |

Payment serializers omit provider payloads and access secrets. Ledger rows are not editable/deletable through model or admin interfaces. Cached balances update in the same transaction as each ledger movement.

## Failures, reversals, and reconciliation

Pending, failed, and abandoned payments grant no credits. Unique internal references and ledger constraints make duplicate webhooks and verification retries idempotent. A processed refund marks the payment reversed; refund and dispute notifications create reconciliation issues. Credits are not automatically removed: no refund/chargeback business policy is approved, and credits may already have been spent. A platform superuser reviews provider evidence and the balance, records any approved adjustment through the audited adjustment API, and adds a resolution note. Never delete ledger history or directly edit the cached balance.

## Local development and verification

1. Copy `backend/.env.example` to `backend/.env`; add a Paystack test secret only when testing checkout.
2. Create active package rows in Django Admin.
3. Apply migrations without resetting data: `.venv\Scripts\python.exe backend\manage.py migrate`.
4. Run mocked tests: `.venv\Scripts\python.exe backend\manage.py test apps.billing.tests`, then run the full Module 1–10 regression suite.

Tests mock provider requests and never make charges. Real checkout/webhook verification needs valid test credentials and a publicly reachable HTTPS webhook. Local development uses SQLite. PostgreSQL row locking and uniqueness provide production serialization; PostgreSQL concurrency has not been exercised in this local environment.
