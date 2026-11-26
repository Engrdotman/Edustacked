"""Provider operations for school-owned fee collection accounts."""
import json
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError

from apps.billing.providers import BachsProvider


class SchoolPaymentProvider:
    provider = ""

    def _request(self, method, path, payload=None):
        raise NotImplementedError

    def banks(self):
        raise NotImplementedError

    def connect_account(self, *, bank_code, account_number, business_name, phone, business_email=""):
        raise NotImplementedError

    def initialize(self, *, email, amount_minor, reference, callback_url, subaccount_id, channels=None):
        raise NotImplementedError

    def verify(self, reference_or_id):
        raise NotImplementedError


class PaystackSchoolProvider(SchoolPaymentProvider):
    provider = "paystack"
    base_url = "https://api.paystack.co"

    @property
    def secret(self):
        key = getattr(settings, "PAYSTACK_SECRET_KEY", "")
        if not key:
            raise ImproperlyConfigured("Paystack is not configured on the EDUstacked server.")
        return key

    def _request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(f"{self.base_url}{path}", data=body, method=method, headers={
            "Authorization": f"Bearer {self.secret}", "Content-Type": "application/json",
        })
        try:
            with urlopen(request, timeout=18) as response:
                result = json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise ValidationError({"payment": "Paystack could not complete the request. Check the bank details or retry shortly."}) from exc
        if not isinstance(result, dict) or not result.get("status"):
            raise ValidationError({"payment": "Paystack rejected the request. Check the account details and try again."})
        return result.get("data") or {}

    def banks(self):
        return self._request("GET", "/bank?country=nigeria&perPage=200")

    def connect_account(self, *, bank_code, account_number, business_name, phone, business_email=""):
        resolved = self._request("GET", f"/bank/resolve?account_number={quote(account_number)}&bank_code={quote(bank_code)}")
        account_name = resolved.get("account_name", "").strip()
        if not account_name:
            raise ValidationError({"account_number": "Paystack could not verify this account. Confirm the bank and account number."})
        account = self._request("POST", "/subaccount", {
            "business_name": business_name, "settlement_bank": bank_code,
            "account_number": account_number, "percentage_charge": 0,
            **({"primary_contact_email": business_email} if business_email else {}),
        })
        if not account.get("subaccount_code"):
            raise ValidationError({"payment": "The account was verified, but Paystack did not return a collection account. Contact support before enabling online payments."})
        return {"account_name": account_name, "provider_account_id": account["subaccount_code"]}

    def initialize(self, *, email, amount_minor, reference, callback_url, subaccount_id, channels=None):
        payload = {
            "email": email, "amount": amount_minor, "currency": "NGN", "reference": reference,
            "callback_url": callback_url, "subaccount": subaccount_id, "bearer": "subaccount",
            "metadata": {"edustacked_reference": reference},
        }
        if channels:
            payload["channels"] = channels
        return self._request("POST", "/transaction/initialize", payload)

    def verify(self, reference_or_id):
        return self._request("GET", f"/transaction/verify/{quote(str(reference_or_id), safe='')}")


class FlutterwaveSchoolProvider(SchoolPaymentProvider):
    provider = "flutterwave"
    base_url = "https://api.flutterwave.com/v3"

    @property
    def secret(self):
        key = getattr(settings, "FLUTTERWAVE_SECRET_KEY", "")
        if not key:
            raise ImproperlyConfigured("Flutterwave is not configured on the EDUstacked server.")
        return key

    def _request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(f"{self.base_url}{path}", data=body, method=method, headers={
            "Authorization": f"Bearer {self.secret}", "Content-Type": "application/json",
        })
        try:
            with urlopen(request, timeout=18) as response:
                result = json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise ValidationError({"payment": "Flutterwave could not complete the request. Check the bank details or retry shortly."}) from exc
        if not isinstance(result, dict) or result.get("status") != "success":
            raise ValidationError({"payment": "Flutterwave rejected the request. Check the account details and try again."})
        return result.get("data") or {}

    def banks(self):
        return self._request("GET", "/banks/NG")

    def connect_account(self, *, bank_code, account_number, business_name, phone, business_email=""):
        if not phone:
            raise ValidationError({"business_mobile": "Add a school contact phone number before connecting a Flutterwave account."})
        resolved = self._request("POST", "/accounts/resolve", {"account_number": account_number, "account_bank": bank_code})
        account_name = resolved.get("account_name", "").strip()
        if not account_name:
            raise ValidationError({"account_number": "Flutterwave could not verify this account. Confirm the bank and account number."})
        account = self._request("POST", "/subaccounts", {
            "account_bank": bank_code, "account_number": account_number,
            "business_name": business_name[:100], "business_mobile": phone[:20],
            "country": "NG", "split_type": "percentage", "split_value": 0.0,
            **({"business_email": business_email} if business_email else {}),
        })
        account_id = account.get("subaccount_id")
        if not account_id:
            raise ValidationError({"payment": "The account was verified, but Flutterwave did not return a collection account. Contact support before enabling online payments."})
        return {"account_name": account_name, "provider_account_id": account_id}

    def initialize(self, *, email, amount_minor, reference, callback_url, subaccount_id, channels=None):
        payload = {
            "tx_ref": reference, "amount": f"{Decimal(amount_minor) / 100:.2f}", "currency": "NGN",
            "redirect_url": callback_url, "customer": {"email": email},
            "subaccounts": [{"id": subaccount_id}],
            "customizations": {"title": "School fees", "description": "School fee payment"},
            "meta": {"edustacked_reference": reference},
        }
        if channels:
            flutterwave_channels = {"bank_transfer": "banktransfer"}
            payload["payment_options"] = ", ".join(flutterwave_channels.get(channel, channel) for channel in channels)
        data = self._request("POST", "/payments", payload)
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


def provider_for(name):
    if name == "paystack":
        return PaystackSchoolProvider()
    if name == "flutterwave":
        return FlutterwaveSchoolProvider()
    if name == "bachs":
        return BachsProvider()
    raise ValidationError({"provider": "Choose Paystack, Flutterwave, or Bachs."})
