# Smart-Shop AI Engine 🛒

End-to-end cart abandonment prediction + personalised win-back email system for Sia Glow Beauty (Shopify).

---

## Stack

| Layer | Tech |
|-------|------|
| ML    | Scikit-learn Random Forest |
| API   | FastAPI + Uvicorn |
| DB    | PostgreSQL 16 + SQLAlchemy |
| LLM   | Groq (LLaMA-3) |
| Email | Gmail SMTP |
| Shop  | Shopify Admin API 2025-01 |
| UI    | Vanilla HTML/CSS/JS (no framework) |
| Infra | Docker + Docker Compose |

---

## Project Structure

```
smart-shop/
├── backend/
│   ├── main.py              # FastAPI — all endpoints
│   ├── database.py          # SQLAlchemy models + init
│   ├── shopify_client.py    # Shopify token exchange + data fetch
│   ├── ml_model.py          # Random Forest inference
│   ├── ai_engine.py         # Groq LLM email generation
│   ├── email_service.py     # Gmail SMTP sender
│   ├── models/              # random_forest.pkl + scaler.pkl (generated)
│   └── requirements.txt
├── frontend/
│   └── index.html           # Full dashboard SPA
├── notebooks/
│   └── eda_and_model.ipynb  # EDA + model training notebook
├── train_model.py           # One-time model training script
├── Dockerfile
├── docker-compose.yml

```

---

## Quick Start (Local — No Docker)

### 1. Prerequisites
- Python 3.11 venv activated
- PostgreSQL running with `sshop_db` database created
- `.env` file filled in (already done)

### 2. Install dependencies
```powershell
cd smart-shop
venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

### 3. Train the ML model (run once)
Copy your dataset CSV into the notebooks folder first, then:
```powershell
python train_model.py
# or with explicit path:
python train_model.py notebooks/online_shoppers_intention.csv
```
This saves `backend/models/random_forest.pkl` and `backend/models/scaler.pkl`.

### 4. Initialise the database
```powershell
cd backend
python database.py
# Prints: ✅ All tables created / verified in sshop_db
```

### 5. Start the API
```powershell
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Open the dashboard
Open `frontend/index.html` directly in your browser, **or** visit:
```
http://localhost:8000/app
```

### 7. View API docs
```
http://localhost:8000/docs
```

---

## Quick Start (Docker)

```powershell
# From smart-shop/ root:
docker-compose up --build
```

- API:       http://localhost:8000
- API docs:  http://localhost:8000/docs
- Dashboard: http://localhost:8000/app
- DB port:   localhost:5433 (mapped to avoid clash with local PG)

> **First run:** The model PKL files must exist before Docker starts.
> Run `python train_model.py` locally first, then `docker-compose up --build`.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/health` | API + DB health check |
| POST   | `/predict` | Run ML on a single customer |
| POST   | `/predict_and_email` | Predict + auto-send email if at risk |
| POST   | `/send_email/{customer_id}` | Manually send email (force option) |
| POST   | `/shopify/sync` | Fetch abandoned carts + run ML on all |
| GET    | `/shopify/info` | Store info + token status |
| GET    | `/dashboard/overview` | KPIs + chart data |
| GET    | `/dashboard/customers` | Customer list with predictions |
| GET    | `/dashboard/history` | Email send history |
| GET    | `/dashboard/sync_logs` | Last sync operations |

---

## Dashboard Pages

| Page | What it shows |
|------|---------------|
| **Overview** | KPI cards, monthly churn trend chart, risk distribution donut, top at-risk table |
| **Shopify Connect** | Store connection status, credentials form, one-click sync |
| **Customers** | All customers sorted by churn probability, send email buttons |
| **Email History** | Full log of all emails sent, status, timestamps |

---

## Environment Variables

```env
GROQ_API_KEY=           # Groq Cloud API key (free)
DATABASE_URL=           # postgresql://user:pass@host:port/dbname
SHOPIFY_SHOP=           # your-store (without .myshopify.com)
SHOPIFY_CLIENT_ID=      # From Shopify Dev Dashboard
SHOPIFY_CLIENT_SECRET=  # From Shopify Dev Dashboard
SHOPIFY_API_VERSION=    # e.g. 2025-01
GMAIL_ADDRESS=          # sender Gmail address
GMAIL_APP_PASSWORD=     # Gmail App Password (not account password)
SENDER_NAME=            # Display name in emails
```

---

## Smoke Tests

```powershell
# Test DB connection
python -c "
import psycopg2
conn = psycopg2.connect('db connection')
print('DB OK'); conn.close()
"

# Test Shopify connection
cd backend && python shopify_client.py

# Test LLM email generation
cd backend && python ai_engine.py

# Test email sending (sends to your own Gmail)
cd backend && python email_service.py
```

---

## Grading Checklist

- [x] Phase 1 — EDA + 6 visualisations + Random Forest vs SVM comparison
- [x] Phase 1 — Precision as primary metric (RF: 0.776, SVM: 0.530)
- [x] Phase 2 — PostgreSQL + SQLAlchemy (`database.py`, 4 tables)
- [x] Phase 3 — Groq LLM dynamic prompting (`ai_engine.py`)
- [x] Phase 3 — Full email pipeline with Gmail SMTP (`email_service.py`)
- [x] Phase 4 — FastAPI `/predict_and_email` endpoint (`main.py`)
- [x] Phase 4 — Dockerfile + requirements.txt
- [x] Bonus  — Full dashboard frontend (Overview / Connect / Customers / History)
- [x] Bonus  — Force-send option for low-risk customers
