import json
import ipaddress
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError


class PaystackProvider:
    base_url = "https://api.paystack.co"

    @property
    def secret_key(self):
        key = getattr(settings, "PAYSTACK_SECRET_KEY", "")
        if not key:
            raise ImproperlyConfigured("PAYSTACK_SECRET_KEY is required to initialize or verify Paystack payments.")
        return key

    def _request(self, method, path, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}", data=body, method=method,
            headers={"Authorization": f"Bearer {self.secret_key}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise ValidationError({"payment": "The payment provider could not be reached. Retry or wait for the provider notification."}) from exc
        if not result.get("status") or not isinstance(result.get("data"), dict):
            raise ValidationError({"payment": "The payment provider rejected the request."})
        return result["data"]

    def initialize(self, *, email, amount_minor, reference, callback_url):
        data = self._request("POST", "/transaction/initialize", {
            "email": email, "amount": amount_minor, "currency": "NGN",
            "reference": reference, "callback_url": callback_url,
        })
        if not data.get("authorization_url"):
            raise ValidationError({"payment": "The payment provider did not return a checkout URL."})
        return data

    def verify(self, reference):
        return self._request("GET", f"/transaction/verify/{quote(reference, safe='')}")


class FlutterwaveProvider:
    base_url = "https://api.flutterwave.com/v3"

    @property
    def secret_key(self):
        key = getattr(settings, "FLUTTERWAVE_SECRET_KEY", "")
        if not key:
            raise ImproperlyConfigured("FLUTTERWAVE_SECRET_KEY is required to initialize or verify Flutterwave payments.")
        return key

    def _request(self, method, path, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}", data=body, method=method,
            headers={"Authorization": f"Bearer {self.secret_key}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise ValidationError({"payment": "Flutterwave could not be reached. Retry or check the provider status."}) from exc
        if result.get("status") != "success" or not isinstance(result.get("data"), dict):
            raise ValidationError({"payment": "Flutterwave rejected the payment request."})
        return result["data"]

    def initialize(self, *, email, amount_minor, reference, callback_url, title="EDUstacked", description="Report-card credits"):
        data = self._request("POST", "/payments", {
            "tx_ref": reference, "amount": f"{Decimal(amount_minor) / Decimal(100):.2f}", "currency": "NGN",
            "redirect_url": callback_url, "customer": {"email": email},
            "customizations": {"title": title, "description": description},
        })
        if not data.get("link"):
            raise ValidationError({"payment": "Flutterwave did not return a checkout link."})
        return {"authorization_url": data["link"]}

    def verify(self, transaction_id):
        if not str(transaction_id).isdigit():
            raise ValidationError({"payment": "Flutterwave transaction ID is missing or invalid."})
        data = self._request("GET", f"/transactions/{quote(str(transaction_id), safe='')}/verify")
        data["reference"] = data.get("tx_ref")
        data["status"] = "success" if data.get("status") == "successful" else data.get("status")
        try:
            amount = Decimal(str(data.get("amount"))) * 100
            data["amount"] = int(amount) if amount.is_finite() and amount == amount.to_integral_value() else None
        except (InvalidOperation, TypeError, ValueError):
            data["amount"] = None
        return data


class BachsProvider:
    """Hosted Bachs checkout plus server-side checkout-session verification."""

    @property
    def base_url(self):
        return getattr(settings, "BACHS_API_BASE_URL", "https://sandbox-api.bachs.io/v1").rstrip("/")

    @property
    def api_key(self):
        key = getattr(settings, "BACHS_API_KEY", "")
        if not key:
            raise ImproperlyConfigured("BACHS_API_KEY is required to initialize or verify Bachs payments.")
        return key

    def _request(self, method, path, payload=None, idempotency_key="", headers=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if idempotency_key:
            request_headers["Idempotency-Key"] = idempotency_key
        request_headers.update(headers or {})
        request = Request(f"{self.base_url}{path}", data=body, method=method, headers=request_headers)
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            if isinstance(exc, HTTPError):
                try:
                    detail = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    detail = ""
                raise ValidationError({"payment": f"Bachs rejected the checkout request (HTTP {exc.code}). Check sandbox key, API permissions, and request fields. {detail}"}) from exc
            raise ValidationError({"payment": "Bachs could not be reached. Check the API URL and try again."}) from exc
        if not isinstance(result, dict):
            raise ValidationError({"payment": "Bachs returned an invalid response."})
        return result

    def _public_return_url(self, callback_url, reference):
        candidates = (callback_url, getattr(settings, "BACHS_RETURN_URL", ""))
        for candidate in candidates:
            parsed_return = urlsplit(str(candidate or "").strip())
            hostname = (parsed_return.hostname or "").lower().rstrip(".")
            try:
                public_host = ipaddress.ip_address(hostname).is_global
            except ValueError:
                public_host = bool(hostname) and hostname != "localhost" and not hostname.endswith((".localhost", ".local"))
            if parsed_return.scheme == "https" and public_host:
                query = dict(parse_qsl(parsed_return.query, keep_blank_values=True))
                query["reference"] = reference
                return urlunsplit((parsed_return.scheme, parsed_return.netloc, parsed_return.path, urlencode(query), parsed_return.fragment))
        # Bachs rejects localhost/private callback URLs, including in sandbox.
        return ""

    def initialize(self, *, email, amount_minor, reference, callback_url, connected_account_id="", channels=None):
        amount = f"{Decimal(amount_minor) / Decimal(100):.2f}"
        return_url = self._public_return_url(callback_url, reference)
        payload = {
            "pricing": {"currency": "NGN", "amount": amount},
            "customer": {"email": email},
            "reference": reference,
            "metadata": {"edustacked_payment_reference": reference},
        }
        if channels:
            bachs_channels = {"card": "NGN_CARD", "bank_transfer": "NGN_BANK_TRANSFER"}
            payload["payment_method_types"] = [bachs_channels[value] for value in channels if value in bachs_channels]
        if return_url:
            payload.update({"success_url": return_url, "cancel_url": return_url})
        request_headers = {"X-Account-Id": connected_account_id} if connected_account_id else None
        data = self._request("POST", "/checkout-sessions", payload, idempotency_key=reference, headers=request_headers)
        if not data.get("checkout_url", "").startswith("https://") or not data.get("checkout_id"):
            raise ValidationError({"payment": "Bachs did not return a valid hosted checkout."})
        return {"authorization_url": data["checkout_url"], "checkout_id": data["checkout_id"]}

    def verify(self, checkout_id, connected_account_id=""):
        if not checkout_id:
            raise ValidationError({"payment": "Bachs checkout ID is missing. Use the verification link or wait for the payment notification."})
        request_headers = {"X-Account-Id": connected_account_id} if connected_account_id else None
        data = self._request("GET", f"/checkout-sessions/{quote(str(checkout_id), safe='')}", headers=request_headers)
        if data.get("checkout_id") != str(checkout_id):
            raise ValidationError({"payment": "Bachs returned a different checkout than expected."})
        checkout_status = str(data.get("status", "")).lower()
        payment_status = str(data.get("payment_status", "")).lower()
        if checkout_status == "completed" and payment_status in {"succeeded", "paid"}:
            result_status = "success"
        elif checkout_status in {"expired", "cancelled"} or payment_status in {"failed", "canceled"}:
            result_status = "failed"
        else:
            result_status = "pending"
        try:
            amount_value = Decimal(str(data.get("amount"))) * 100
            amount_minor = int(amount_value) if amount_value.is_finite() and amount_value == amount_value.to_integral_value() else None
        except (InvalidOperation, TypeError, ValueError):
            amount_minor = None
        charge = data.get("charge")
        if not isinstance(charge, dict):
            charge = {}
        customer = data.get("customer") or data.get("customer_details") or {}
        if not isinstance(customer, dict):
            customer = {}
        payment_method = str(data.get("payment_method") or "").strip().lower().replace(" ", "_")
        channel = {
            "card": "card", "ngn_card": "card",
            "bank_transfer": "bank_transfer", "ngn_bank_transfer": "bank_transfer",
        }.get(payment_method, payment_method)
        return {
            "id": charge.get("id") or charge.get("payment_id") or data.get("checkout_id"),
            "reference": data.get("reference"),
            "status": result_status,
            "amount": amount_minor,
            "currency": data.get("currency"),
            "customer": customer,
            "channel": channel,
        }

    def connect_capabilities(self):
        account = self._request("GET", "/accounts/me")
        return set(account.get("enabled_capabilities") or [])

    def create_connected_school_account(self, *, school_name, contact_email, entity_type):
        if "connect" not in self.connect_capabilities():
            raise ValidationError({"provider": "Bachs Connect is not enabled for EDUstacked yet. Contact Bachs to activate Connect before connecting school fee accounts."})
        if entity_type not in {"individual", "company"}:
            raise ValidationError({"entity_type": "Choose whether the school account is an individual or registered company."})
        if not contact_email:
            raise ValidationError({"contact_email": "Add the school owner or financial representative’s own email before starting Bachs onboarding."})
        account = self._request("POST", "/accounts", {
            "contact_email": contact_email,
            "display_name": school_name,
            "country": "NG",
            "entity_type": entity_type,
            "configuration": {
                "merchant": {"capabilities": {
                    "ngn_card_collection": {"requested": True},
                    "bank_transfer": {"requested": True},
                }},
                "recipient": {"capabilities": {"payouts": {"requested": True}}},
            },
        })
        account_id = str(account.get("id") or "")
        if not account_id:
            raise ValidationError({"provider": "Bachs did not return the school account ID. Try again or contact EDUstacked support."})
        return {"account_id": account_id}

    def create_connected_account_link(self, account_id, *, return_url):
        data = self._request("POST", f"/accounts/{quote(str(account_id), safe='')}/account-links", {
            "type": "onboarding", "refresh_url": return_url, "return_url": return_url,
        })
        onboarding_url = str(data.get("url") or "")
        if not onboarding_url.startswith("https://"):
            raise ValidationError({"provider": "Bachs did not return a secure school-onboarding link. Try again or contact EDUstacked support."})
        return {"account_id": str(account_id), "onboarding_url": onboarding_url}

    def connected_account_capabilities(self, account_id):
        data = self._request("GET", f"/accounts/{quote(str(account_id), safe='')}/capabilities")
        items = data.get("items") or []
        return {str(item.get("name")): str(item.get("status")) for item in items if isinstance(item, dict)}
