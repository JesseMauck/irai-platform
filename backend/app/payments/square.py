"""Square Subscriptions client (REST, no SDK).

Flow
  1. One-time setup: `python -m app.payments.setup_square` creates a SUBSCRIPTION_PLAN in the Square catalog
     with four variations (Essential/Pro × monthly/annual) and prints their IDs for the
     SQUARE_PLAN_<PLAN>_<INTERVAL> variables.
  2. Checkout: CreatePaymentLink with checkout_options.subscription_plan_id = the plan *variation* ID returns a
     Square-hosted page; paying there creates the subscription in Square.
  3. Square sends subscription.created / subscription.updated webhooks, signed with
     base64(HMAC-SHA256(signature_key, notification_url + raw_body)) in x-square-hmacsha256-signature.
  4. Cancel: POST /v2/subscriptions/{id}/cancel (takes effect at the end of the paid period).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

SQUARE_VERSION = "2025-10-16"
BASES = {"production": "https://connect.squareup.com", "sandbox": "https://connect.squareupsandbox.com"}


class SquareError(RuntimeError):
    pass


@dataclass(frozen=True)
class SquareConfig:
    access_token: str
    environment: str
    location_id: str
    webhook_signature_key: str
    webhook_url: str
    plan_variations: dict[str, str]  # "essential_monthly" -> variation id

    @classmethod
    def from_env(cls) -> SquareConfig:
        env = os.environ.get
        return cls(
            access_token=env("SQUARE_ACCESS_TOKEN", ""),
            environment=env("SQUARE_ENVIRONMENT", "sandbox").lower(),
            location_id=env("SQUARE_LOCATION_ID", ""),
            webhook_signature_key=env("SQUARE_WEBHOOK_SIGNATURE_KEY", ""),
            webhook_url=env("SQUARE_WEBHOOK_URL", ""),
            plan_variations={k: env(f"SQUARE_PLAN_{k.upper()}", "") for k in
                             ("essential_monthly", "essential_annual", "pro_monthly", "pro_annual")},
        )

    @property
    def enabled(self) -> bool:
        return bool(self.access_token and self.location_id)

    def plan_for_variation(self, variation_id: str | None) -> tuple[str, str] | None:
        for key, vid in self.plan_variations.items():
            if vid and vid == variation_id:
                plan, interval = key.split("_")
                return plan, interval
        return None


def verify_signature(body: bytes, signature: str, key: str, notification_url: str) -> bool:
    if not (signature and key and notification_url):
        return False
    digest = hmac.new(key.encode(), notification_url.encode() + body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


class SquareClient:
    def __init__(self, cfg: SquareConfig, client: httpx.Client | None = None):
        self.cfg = cfg
        self.http = client or httpx.Client(timeout=20)

    def _req(self, method: str, path: str, json: dict | None = None) -> dict[str, Any]:
        r = self.http.request(method, BASES.get(self.cfg.environment, BASES["sandbox"]) + path, json=json, headers={
            "Authorization": f"Bearer {self.cfg.access_token}", "Square-Version": SQUARE_VERSION,
            "Content-Type": "application/json"})
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code >= 400 or data.get("errors"):
            errs = data.get("errors") or [{"detail": r.text[:200]}]
            raise SquareError("; ".join(e.get("detail") or e.get("code", "error") for e in errs))
        return data

    # checkout ------------------------------------------------------------------------------------
    def create_subscription_link(self, *, variation_id: str, name: str, amount_cents: int, buyer_email: str,
                                 redirect_url: str, reference: str) -> dict[str, Any]:
        body = {
            "idempotency_key": str(uuid.uuid4()),
            "quick_pay": {"name": name, "price_money": {"amount": amount_cents, "currency": "USD"},
                          "location_id": self.cfg.location_id},
            "checkout_options": {"subscription_plan_id": variation_id, "redirect_url": redirect_url,
                                 "ask_for_shipping_address": False, "allow_tipping": False},
            "pre_populated_data": {"buyer_email": buyer_email},
            "payment_note": reference,
        }
        link = self._req("POST", "/v2/online-checkout/payment-links", body)["payment_link"]
        return {"id": link["id"], "url": link["url"], "order_id": link.get("order_id")}

    # subscriptions -------------------------------------------------------------------------------
    def get_subscription(self, sub_id: str) -> dict[str, Any]:
        return self._req("GET", f"/v2/subscriptions/{sub_id}")["subscription"]

    def cancel_subscription(self, sub_id: str) -> dict[str, Any]:
        return self._req("POST", f"/v2/subscriptions/{sub_id}/cancel")["subscription"]

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        return self._req("GET", f"/v2/customers/{customer_id}")["customer"]

    # catalog setup -------------------------------------------------------------------------------
    def create_plans(self, prices: dict[str, int]) -> dict[str, str]:
        """Create the Irradiance membership plan with one variation per plan × interval. Returns key -> id."""
        variations = []
        for key, cents in prices.items():
            plan, interval = key.split("_")
            variations.append({
                "type": "SUBSCRIPTION_PLAN_VARIATION", "id": f"#{key}",
                "subscription_plan_variation_data": {
                    "name": f"{plan.title()} ({interval})",
                    "phases": [{"ordinal": 0, "cadence": "MONTHLY" if interval == "monthly" else "ANNUAL",
                                "pricing": {"type": "STATIC",
                                            "price_money": {"amount": cents, "currency": "USD"}}}]}})
        body = {"idempotency_key": str(uuid.uuid4()), "object": {
            "type": "SUBSCRIPTION_PLAN", "id": "#irradiance_membership",
            "subscription_plan_data": {"name": "Irradiance membership", "subscription_plan_variations": variations}}}
        res = self._req("POST", "/v2/catalog/object", body)
        ids = {m["client_object_id"].lstrip("#"): m["object_id"] for m in res.get("id_mappings", [])}
        return {k: ids[k] for k in prices if k in ids}

    def list_locations(self) -> list[dict[str, Any]]:
        return self._req("GET", "/v2/locations").get("locations", [])
