"""
app.py — Specialty Pharmacy Claims Analytics Dashboard
Run: streamlit run app/app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os, sys

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title  = "SP Claims Analytics",
    page_icon   = "💊",
    layout      = "wide",
    initial_sidebar_state = "expanded",
)

# ── data loading (CSV — works without live DB) ────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

@st.cache_data
def load_data():
    claims    = pd.read_csv(f"{DATA_DIR}/claims.csv",            parse_dates=["service_date"])
    patients  = pd.read_csv(f"{DATA_DIR}/patients.csv",          parse_dates=["enrollment_date"])
    drugs     = pd.read_csv(f"{DATA_DIR}/drugs.csv")
    payers    = pd.read_csv(f"{DATA_DIR}/payers.csv")
    prescribers = pd.read_csv(f"{DATA_DIR}/prescribers.csv")
    dispensing  = pd.read_csv(f"{DATA_DIR}/dispensing_events.csv")

    # Join enriched claims
    enriched = (
        claims
        .merge(drugs,       on="drug_id",       how="left")
        .merge(patients,    on="patient_id",     how="left", suffixes=("","_pt"))
        .merge(payers,      on="payer_id",       how="left", suffixes=("","_py"))
        .merge(prescribers, on="prescriber_id",  how="left", suffixes=("","_pr"))
    )
    enriched["month"]   = enriched["service_date"].dt.to_period("M").dt.to_timestamp()
    enriched["quarter"] = enriched["service_date"].dt.to_period("Q").dt.to_timestamp()
    enriched["year"]    = enriched["service_date"].dt.year
    return enriched, dispensing, drugs, payers

df, dispensing, drugs_ref, payers_ref = load_data()

# ── colour palette ────────────────────────────────────────────────────────────
COLOURS = {
    "Approved": "#2ecc71", "Denied": "#e74c3c",
    "Pending": "#f39c12",  "primary": "#1a3c5e",
}
THERAPY_COLOURS = px.colors.qualitative.Bold

# ── sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.image("https://img.icons8.com/color/96/000000/pharmacy-shop.png", width=60)
st.sidebar.title("🔍 Filters")

years         = sorted(df["year"].unique())
sel_years     = st.sidebar.multiselect("Year", years, default=years)
therapy_areas = sorted(df["therapy_area"].dropna().unique())
sel_therapy   = st.sidebar.multiselect("Therapy Area", therapy_areas, default=therapy_areas)
payer_types   = sorted(df["payer_type"].dropna().unique())
sel_payer     = st.sidebar.multiselect("Payer Type", payer_types, default=payer_types)
sel_status    = st.sidebar.multiselect(
    "Claim Status", ["Approved","Denied","Pending"],
    default=["Approved","Denied","Pending"]
)

# ── apply filters ─────────────────────────────────────────────────────────────
mask = (
    df["year"].isin(sel_years) &
    df["therapy_area"].isin(sel_therapy) &
    df["payer_type"].isin(sel_payer) &
    df["claim_status"].isin(sel_status)
)
fdf = df[mask].copy()

# ── header ────────────────────────────────────────────────────────────────────
st.title("💊 Specialty Pharmacy Claims Analytics")
st.caption("Executive dashboard — claims volume, spend, denial analysis, dispensing performance")
st.divider()

# ── KPI cards ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)

total        = len(fdf)
approved     = (fdf["claim_status"] == "Approved").sum()
denied       = (fdf["claim_status"] == "Denied").sum()
approval_rt  = approved / total * 100 if total else 0
total_billed = fdf["billed_amount_usd"].sum()
total_paid   = fdf["paid_amount_usd"].sum()

k1.metric("Total Claims",     f"{total:,}")
k2.metric("Approved",         f"{approved:,}")
k3.metric("Denied",           f"{denied:,}")
k4.metric("Approval Rate",    f"{approval_rt:.1f}%")
k5.metric("Total Billed",     f"${total_billed/1e6:.1f}M")
k6.metric("Total Paid",       f"${total_paid/1e6:.1f}M")

st.divider()

# ── tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Trends", "💊 Drug Analysis", "🏦 Payer Mix",
    "🚚 Dispensing", "🔎 Data Quality"
])

# ══ TAB 1 — TRENDS ═══════════════════════════════════════════════════════════
with tab1:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Monthly Claims Volume by Status")
        monthly = (fdf.groupby(["month","claim_status"])
                   .size().reset_index(name="count"))
        fig = px.bar(monthly, x="month", y="count", color="claim_status",
                     color_discrete_map=COLOURS,
                     labels={"month":"Month","count":"Claims","claim_status":"Status"},
                     barmode="stack")
        fig.update_layout(legend_title="Status", xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Monthly Paid Amount by Therapy Area")
        spend = (fdf[fdf["claim_status"]=="Approved"]
                 .groupby(["month","therapy_area"])["paid_amount_usd"]
                 .sum().reset_index())
        fig2 = px.area(spend, x="month", y="paid_amount_usd",
                       color="therapy_area",
                       color_discrete_sequence=THERAPY_COLOURS,
                       labels={"paid_amount_usd":"Paid ($)","therapy_area":"Therapy","month":"Month"})
        fig2.update_layout(legend_title="Therapy Area", xaxis_title=None)
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Quarterly Spend Trend — Billed vs Paid")
    qtr = (fdf.groupby("quarter")
           .agg(billed=("billed_amount_usd","sum"), paid=("paid_amount_usd","sum"))
           .reset_index())
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=qtr["quarter"], y=qtr["billed"], name="Billed", marker_color="#aed6f1"))
    fig3.add_trace(go.Bar(x=qtr["quarter"], y=qtr["paid"],   name="Paid",   marker_color=COLOURS["primary"]))
    fig3.update_layout(barmode="group", yaxis_title="Amount ($)", xaxis_title=None)
    st.plotly_chart(fig3, use_container_width=True)

# ══ TAB 2 — DRUG ANALYSIS ════════════════════════════════════════════════════
with tab2:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Top 10 Drugs by Total Paid")
        drug_spend = (fdf[fdf["claim_status"]=="Approved"]
                      .groupby(["brand_name","therapy_area"])["paid_amount_usd"]
                      .sum().reset_index()
                      .sort_values("paid_amount_usd", ascending=False).head(10))
        fig = px.bar(drug_spend, x="paid_amount_usd", y="brand_name",
                     color="therapy_area", orientation="h",
                     color_discrete_sequence=THERAPY_COLOURS,
                     labels={"paid_amount_usd":"Total Paid ($)","brand_name":"Drug"})
        fig.update_layout(yaxis=dict(autorange="reversed"), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Denial Rate by Drug")
        denial = (fdf.groupby("brand_name")
                  .apply(lambda x: pd.Series({
                      "denial_rate": (x["claim_status"]=="Denied").mean()*100,
                      "total_claims": len(x)
                  })).reset_index()
                  .sort_values("denial_rate", ascending=False).head(10))
        fig2 = px.bar(denial, x="brand_name", y="denial_rate",
                      color="denial_rate",
                      color_continuous_scale=["#2ecc71","#f39c12","#e74c3c"],
                      labels={"denial_rate":"Denial Rate (%)","brand_name":"Drug"})
        fig2.update_layout(coloraxis_showscale=False, xaxis_tickangle=-30)
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Denial Reasons Breakdown")
        den = fdf[fdf["claim_status"]=="Denied"]["denial_reason"].value_counts().reset_index()
        den.columns = ["Reason","Count"]
        fig3 = px.pie(den, values="Count", names="Reason",
                      color_discrete_sequence=px.colors.qualitative.Set2, hole=0.4)
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        st.subheader("Claims by Therapy Area")
        therapy = fdf["therapy_area"].value_counts().reset_index()
        therapy.columns = ["Therapy Area","Claims"]
        fig4 = px.pie(therapy, values="Claims", names="Therapy Area",
                      color_discrete_sequence=THERAPY_COLOURS, hole=0.4)
        st.plotly_chart(fig4, use_container_width=True)

# ══ TAB 3 — PAYER MIX ════════════════════════════════════════════════════════
with tab3:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Total Paid by Payer")
        payer_spend = (fdf[fdf["claim_status"]=="Approved"]
                       .groupby(["payer_name","payer_type"])["paid_amount_usd"]
                       .sum().reset_index()
                       .sort_values("paid_amount_usd", ascending=False))
        fig = px.bar(payer_spend, x="payer_name", y="paid_amount_usd",
                     color="payer_type",
                     labels={"paid_amount_usd":"Total Paid ($)","payer_name":"Payer"},
                     color_discrete_sequence=["#2980b9","#e67e22"])
        fig.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Denial Rate by Payer")
        payer_denial = (fdf.groupby("payer_name")
                        .apply(lambda x: pd.Series({
                            "denial_rate": (x["claim_status"]=="Denied").mean()*100,
                            "volume": len(x)
                        })).reset_index())
        fig2 = px.scatter(payer_denial, x="volume", y="denial_rate",
                          text="payer_name", size="volume",
                          color="denial_rate",
                          color_continuous_scale=["#2ecc71","#e74c3c"],
                          labels={"volume":"Claim Volume","denial_rate":"Denial Rate (%)"})
        fig2.update_traces(textposition="top center")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Insurance Type Mix — Patient Population")
    ins_mix = fdf.drop_duplicates("patient_id")["insurance_type"].value_counts().reset_index()
    ins_mix.columns = ["Insurance Type","Patients"]
    fig3 = px.bar(ins_mix, x="Insurance Type", y="Patients",
                  color="Insurance Type",
                  color_discrete_sequence=["#2980b9","#27ae60","#e67e22"])
    st.plotly_chart(fig3, use_container_width=True)

# ══ TAB 4 — DISPENSING PERFORMANCE ═══════════════════════════════════════════
with tab4:
    disp_enriched = (dispensing
                     .merge(df[["claim_id","therapy_area","brand_name"]].drop_duplicates(),
                            on="claim_id", how="left"))

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Avg Days to Deliver by Method")
        d_perf = (disp_enriched.groupby("delivery_method")
                  .agg(avg_ship=("days_to_ship","mean"),
                       avg_deliver=("days_to_deliver","mean"),
                       count=("dispense_id","count"))
                  .reset_index())
        fig = px.bar(d_perf, x="delivery_method",
                     y=["avg_ship","avg_deliver"],
                     barmode="group",
                     labels={"value":"Days","delivery_method":"Method","variable":"Metric"},
                     color_discrete_map={"avg_ship":"#aed6f1","avg_deliver":"#1a3c5e"})
        fig.update_layout(xaxis_tickangle=-20)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Delivery Method Distribution")
        method_dist = disp_enriched["delivery_method"].value_counts().reset_index()
        method_dist.columns = ["Method","Count"]
        fig2 = px.pie(method_dist, values="Count", names="Method",
                      hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Refill Number Distribution (Adherence Indicator)")
    fig3 = px.histogram(disp_enriched, x="refill_number", nbins=10,
                        color_discrete_sequence=["#1a3c5e"],
                        labels={"refill_number":"Refill Number","count":"Patients"})
    fig3.update_layout(bargap=0.1)
    st.plotly_chart(fig3, use_container_width=True)

# ══ TAB 5 — DATA QUALITY ═════════════════════════════════════════════════════
with tab5:
    st.subheader("🔎 Data Quality Checks")

    checks = {
        "Claims with missing diagnosis code": df["diagnosis_code"].isna().sum(),
        "Approved claims with $0 paid":       ((df["claim_status"]=="Approved") & (df["paid_amount_usd"]==0)).sum(),
        "Paid amount exceeds billed":         (df["paid_amount_usd"] > df["billed_amount_usd"]).sum(),
        "Missing denial reason on denials":   ((df["claim_status"]=="Denied") & df["denial_reason"].isna()).sum(),
        "Patients with missing state":        df["state"].isna().sum(),
    }
    dq = pd.DataFrame(list(checks.items()), columns=["Check","Issues Found"])
    dq["Status"] = dq["Issues Found"].apply(lambda x: "✅ Pass" if x == 0 else "⚠️ Review")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.dataframe(dq.style.applymap(
            lambda v: "color: green" if "Pass" in str(v) else "color: orange",
            subset=["Status"]
        ), use_container_width=True, hide_index=True)

    with col2:
        pass_count = (dq["Issues Found"] == 0).sum()
        total_checks = len(dq)
        score = pass_count / total_checks * 100
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": "Data Quality Score"},
            gauge={
                "axis":  {"range": [0, 100]},
                "bar":   {"color": "#2ecc71" if score > 80 else "#e74c3c"},
                "steps": [
                    {"range": [0, 60],   "color": "#fadbd8"},
                    {"range": [60, 80],  "color": "#fdebd0"},
                    {"range": [80, 100], "color": "#d5f5e3"},
                ],
            },
            number={"suffix": "%"},
        ))
        fig.update_layout(height=280)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Raw Claims Sample (filtered)")
    st.dataframe(
        fdf[["claim_id","patient_id","brand_name","claim_status",
             "billed_amount_usd","paid_amount_usd","service_date","payer_name"]]
        .head(50),
        use_container_width=True, hide_index=True
    )

# ── footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Specialty Pharmacy Claims Analytics · Built with Python, PostgreSQL & Streamlit · Portfolio Project — sumaksharika.com")
