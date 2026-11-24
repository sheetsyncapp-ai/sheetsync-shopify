import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    app_name: str = "SheetSync for Shopify"
    app_url: str = os.getenv("APP_URL", "http://localhost:8000")
    
    # Shopify Credentials
    shopify_api_key: str = os.getenv("SHOPIFY_API_KEY", "")
    shopify_api_secret: str = os.getenv("SHOPIFY_API_SECRET", "")
    shopify_scopes: str = "read_orders,read_products,read_inventory"
    
    # Google OAuth Credentials
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")
    
    # Storage
    db_file: str = os.getenv("DB_FILE", "sheetsync_data.json")

settings = Settings()
