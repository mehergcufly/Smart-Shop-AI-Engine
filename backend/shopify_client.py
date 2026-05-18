"""
shopify_client.py — Shopify token exchange + abandoned cart fetching
Smart-Shop AI Engine
"""

import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database import ShopifyToken, SyncLog

load_dotenv()

SHOP            = os.getenv("SHOPIFY_SHOP", "sia-glow")
CLIENT_ID       = os.getenv("SHOPIFY_CLIENT_ID")
CLIENT_SECRET   = os.getenv("SHOPIFY_CLIENT_SECRET")
API_VERSION     = os.getenv("SHOPIFY_API_VERSION", "2025-01")
BASE_URL        = f"https://{SHOP}.myshopify.com/admin/api/{API_VERSION}"


# ── Token Management ──────────────────────────────────────────────────────────

def get_access_token(db: Session) -> str:
    """
    Return a valid access token.
    - If we have one in DB that is not expired → return it.
    - Otherwise exchange client credentials for a fresh token → save → return.
    """
    record = db.query(ShopifyToken).filter_by(shop=SHOP, is_active=True).first()

    if record:
        # tokens expire after 24 h; refresh 5 min early
        if record.expires_at and record.expires_at > datetime.utcnow() + timedelta(minutes=5):
            return record.access_token

    # Exchange credentials
    token, expires_at = _exchange_credentials()

    if record:
        record.access_token = token
        record.expires_at   = expires_at
        record.updated_at   = datetime.utcnow()
    else:
        record = ShopifyToken(
            shop         = SHOP,
            access_token = token,
            expires_at   = expires_at,
            is_active    = True,
        )
        db.add(record)

    db.commit()
    return token


def _exchange_credentials() -> tuple[str, datetime]:
    """POST to Shopify OAuth endpoint and return (token, expires_at)."""
    url  = f"https://{SHOP}.myshopify.com/admin/oauth/access_token"
    body = {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "client_credentials",
    }

    resp = requests.post(url, json=body, timeout=15)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Shopify token exchange failed [{resp.status_code}]: {resp.text}"
        )

    data       = resp.json()
    token      = data.get("access_token") or data.get("token")
    expires_at = datetime.utcnow() + timedelta(hours=24)

    if not token:
        raise RuntimeError(f"No token in Shopify response: {data}")

    print(f"✅ New Shopify token obtained, expires at {expires_at}")
    return token, expires_at


def _headers(token: str) -> dict:
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type":           "application/json",
    }


# ── Abandoned Checkouts ───────────────────────────────────────────────────────

def fetch_abandoned_checkouts(db: Session, limit: int = 50) -> list[dict]:
    """
    Fetch abandoned checkouts from Shopify.
    Returns a clean list of dicts ready for ML inference + email generation.
    """
    token     = get_access_token(db)
    url       = f"{BASE_URL}/checkouts.json"
    params    = {"limit": limit, "status": "open"}

    resp = requests.get(url, headers=_headers(token), params=params, timeout=15)

    if resp.status_code != 200:
        _log_sync(db, "abandoned_carts", 0, 0, "failed", resp.text)
        raise RuntimeError(f"Shopify checkouts fetch failed [{resp.status_code}]: {resp.text}")

    checkouts = resp.json().get("checkouts", [])
    cleaned   = [_parse_checkout(c) for c in checkouts]

    _log_sync(db, "abandoned_carts", len(cleaned), len(cleaned), "success")
    return cleaned


def _parse_checkout(c: dict) -> dict:
    """Flatten a Shopify checkout object into the fields we need."""
    customer  = c.get("customer") or {}
    email     = c.get("email") or customer.get("email", "")
    name      = (
        f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
        or c.get("billing_address", {}).get("name", "Valued Customer")
    )

    line_items = c.get("line_items", [])
    cart_items = [
        {
            "title":    item.get("title", "Unknown Item"),
            "quantity": item.get("quantity", 1),
            "price":    float(item.get("price", 0)),
        }
        for item in line_items
    ]

    total = float(c.get("total_price", 0) or 0)

    return {
        "customer_id":    str(customer.get("id") or c.get("token", "unknown")),
        "customer_email": email,
        "customer_name":  name or "Valued Customer",
        "cart_token":     c.get("token", ""),
        "items_in_cart":  len(line_items),
        "cart_items":     cart_items,
        "total_cart_value": total,
        # Default browsing features (Shopify doesn't provide these;
        # they will be 0 unless you inject real analytics data)
        "administrative":           0,
        "administrative_duration":  0.0,
        "informational":            0,
        "informational_duration":   0.0,
        "product_related":          len(line_items),
        "product_related_duration": 0.0,
        "bounce_rates":             0.0,
        "exit_rates":               0.0,
        "page_values":              total,   # cart value ≈ page value proxy
        "special_day":              0.0,
    }


# ── Shop Info ─────────────────────────────────────────────────────────────────

def fetch_shop_info(db: Session) -> dict:
    """Return basic store metadata."""
    token = get_access_token(db)
    resp  = requests.get(f"{BASE_URL}/shop.json", headers=_headers(token), timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Shop info failed [{resp.status_code}]: {resp.text}")
    return resp.json().get("shop", {})


def fetch_orders_summary(db: Session, limit: int = 250) -> dict:
    """Return total orders + revenue for dashboard KPIs."""
    token  = get_access_token(db)
    url    = f"{BASE_URL}/orders.json"
    params = {"limit": limit, "status": "any", "fields": "id,total_price,financial_status,created_at"}

    resp = requests.get(url, headers=_headers(token), params=params, timeout=15)
    if resp.status_code != 200:
        return {"total_orders": 0, "total_revenue": 0.0}

    orders  = resp.json().get("orders", [])
    revenue = sum(float(o.get("total_price", 0)) for o in orders)

    return {
        "total_orders":  len(orders),
        "total_revenue": round(revenue, 2),
        "orders":        orders,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_sync(db: Session, sync_type: str, fetched: int,
              saved: int, status: str, error: str = None):
    log = SyncLog(
        sync_type       = sync_type,
        records_fetched = fetched,
        records_saved   = saved,
        status          = status,
        error_message   = error,
    )
    db.add(log)
    db.commit()


# ── Quick smoke-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    from database import SessionLocal, init_db
    init_db()
    db = SessionLocal()
    try:
        info = fetch_shop_info(db)
        print(f"✅ Connected to shop: {info.get('name')} ({info.get('domain')})")
        carts = fetch_abandoned_checkouts(db, limit=5)
        print(f"✅ Abandoned checkouts fetched: {len(carts)}")
        for c in carts:
            print(f"   → {c['customer_name']} | {c['items_in_cart']} items | £{c['total_cart_value']}")
    finally:
        db.close()
