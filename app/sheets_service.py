import json
import urllib.parse
from typing import Dict, Any, List, Optional
import httpx
from app.config import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SHEETS_BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly"
]

class SheetsService:
    @staticmethod
    def get_auth_url(state: str = "") -> str:
        """Generates Google OAuth2 consent URL without heavy SDK."""
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    @staticmethod
    async def exchange_code(code: str) -> Dict[str, Any]:
        """Exchanges Google auth code for refresh and access tokens."""
        data = {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code"
        }
        async with httpx.AsyncClient() as client:
            res = await client.post(GOOGLE_TOKEN_URL, data=data)
            res.raise_for_status()
            return res.json()

    @staticmethod
    async def get_valid_access_token(tokens: Dict[str, Any]) -> str:
        """Returns active token, refreshing it if necessary."""
        refresh_token = tokens.get("refresh_token")
        # In mock/dev mode
        if tokens.get("token") == "mock_token_for_dev":
            return "mock_token_for_dev"

        if refresh_token and settings.google_client_id and settings.google_client_secret:
            try:
                data = {
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token"
                }
                async with httpx.AsyncClient() as client:
                    res = await client.post(GOOGLE_TOKEN_URL, data=data)
                    if res.status_code == 200:
                        new_tokens = res.json()
                        tokens["access_token"] = new_tokens.get("access_token", tokens.get("access_token"))
                        return tokens["access_token"]
            except Exception:
                pass
        return tokens.get("access_token") or tokens.get("token", "")

    @staticmethod
    def format_order_row(order: Dict[str, Any]) -> List[Any]:
        """Maps Shopify Order webhook JSON to a clean spreadsheet row."""
        order_name = order.get("name", "")
        created_at = order.get("created_at", "")[:19].replace("T", " ")
        customer = order.get("customer", {}) or {}
        customer_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
        customer_email = customer.get("email", "") or order.get("email", "")
        
        items = order.get("line_items", [])
        items_summary = ", ".join([f"{item.get('title')} (x{item.get('quantity')})" for item in items])
        
        total_price = order.get("total_price", "0.00")
        currency = order.get("currency", "USD")
        financial_status = order.get("financial_status", "")
        fulfillment_status = order.get("fulfillment_status") or "unfulfilled"
        
        shipping = order.get("shipping_address", {}) or {}
        city = shipping.get("city", "")
        country = shipping.get("country", "")

        return [
            order_name,
            created_at,
            customer_name,
            customer_email,
            items_summary,
            f"{total_price} {currency}",
            financial_status.upper(),
            fulfillment_status.capitalize(),
            f"{city}, {country}".strip(", ")
        ]

    @classmethod
    async def append_order(cls, tokens: Dict[str, Any], spreadsheet_id: str, sheet_tab: str, order: Dict[str, Any]) -> Dict[str, Any]:
        """Appends formatted order row to Google Sheets via REST API with automatic sheet detection."""
        access_token = await cls.get_valid_access_token(tokens)
        if access_token == "mock_token_for_dev":
            return {"status": "simulated", "order": order.get("name")}

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            # 1. Fetch spreadsheet metadata to verify sheet tab exists or pick the first sheet
            meta_url = f"{GOOGLE_SHEETS_BASE_URL}/{spreadsheet_id}?fields=sheets.properties.title"
            meta_res = await client.get(meta_url, headers=headers)
            target_tab = sheet_tab
            
            if meta_res.status_code == 200:
                available_sheets = [
                    s.get("properties", {}).get("title") 
                    for s in meta_res.json().get("sheets", [])
                ]
                if available_sheets:
                    # If requested tab isn't present, default to the first sheet or add it
                    if sheet_tab not in available_sheets:
                        target_tab = available_sheets[0]

            # 2. Check if headers exist in target sheet
            check_url = f"{GOOGLE_SHEETS_BASE_URL}/{spreadsheet_id}/values/'{target_tab}'!A1:I1"
            check_res = await client.get(check_url, headers=headers)
            values = []
            if check_res.status_code == 200:
                values = check_res.json().get("values", [])

            table_headers = [
                "Order #", "Date (UTC)", "Customer Name", "Customer Email",
                "Products", "Total Price", "Payment Status", "Fulfillment", "Location"
            ]

            append_url = f"{GOOGLE_SHEETS_BASE_URL}/{spreadsheet_id}/values/'{target_tab}'!A1:append?valueInputOption=USER_ENTERED"
            
            if not values:
                # Insert header row first
                await client.post(append_url, headers=headers, json={"values": [table_headers]})

            # 3. Append the actual order data
            row_data = cls.format_order_row(order)
            res = await client.post(append_url, headers=headers, json={"values": [row_data]})
            res.raise_for_status()
            return res.json()
