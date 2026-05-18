"""
database.py — SQLAlchemy connection + all table models
Smart-Shop AI Engine
"""

import os
from datetime import datetime
from dotenv import load_dotenv

from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    Boolean, DateTime, Text, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# ── Connection ────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:db155867@localhost:5432/sshop_db")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── Table 1: customer_predictions ─────────────────────────────────────────────
class CustomerPrediction(Base):
    __tablename__ = "customer_predictions"

    id                      = Column(Integer, primary_key=True, index=True)
    customer_id             = Column(String(100), index=True)
    customer_email          = Column(String(255), nullable=True)
    customer_name           = Column(String(255), nullable=True)

    # Shopify cart data
    cart_token              = Column(String(255), nullable=True)
    items_in_cart           = Column(Integer, default=0)
    cart_items_json         = Column(JSON, nullable=True)       # [{title, price, qty}]
    total_cart_value        = Column(Float, default=0.0)

    # Browsing behaviour features (from ML model)
    administrative          = Column(Integer, default=0)
    administrative_duration = Column(Float, default=0.0)
    informational           = Column(Integer, default=0)
    informational_duration  = Column(Float, default=0.0)
    product_related         = Column(Integer, default=0)
    product_related_duration= Column(Float, default=0.0)
    bounce_rates            = Column(Float, default=0.0)
    exit_rates              = Column(Float, default=0.0)
    page_values             = Column(Float, default=0.0)
    special_day             = Column(Float, default=0.0)

    # ML output
    churn_prediction        = Column(Integer, default=0)        # 0 = safe, 1 = churn risk
    churn_probability       = Column(Float, default=0.0)        # 0.0 – 1.0

    # Meta
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Table 2: email_history ────────────────────────────────────────────────────
class EmailHistory(Base):
    __tablename__ = "email_history"

    id                  = Column(Integer, primary_key=True, index=True)
    customer_id         = Column(String(100), index=True)
    customer_email      = Column(String(255))
    customer_name       = Column(String(255), nullable=True)

    churn_probability   = Column(Float, default=0.0)
    email_subject       = Column(String(500), nullable=True)
    email_body          = Column(Text, nullable=True)           # AI-generated content
    discount_code       = Column(String(50), default="SAVE10")

    sent_manually       = Column(Boolean, default=False)        # True = user forced send
    send_status         = Column(String(50), default="pending") # pending | sent | failed
    error_message       = Column(Text, nullable=True)

    sent_at             = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)


# ── Table 3: shopify_tokens ───────────────────────────────────────────────────
class ShopifyToken(Base):
    __tablename__ = "shopify_tokens"

    id           = Column(Integer, primary_key=True, index=True)
    shop         = Column(String(255), unique=True, index=True)
    access_token = Column(String(500))
    scope        = Column(String(500), nullable=True)
    expires_at   = Column(DateTime, nullable=True)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Table 4: sync_logs ────────────────────────────────────────────────────────
class SyncLog(Base):
    __tablename__ = "sync_logs"

    id              = Column(Integer, primary_key=True, index=True)
    sync_type       = Column(String(100))    # "abandoned_carts" | "manual" | "webhook"
    records_fetched = Column(Integer, default=0)
    records_saved   = Column(Integer, default=0)
    status          = Column(String(50), default="success")  # success | failed
    error_message   = Column(Text, nullable=True)
    synced_at       = Column(DateTime, default=datetime.utcnow)


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_db():
    """FastAPI dependency — yields a DB session then closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created / verified in sshop_db")


if __name__ == "__main__":
    init_db()
