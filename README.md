# 💊 Specialty Pharmacy Claims Analytics

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue?logo=postgresql)](https://postgresql.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35-red?logo=streamlit)](https://streamlit.io)
[![Plotly](https://img.shields.io/badge/Plotly-5.22-purple?logo=plotly)](https://plotly.com)

An end-to-end **Specialty Pharmacy (SP) Claims Analytics** pipeline — from synthetic data generation to a production-grade PostgreSQL data warehouse to an interactive executive dashboard. Built to demonstrate pharmacy domain expertise, SQL analytics, ETL engineering, and data governance.

---

## 🗂️ Project Structure

```
sp-claims-analytics/
├── data/
│   └── generate_data.py          # Synthetic SP claims data generator
├── sql/
│   ├── schema.sql                # PostgreSQL schema with ER model, indexes, triggers
│   └── analytics_queries.sql     # 11 production-ready KPI queries
├── etl/
│   └── etl_pipeline.py           # Full ETL: Extract → Validate → Transform → Load
├── app/
│   └── app.py                    # Streamlit executive dashboard (5 tabs)
├── requirements.txt
└── README.md
```

---

## 🏗️ ER Model

```
         ┌─────────────┐
         │   patients  │
         └──────┬──────┘
                │ 1
                │
    ┌───────────▼────────────┐
    │         claims         │◄──────── payers
    │  (central fact table)  │◄──────── drugs
    └───────────┬────────────┘◄──────── prescribers
                │ 1
                │
         ┌──────▼──────────────┐
         │  dispensing_events  │
         └─────────────────────┘
```

**Tables:** `patients` · `drugs` · `prescribers` · `payers` · `claims` · `dispensing_events` · `audit_log`

---

## 📊 Dashboard Features

| Tab | What it shows |
|---|---|
| **📈 Trends** | Monthly claims volume, therapy area spend (area chart), quarterly billed vs paid |
| **💊 Drug Analysis** | Top 10 drugs by spend, denial rate by drug, denial reason breakdown, therapy mix |
| **🏦 Payer Mix** | Spend by payer, denial rate scatter, insurance type distribution |
| **🚚 Dispensing** | Days-to-ship/deliver by method, refill adherence histogram |
| **🔎 Data Quality** | Automated DQ checks with pass/fail gauge, raw data explorer |

---

## ⚙️ Setup & Run

### 1. Clone & install
```bash
git clone https://github.com/sumaksharikaa/sp-claims-analytics.git
cd sp-claims-analytics
pip install -r requirements.txt
```

### 2. Generate synthetic data
```bash
python data/generate_data.py
```

### 3. Set up PostgreSQL (optional — dashboard runs on CSV without DB)
```bash
# Create database
createdb sp_claims_db

# Run schema
psql -d sp_claims_db -f sql/schema.sql

# Configure env
export DB_HOST=localhost
export DB_USER=postgres
export DB_PASSWORD=your_password
export DB_NAME=sp_claims_db

# Run ETL
python etl/etl_pipeline.py
```

### 4. Launch dashboard
```bash
streamlit run app/app.py
```

---

## 🔑 Key Technical Concepts Demonstrated

| Concept | Implementation |
|---|---|
| **ER Modeling** | 6-table normalized schema with FK constraints and composite indexes |
| **Data Governance** | Audit log table with INSERT/UPDATE/DELETE triggers, JSONB change tracking |
| **ETL Pipeline** | Extract → validate → transform → upsert with conflict resolution |
| **Data Quality** | 5 automated DQ checks with pass/fail scoring |
| **PL/pgSQL** | `update_timestamp()` and `log_claims_audit()` stored functions |
| **Advanced SQL** | CTEs, window functions, PERCENTILE_CONT, conditional aggregation |
| **Pharmacy Domain** | SP claims lifecycle, specialty drugs, prior auth, cold chain, dispensing |

---

## 📈 Sample KPIs Tracked

- **Approval Rate** — claims approved / total claims
- **Denial Rate by Drug & Payer** — identifies problem patterns
- **Avg Days to Deliver** — dispensing SLA monitoring
- **Patient Adherence Rate** — refill compliance (≥3 fills = adherent)
- **Payment Ratio** — paid / billed (payer reimbursement efficiency)
- **Quarterly YoY Spend** — with QoQ change using window functions

---

## 🗃️ Dataset

Synthetic dataset generated with realistic specialty pharmacy patterns:
- **500** patients · **10** specialty drugs · **80** prescribers · **7** payers
- **2,000** claims (2022–2024) · **~1,300** dispensing events
- Therapy areas: Oncology, Immunology, Neurology, Dermatology, Hepatology

---

## 🔗 Related Projects

- [Drug Utilization & Formulary Analytics](https://github.com/sumaksharikaa/drug-utilization-analytics)
- [Healthcare Data Quality & Governance Pipeline](https://github.com/sumaksharikaa/healthcare-dq-governance)
- [Pharmacy Readmission Risk Predictor](https://github.com/sumaksharikaa/pharmacy-readmission-risk)
- [Financial Risk Dashboard](https://github.com/sumaksharikaa/financial-risk-dashboard)

---

*Built by [Sumaksharika Nainavarapu](https://sumaksharika.com) · B.S. Pharmacy · M.S. Health Informatics & Analytics*
