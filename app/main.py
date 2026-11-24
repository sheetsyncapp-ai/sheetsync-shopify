import os
import random
import datetime
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import settings
from app.shopify_service import ShopifyService, StorageManager
from app.sheets_service import SheetsService

app = FastAPI(title=settings.app_name)

current_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(current_dir, "templates"))


class SettingsUpdatePayload(BaseModel):
    shop: str
    spreadsheet_id: str
    sheet_tab: str = "Orders"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, shop: Optional[str] = "demo-store.myshopify.com"):
    """Renders the Shopify Polaris Admin UI for the app."""
    store = StorageManager.get_store(shop) or {}
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "shop": shop,
            "store": store
        }
    )


@app.get("/api/auth/shopify/install")
async def shopify_install(shop: str):
    """Initiates Shopify OAuth installation."""
    install_url = ShopifyService.get_install_url(shop)
    return RedirectResponse(url=install_url)


@app.get("/api/auth/shopify/callback")
async def shopify_callback(shop: str, code: Optional[str] = None):
    """Handles Shopify OAuth Callback, saves access token, redirects to app."""
    store = StorageManager.get_store(shop) or {}
    if code:
        try:
            token = await ShopifyService.exchange_token(shop, code)
            store["shopify_token"] = token
            store["installed"] = True
            StorageManager.save_store(shop, store)
        except Exception as e:
            print(f"[Notice] Shopify token exchange note: {e}")
            store["installed"] = True
            StorageManager.save_store(shop, store)

    return RedirectResponse(url=f"/?shop={shop}&installed=true")


@app.get("/api/auth/google/login")
async def google_login(shop: str = "demo-store.myshopify.com"):
    """Initiates Google OAuth2 consent flow or dev mock mode."""
    if not settings.google_client_id or not settings.google_client_secret:
        # Mock connection for local dev / testing without Google credentials configured yet
        store = StorageManager.get_store(shop) or {}
        store["google_tokens"] = {
            "token": "mock_token_for_dev",
            "refresh_token": "mock_refresh_token"
        }
        StorageManager.save_store(shop, store)
        return RedirectResponse(url=f"/?shop={shop}&notice=connected_dev_mode")
    
    auth_url = SheetsService.get_auth_url(state=shop)
    return RedirectResponse(url=auth_url)


@app.get("/api/auth/google/callback")
async def google_callback(code: str, state: str):
    """Google OAuth2 Callback: exchanges code and saves tokens for this shop."""
    shop = state
    try:
        tokens = await SheetsService.exchange_code(code)
        store = StorageManager.get_store(shop) or {}
        store["google_tokens"] = tokens
        StorageManager.save_store(shop, store)
        return RedirectResponse(url=f"/?shop={shop}&notice=google_connected")
    except Exception as e:
        return RedirectResponse(url=f"/?shop={shop}&error={str(e)}")


@app.post("/api/settings")
async def save_settings(payload: SettingsUpdatePayload):
    """Saves merchant's target Google Spreadsheet ID and Tab name."""
    store = StorageManager.get_store(payload.shop) or {}
    clean_sheet_id = payload.spreadsheet_id.strip()
    
    # Extract ID if user pasted full Google Sheets URL
    if "/d/" in clean_sheet_id:
        try:
            clean_sheet_id = clean_sheet_id.split("/d/")[1].split("/")[0]
        except Exception:
            pass

    store["spreadsheet_id"] = clean_sheet_id
    store["sheet_tab"] = payload.sheet_tab or "Orders"
    store["sheet_title"] = f"Sheet ({clean_sheet_id[:6]}...)" if clean_sheet_id else "Not Set"
    StorageManager.save_store(payload.shop, store)
    return {"status": "success", "store": store}


@app.post("/api/webhooks/orders-paid")
async def webhook_orders_paid(request: Request, x_shopify_hmac_sha256: Optional[str] = Header(None), x_shopify_shop_domain: Optional[str] = Header(None)):
    """Shopify Webhook endpoint: triggered immediately when a customer pays for an order."""
    body_bytes = await request.body()
    
    # Verify HMAC authenticity
    if x_shopify_hmac_sha256:
        if not ShopifyService.verify_webhook(body_bytes, x_shopify_hmac_sha256):
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    order_data = await request.json()
    shop = x_shopify_shop_domain or "demo-store.myshopify.com"
    store = StorageManager.get_store(shop) or {}

    tokens = store.get("google_tokens")
    spreadsheet_id = store.get("spreadsheet_id")
    sheet_tab = store.get("sheet_tab", "Orders")

    # If Google is configured, append to live spreadsheet
    if tokens and spreadsheet_id:
        try:
            await SheetsService.append_order(tokens, spreadsheet_id, sheet_tab, order_data)
        except Exception as e:
            print(f"[Error] Failed to append order to Google Sheet: {e}")

    # Track sync metrics
    store["synced_count"] = (store.get("synced_count") or 0) + 1
    store["last_sync_at"] = datetime.datetime.utcnow().isoformat()
    StorageManager.save_store(shop, store)

    return {"status": "processed", "order_id": order_data.get("id")}


@app.post("/api/test-sync")
async def test_sync(shop: str = "demo-store.myshopify.com"):
    """Simulates an order and attempts to append to the configured Google Sheet."""
    store = StorageManager.get_store(shop) or {}
    tokens = store.get("google_tokens")
    spreadsheet_id = store.get("spreadsheet_id")
    sheet_tab = store.get("sheet_tab", "Orders")

    sample_order_number = f"#{random.randint(1001, 9999)}"
    sample_order = {
        "name": sample_order_number,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "customer": {
            "first_name": "Alexander",
            "last_name": "Wright",
            "email": "alex.wright@example.com"
        },
        "line_items": [
            {"title": "Classic Leather Wallet", "quantity": 1},
            {"title": "Minimalist Cardholder", "quantity": 2}
        ],
        "total_price": "79.00",
        "currency": "USD",
        "financial_status": "paid",
        "fulfillment_status": "unfulfilled",
        "shipping_address": {
            "city": "Austin",
            "country": "United States"
        }
    }

    if tokens and spreadsheet_id and tokens.get("token") != "mock_token_for_dev":
        try:
            await SheetsService.append_order(tokens, spreadsheet_id, sheet_tab, sample_order)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Google API Error: {str(e)}")

    store["synced_count"] = (store.get("synced_count") or 0) + 1
    store["last_sync_at"] = datetime.datetime.utcnow().isoformat()
    StorageManager.save_store(shop, store)

    return {
        "status": "success",
        "order_name": sample_order_number,
        "mode": "live" if (tokens and spreadsheet_id and tokens.get("token") != "mock_token_for_dev") else "simulation"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
