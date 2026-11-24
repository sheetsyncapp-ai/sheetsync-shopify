import hmac
import hashlib
import base64
import json
import os
from typing import Dict, Any, Optional
import httpx
from app.config import settings

class ShopifyService:
    @staticmethod
    def verify_webhook(data: bytes, hmac_header: str) -> bool:
        """Verifies that incoming webhook is authentically signed by Shopify."""
        if not settings.shopify_api_secret:
            # In local dev without secret configured, allow bypass
            return True
        digest = hmac.new(
            settings.shopify_api_secret.encode('utf-8'),
            data,
            hashlib.sha256
        ).digest()
        computed_hmac = base64.b64encode(digest).decode('utf-8')
        return hmac.compare_digest(computed_hmac, hmac_header)

    @staticmethod
    def get_install_url(shop: str) -> str:
        """Generates Shopify OAuth URL for installing the app."""
        redirect_uri = f"{settings.app_url}/api/auth/shopify/callback"
        return (
            f"https://{shop}/admin/oauth/authorize?"
            f"client_id={settings.shopify_api_key}&"
            f"scope={settings.shopify_scopes}&"
            f"redirect_uri={redirect_uri}"
        )

    @staticmethod
    async def exchange_token(shop: str, code: str) -> str:
        """Exchanges Shopify OAuth code for permanent store access token."""
        url = f"https://{shop}/admin/oauth/access_token"
        payload = {
            "client_id": settings.shopify_api_key,
            "client_secret": settings.shopify_api_secret,
            "code": code
        }
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
            return data["access_token"]

    @staticmethod
    async def create_subscription(shop: str, access_token: str, plan_name: str, price: float, return_url: str) -> str:
        """Creates a recurring subscription charge via Shopify GraphQL API and returns confirmation URL."""
        graphql_url = f"https://{shop}/admin/api/2026-10/graphql.json"
        query = """
        mutation AppSubscriptionCreate($name: String!, $lineItems: [AppSubscriptionLineItemInput!]!, $returnUrl: URL!, $trialDays: Int) {
          appSubscriptionCreate(name: $name, lineItems: $lineItems, returnUrl: $returnUrl, trialDays: $trialDays) {
            userErrors {
              field
              message
            }
            confirmationUrl
            appSubscription {
              id
              status
            }
          }
        }
        """
        variables = {
            "name": f"SheetSync {plan_name}",
            "returnUrl": return_url,
            "trialDays": 7,
            "lineItems": [
                {
                    "plan": {
                        "appRecurringPricingDetails": {
                            "price": {
                                "amount": price,
                                "currencyCode": "USD"
                            },
                            "interval": "EVERY_30_DAYS"
                        }
                    }
                }
            ]
        }
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token
        }
        async with httpx.AsyncClient() as client:
            res = await client.post(graphql_url, json={"query": query, "variables": variables}, headers=headers)
            data = res.json()
            sub_data = data.get("data", {}).get("appSubscriptionCreate", {})
            errors = sub_data.get("userErrors", [])
            if errors:
                raise Exception(errors[0].get("message", "Error creating subscription"))
            return sub_data.get("confirmationUrl")


class StorageManager:
    """Simple JSON-based store configuration database (ideal for micro-apps and local dev)."""
    @staticmethod
    def _read_data() -> Dict[str, Any]:
        if not os.path.exists(settings.db_file):
            return {}
        try:
            with open(settings.db_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _write_data(data: Dict[str, Any]):
        with open(settings.db_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def get_store(cls, shop: str) -> Optional[Dict[str, Any]]:
        data = cls._read_data()
        return data.get(shop)

    @classmethod
    def save_store(cls, shop: str, store_data: Dict[str, Any]):
        data = cls._read_data()
        current = data.get(shop, {})
        current.update(store_data)
        data[shop] = current
        cls._write_data(data)

    @classmethod
    def get_all_stores(cls) -> Dict[str, Any]:
        return cls._read_data()
