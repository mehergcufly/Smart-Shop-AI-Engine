"""
main.py — FastAPI application
Smart-Shop AI Engine — Fixed: anti-spam email, PKR, no duplicates, force-send response
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from pathlib import Path
import traceback, os

from database import (
    get_db, init_db,
    CustomerPrediction, EmailHistory, SyncLog
)
from shopify_client import (
    fetch_abandoned_checkouts, fetch_shop_info,
    fetch_orders_summary, get_access_token
)
from ml_model import predict_churn, predict_batch
from ai_engine import generate_email
from email_service import send_and_log

SHOP_URL = os.getenv("SHOPIFY_SHOP", "sia-glow")

app = FastAPI(
    title       = "Smart-Shop AI Engine",
    description = "Cart abandonment prediction + personalised win-back emails",
    version     = "1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.on_event("startup")
def startup():
    init_db()
    print("🚀 Smart-Shop AI Engine running")


# ── Schemas ───────────────────────────────────────────────────────────────────
class CustomerData(BaseModel):
    customer_id:              str
    customer_email:           str   = ""
    customer_name:            str   = "Valued Customer"
    cart_items:               list  = []
    total_cart_value:         float = 0.0
    items_in_cart:            int   = 0
    cart_url:                 str   = ""
    administrative:           float = 0.0
    administrative_duration:  float = 0.0
    informational:            float = 0.0
    informational_duration:   float = 0.0
    product_related:          float = 0.0
    product_related_duration: float = 0.0
    bounce_rates:             float = 0.0
    exit_rates:               float = 0.0
    page_values:              float = 0.0
    special_day:              float = 0.0


class SendEmailRequest(BaseModel):
    customer_id:   str
    force_send:    bool = False
    discount_code: str  = "SAVE10"


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "running", "service": "Smart-Shop AI Engine", "docs": "/docs"}

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        import sqlalchemy
        db.execute(sqlalchemy.text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"
    return {"api": "ok", "database": db_status, "timestamp": datetime.utcnow()}


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — ML Prediction
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/predict")
def predict_single(data: CustomerData, db: Session = Depends(get_db)):
    try:
        result = predict_churn(data.dict())
        record = CustomerPrediction(
            customer_id              = data.customer_id,
            customer_email           = data.customer_email,
            customer_name            = data.customer_name,
            items_in_cart            = data.items_in_cart,
            cart_items_json          = data.cart_items,
            total_cart_value         = data.total_cart_value,
            administrative           = data.administrative,
            administrative_duration  = data.administrative_duration,
            informational            = data.informational,
            informational_duration   = data.informational_duration,
            product_related          = data.product_related,
            product_related_duration = data.product_related_duration,
            bounce_rates             = data.bounce_rates,
            exit_rates               = data.exit_rates,
            page_values              = data.page_values,
            special_day              = data.special_day,
            churn_prediction         = result["churn_prediction"],
            churn_probability        = result["churn_probability"],
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {
            "record_id":         record.id,
            "customer_id":       data.customer_id,
            "churn_prediction":  result["churn_prediction"],
            "churn_probability": result["churn_probability"],
            "risk_level":        result["risk_level"],
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — Shopify Sync (FIX: deduplicate by cart_token, not just customer_id)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/shopify/sync")
def sync_abandoned_carts(db: Session = Depends(get_db)):
    try:
        checkouts = fetch_abandoned_checkouts(db, limit=50)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not checkouts:
        return {"synced": 0, "message": "No abandoned checkouts found"}

    enriched = predict_batch(checkouts)
    saved = 0

    for c in enriched:
        # FIX: deduplicate by cart_token (unique per checkout) — prevents duplicates
        cart_token = c.get("cart_token", "")
        if cart_token:
            existing = (
                db.query(CustomerPrediction)
                .filter(CustomerPrediction.cart_token == cart_token)
                .first()
            )
        else:
            # Fallback: deduplicate by customer_id within today
            existing = (
                db.query(CustomerPrediction)
                .filter_by(customer_id=c["customer_id"])
                .filter(
                    func.date(CustomerPrediction.created_at) == datetime.utcnow().date()
                )
                .first()
            )

        if existing:
            continue

        record = CustomerPrediction(
            customer_id       = c["customer_id"],
            customer_email    = c.get("customer_email", ""),
            customer_name     = c.get("customer_name", ""),
            cart_token        = cart_token,
            items_in_cart     = c.get("items_in_cart", 0),
            cart_items_json   = c.get("cart_items", []),
            total_cart_value  = c.get("total_cart_value", 0.0),
            product_related   = c.get("product_related", 0),
            page_values       = c.get("page_values", 0.0),
            churn_prediction  = c["churn_prediction"],
            churn_probability = c["churn_probability"],
        )
        db.add(record)
        saved += 1

    db.commit()
    at_risk = sum(1 for c in enriched if c["churn_prediction"] == 1)

    return {
        "synced":        saved,
        "total_fetched": len(enriched),
        "at_risk":       at_risk,
        "message":       f"Synced {saved} new records. {at_risk} customers at churn risk.",
    }


@app.get("/shopify/info")
def shopify_info(db: Session = Depends(get_db)):
    try:
        info   = fetch_shop_info(db)
        orders = fetch_orders_summary(db)
        token  = get_access_token(db)
        return {
            "connected":     True,
            "shop_name":     info.get("name"),
            "domain":        info.get("domain"),
            "email":         info.get("email"),
            "currency":      info.get("currency"),
            "plan":          info.get("plan_name"),
            "total_orders":  orders["total_orders"],
            "total_revenue": orders["total_revenue"],
            "token_active":  bool(token),
        }
    except RuntimeError as e:
        return {"connected": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — Email Generation & Sending
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/predict_and_email")
def predict_and_email(data: CustomerData, db: Session = Depends(get_db)):
    try:
        result = predict_churn(data.dict())

        record = CustomerPrediction(
            customer_id       = data.customer_id,
            customer_email    = data.customer_email,
            customer_name     = data.customer_name,
            items_in_cart     = data.items_in_cart,
            cart_items_json   = data.cart_items,
            total_cart_value  = data.total_cart_value,
            churn_prediction  = result["churn_prediction"],
            churn_probability = result["churn_probability"],
        )
        db.add(record)
        db.commit()

        if result["churn_prediction"] == 0:
            return {
                "status":           "no_action",
                "churn_prediction": 0,
                "churn_probability":result["churn_probability"],
                "risk_level":       result["risk_level"],
                "message":          "Customer is not at risk — no email sent.",
            }

        if not data.customer_email or "@" not in data.customer_email:
            return {
                "status":           "prediction_saved_no_email",
                "churn_prediction": result["churn_prediction"],
                "churn_probability":result["churn_probability"],
                "risk_level":       result["risk_level"],
                "message":          "At-risk customer saved. No valid email — skipped.",
            }

        email = generate_email(
            customer_name     = data.customer_name,
            cart_items        = data.cart_items,
            total_cart_value  = data.total_cart_value,
            churn_probability = result["churn_probability"],
        )

        cart_link = data.cart_url or f"https://{SHOP_URL}.myshopify.com/cart"

        send_result = send_and_log(
            db                = db,
            customer_id       = data.customer_id,
            customer_email    = data.customer_email,
            customer_name     = data.customer_name,
            subject           = email["subject"],
            body              = email["body"],
            churn_probability = result["churn_probability"],
            cart_items        = data.cart_items,
            total_cart_value  = data.total_cart_value,
            cart_url          = cart_link,
        )

        return {
            "status":           "email_sent" if send_result["success"] else "email_failed",
            "churn_prediction": result["churn_prediction"],
            "churn_probability":result["churn_probability"],
            "risk_level":       result["risk_level"],
            "generated_email":  email,
            "send_success":     send_result["success"],
            "send_error":       send_result.get("error"),
            "history_id":       send_result.get("history_id"),
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.post("/send_email/{customer_id}")
def send_email_to_customer(
    customer_id: str,
    req: SendEmailRequest,
    db: Session = Depends(get_db),
):
    try:
        pred = (
            db.query(CustomerPrediction)
            .filter_by(customer_id=customer_id)
            .order_by(CustomerPrediction.created_at.desc())
            .first()
        )
        if not pred:
            raise HTTPException(status_code=404, detail="Customer prediction not found")

        if not req.force_send and pred.churn_prediction == 0:
            return {
                "status":  "skipped",
                "message": "Churn risk is low. Use force_send=true to send anyway.",
                "churn_probability": pred.churn_probability,
            }

        if not pred.customer_email or "@" not in pred.customer_email:
            raise HTTPException(
                status_code=400,
                detail=f"No valid email for customer {customer_id}: '{pred.customer_email}'"
            )

        email = generate_email(
            customer_name     = pred.customer_name or "Valued Customer",
            cart_items        = pred.cart_items_json or [],
            total_cart_value  = pred.total_cart_value or 0.0,
            churn_probability = pred.churn_probability,
            discount_code     = req.discount_code,
        )

        cart_link = f"https://{SHOP_URL}.myshopify.com/cart"

        result = send_and_log(
            db                = db,
            customer_id       = customer_id,
            customer_email    = pred.customer_email,
            customer_name     = pred.customer_name,
            subject           = email["subject"],
            body              = email["body"],
            churn_probability = pred.churn_probability,
            discount_code     = req.discount_code,
            sent_manually     = True,
            cart_items        = pred.cart_items_json or [],
            total_cart_value  = pred.total_cart_value or 0.0,
            cart_url          = cart_link,
        )

        return {
            "status":          "sent" if result["success"] else "failed",
            "message":         "Email sent successfully!" if result["success"] else f"Failed: {result.get('error')}",
            "generated_email": email,
            "history_id":      result.get("history_id"),
            "error":           result.get("error"),
            "customer_name":   pred.customer_name,
            "customer_email":  pred.customer_email,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — Dashboard APIs
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/dashboard/overview")
def dashboard_overview(db: Session = Depends(get_db)):
    try:
        preds   = db.query(CustomerPrediction).all()
        emails  = db.query(EmailHistory).all()
        total   = len(preds)
        at_risk = sum(1 for p in preds if p.churn_prediction == 1)
        safe    = total - at_risk
        churn_rate  = round((at_risk / total * 100), 1) if total else 0.0
        emails_sent = sum(1 for e in emails if e.send_status == "sent")
        avg_prob    = round(sum(p.churn_probability for p in preds) / total * 100, 1) if total else 0.0

        from collections import defaultdict
        monthly = defaultdict(lambda: {"total": 0, "at_risk": 0})
        for p in preds:
            key = p.created_at.strftime("%Y-%m")
            monthly[key]["total"]   += 1
            monthly[key]["at_risk"] += p.churn_prediction

        monthly_trend = [
            {
                "month":     k,
                "total":     v["total"],
                "at_risk":   v["at_risk"],
                "churn_pct": round(v["at_risk"] / v["total"] * 100, 1) if v["total"] else 0,
            }
            for k, v in sorted(monthly.items())[-6:]
        ]

        risk_dist = {
            "high":   sum(1 for p in preds if p.churn_probability >= 0.65),
            "medium": sum(1 for p in preds if 0.40 <= p.churn_probability < 0.65),
            "low":    sum(1 for p in preds if p.churn_probability < 0.40),
        }

        return {
            "kpis": {
                "total_customers": total,
                "at_risk":         at_risk,
                "safe":            safe,
                "churn_rate_pct":  churn_rate,
                "avg_churn_prob":  avg_prob,
                "emails_sent":     emails_sent,
            },
            "monthly_trend":     monthly_trend,
            "risk_distribution": risk_dist,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/customers")
def dashboard_customers(
    db:      Session = Depends(get_db),
    limit:   int     = 100,
    at_risk: bool    = False,
):
    try:
        # FIX: deduplicate — show only the LATEST record per customer_id
        from sqlalchemy import desc

        # Get latest record per customer_id using subquery
        subq = (
            db.query(
                CustomerPrediction.customer_id,
                func.max(CustomerPrediction.id).label("max_id")
            )
            .group_by(CustomerPrediction.customer_id)
            .subquery()
        )

        query = (
            db.query(CustomerPrediction)
            .join(subq, CustomerPrediction.id == subq.c.max_id)
            .order_by(desc(CustomerPrediction.churn_probability))
        )

        if at_risk:
            query = query.filter(CustomerPrediction.churn_prediction == 1)

        records = query.limit(limit).all()

        return {
            "customers": [
                {
                    "id":               r.id,
                    "customer_id":      r.customer_id,
                    "customer_name":    r.customer_name,
                    "customer_email":   r.customer_email,
                    "items_in_cart":    r.items_in_cart,
                    "total_cart_value": r.total_cart_value,
                    "churn_prediction": r.churn_prediction,
                    "churn_probability":round(r.churn_probability * 100, 1),
                    "risk_level": (
                        "High"   if r.churn_probability >= 0.65 else
                        "Medium" if r.churn_probability >= 0.40 else
                        "Low"
                    ),
                    "created_at": r.created_at.isoformat(),
                }
                for r in records
            ],
            "total": len(records),
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/history")
def dashboard_history(db: Session = Depends(get_db), limit: int = 100):
    try:
        records = (
            db.query(EmailHistory)
            .order_by(EmailHistory.created_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "history": [
                {
                    "id":               r.id,
                    "customer_id":      r.customer_id,
                    "customer_name":    r.customer_name,
                    "customer_email":   r.customer_email,
                    "churn_probability":round(r.churn_probability * 100, 1),
                    "email_subject":    r.email_subject,
                    "send_status":      r.send_status,
                    "sent_manually":    r.sent_manually,
                    "discount_code":    r.discount_code,
                    "sent_at":          r.sent_at.isoformat() if r.sent_at else None,
                    "created_at":       r.created_at.isoformat(),
                }
                for r in records
            ],
            "total":        len(records),
            "sent_count":   sum(1 for r in records if r.send_status == "sent"),
            "failed_count": sum(1 for r in records if r.send_status == "failed"),
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/sync_logs")
def sync_logs(db: Session = Depends(get_db), limit: int = 20):
    logs = (
        db.query(SyncLog)
        .order_by(SyncLog.synced_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "logs": [
            {
                "id":              l.id,
                "sync_type":       l.sync_type,
                "records_fetched": l.records_fetched,
                "records_saved":   l.records_saved,
                "status":          l.status,
                "error":           l.error_message,
                "synced_at":       l.synced_at.isoformat(),
            }
            for l in logs
        ]
    }


@app.get("/app")
def serve_frontend():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Frontend not found."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
