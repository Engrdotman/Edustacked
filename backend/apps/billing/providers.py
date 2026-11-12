import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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

    def initialize(self, *, email, amount_minor, reference, callback_url):
        data = self._request("POST", "/payments", {
            "tx_ref": reference, "amount": f"{amount_minor / 100:.2f}", "currency": "NGN",
            "redirect_url": callback_url, "customer": {"email": email},
            "customizations": {"title": "EDUstacked", "description": "Report-card credits"},
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
            data["amount"] = round(float(data.get("amount")) * 100)
        except (TypeError, ValueError):
            data["amount"] = None
        return data
