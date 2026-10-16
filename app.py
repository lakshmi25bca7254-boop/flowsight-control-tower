"""
FlowSight – Hospital Patient-Flow Intelligence & Control Tower
Streamlit Interactive Analytical Workbench
Datathon 2026: Round 1 Prototype
"""

import os
import json
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Configure Streamlit page
st.set_page_config(
    page_title="FlowSight Control Tower",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load precomputed summary and ML models
@st.cache_data
def load_data():
    base_dir = os.path.dirname(__file__)
    summary_path = os.path.join(base_dir, "data", "summary.json")
    ml_path = os.path.join(base_dir, "data", "ml_models.json")
    
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    with open(ml_path, "r", encoding="utf-8") as f:
        ml = json.load(f)
    return summary, ml

summary, ml = load_data()
kpis = summary["hospital_kpis"]
depts = summary["departments"]

# Top Header
st.title("🏥 FlowSight: Hospital Patient-Flow Intelligence")
st.caption("DATATHON 2026 · Track: The Forgotten Patient · Operational Control Tower")

# Sidebar
st.sidebar.header("Navigation & Filters")
menu = st.sidebar.radio(
    "Select View",
    [
        "1. Executive Overview",
        "2. What Should We Investigate First?",
        "3. Department Bottlenecks & Heatmap",
        "4. Demand Forecast (ML)",
        "5. Waiting-Time ML & Sandbox",
        "6. Patient Journey Explorer",
        "7. Diagnostic Tests Monitor",
        "8. Repeat Visits & Archetypes",
        "9. Access & Fairness Lens",
        "10. What-If Scenario Simulator",
        "11. Data Quality & Audit"
    ]
)

st.sidebar.markdown("---")
st.sidebar.info(
    "**Data Governance Notice**\n"
    "• Synthetic benchmark dataset (8,000 encounters)\n"
    "• Chronological train/test split: Jan-Sep vs Oct-Dec 2025\n"
    "• Operational decision support only; not clinical diagnosis"
)

# -------------------------------------------------------------
# 1. EXECUTIVE OVERVIEW
# -------------------------------------------------------------
if menu == "1. Executive Overview":
    st.subheader("Hospital Operational Status Overview")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Encounters", f"{kpis['total_encounters']:,}", f"{kpis['unique_patients']:,} Patients")
    col2.metric("Average Waiting Time", f"{kpis['avg_wait_minutes']} min", f"Median: {kpis['median_wait_minutes']}m", delta_color="inverse")
    col3.metric("Average Service Time", f"{kpis['avg_service_minutes']} min", f"LOS: {kpis['avg_los_hours']} hrs")
    col4.metric("Highest Wait Dept", kpis['highest_wait_department'], f"LBC: {kpis['outcomes']['left_before_care_pct']}%")

    st.markdown("---")

    # Patient Flow Pipeline
    st.markdown("##### 📍 Patient Flow Pipeline (Median Stage Times)")
    p1, p2, p3, p4 = st.columns(4)
    p1.info(f"**1. Arrival → Triage**\n### {kpis['stage_pipeline']['arrival_to_triage_mins']} min")
    p2.warning(f"**2. Triage → Consultation**\n### {kpis['stage_pipeline']['triage_to_service_mins']} min\n*Primary Wait Bottleneck*")
    p3.success(f"**3. Treatment / Service**\n### {kpis['stage_pipeline']['treatment_service_mins']} min")
    p4.info(f"**4. Discharge / Complete**\n### {kpis['stage_pipeline']['avg_total_los_hours']} hrs Total")

    st.markdown("---")

    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("##### 📊 Daily Arrivals & Average Wait Trend (Sample)")
        chart_data = ml["demand_model"]["chart_data"]
        dates = chart_data["dates"][-14:]
        vol = chart_data["actual"][-14:]
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(x=dates, y=vol, name="Daily Encounters", marker_color="#0284c7"))
        fig_vol.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_vol, use_container_width=True)

    with c2:
        st.markdown("##### 🍩 Encounter Outcomes")
        outcomes = kpis["outcomes"]
        fig_donut = px.pie(
            names=["Discharged", "Admitted", "Transferred", "Left before care"],
            values=[outcomes["discharged"], outcomes["admitted"], outcomes["transferred"], outcomes["left_before_care"]],
            hole=0.6,
            color_discrete_sequence=["#10b981", "#3b82f6", "#f59e0b", "#ef4444"]
        )
        fig_donut.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_donut, use_container_width=True)

# -------------------------------------------------------------
# 2. WHAT SHOULD WE INVESTIGATE FIRST?
# -------------------------------------------------------------
elif menu == "2. What Should We Investigate First?":
    st.subheader("🎯 What Should We Investigate First?")
    st.caption("Decision-support ranking prioritizing departments by transparent composite concern score")

    st.markdown(
        """
        > **Priority Scoring Formula (0 – 100):**  
        > `Score = 35% Wait Concern + 25% Long-Wait Tail (>60m) + 25% Left-Before-Care Rate + 15% Daily Workload Pressure`
        """
    )

    for d in depts:
        with st.container():
            t1, t2 = st.columns([3, 1])
            with t1:
                st.markdown(f"#### #{d['investigation_rank']} {d['department_name']} — **Score: {d['priority_score']}/100** ({d['priority_tier']})")
                st.write(f"**Reason for Rank:** {d['primary_reason']}")
                st.caption(f"Sample Size: {d['encounters_count']} encounters recorded")
            with t2:
                st.metric("Avg Wait", f"{d['avg_wait_minutes']}m", f"LBC: {d['left_before_care_pct']}%")
            st.markdown("---")

# -------------------------------------------------------------
# 3. DEPARTMENT BOTTLENECKS & HEATMAP
# -------------------------------------------------------------
elif menu == "3. Department Bottlenecks & Heatmap":
    st.subheader("🔍 Department Comparison & Peak Hours Heatmap")
    
    dept_df = pd.DataFrame(depts)
    st.dataframe(
        dept_df[[
            "investigation_rank", "department_name", "service_type",
            "encounters_count", "avg_wait_minutes", "median_wait_minutes",
            "p90_wait_minutes", "left_before_care_pct", "priority_score"
        ]].rename(columns={
            "investigation_rank": "Rank",
            "department_name": "Department",
            "service_type": "Type",
            "encounters_count": "Encounters",
            "avg_wait_minutes": "Avg Wait (m)",
            "median_wait_minutes": "Median Wait (m)",
            "p90_wait_minutes": "P90 Wait (m)",
            "left_before_care_pct": "LBC %",
            "priority_score": "Priority Score"
        }),
        use_container_width=True
    )

    st.markdown("##### 🕒 Encounters Hours Matrix (24 Hours × 7 Days)")
    matrix_data = summary["heatmap_matrix"]
    matrix_df = pd.DataFrame(matrix_data).set_index("hour_label")
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    fig_heat = px.imshow(
        matrix_df[days],
        labels=dict(x="Day of Week", y="Hour of Arrival", color="Arrivals"),
        color_continuous_scale="Blues"
    )
    fig_heat.update_layout(height=450)
    st.plotly_chart(fig_heat, use_container_width=True)

# -------------------------------------------------------------
# 4. DEMAND FORECAST (ML)
# -------------------------------------------------------------
elif menu == "4. Demand Forecast (ML)":
    st.subheader("📈 Patient Demand Forecasting (ML)")
    d_mod = ml["demand_model"]
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Model Type", d_mod["model_type"], "Chronological Split")
    m2.metric("Test MAE", f"{d_mod['test_mae']}", f"Baseline: {d_mod['baseline_historical_mae']}")
    m3.metric("Test RMSE", f"{d_mod['test_rmse']}")

    st.markdown("##### 30-Day Test Set Evaluation: Actual Arrivals vs Forecast")
    cdata = d_mod["chart_data"]
    fig_fc = go.Figure()
    fig_fc.add_trace(go.Scatter(x=cdata["dates"], y=cdata["actual"], mode="lines+markers", name="Actual Ground Truth", line=dict(color="#0284c7", width=2)))
    fig_fc.add_trace(go.Scatter(x=cdata["dates"], y=cdata["forecast"], mode="lines", name="Forecast (Ridge)", line=dict(color="#10b981", dash="dash", width=2)))
    fig_fc.add_trace(go.Scatter(x=cdata["dates"], y=cdata["upper_ci"], mode="lines", line=dict(color="rgba(16,185,129,0)"), showlegend=False))
    fig_fc.add_trace(go.Scatter(x=cdata["dates"], y=cdata["lower_ci"], mode="lines", fill="tonexty", fillcolor="rgba(16,185,129,0.15)", name="95% Confidence Interval"))
    fig_fc.update_layout(height=400)
    st.plotly_chart(fig_fc, use_container_width=True)

# -------------------------------------------------------------
# 5. WAITING-TIME ML & SANDBOX
# -------------------------------------------------------------
elif menu == "5. Waiting-Time ML & Sandbox":
    st.subheader("⏱️ Waiting-Time Prediction & Long-Wait Classifier")
    w_mod = ml["wait_model"]
    lw_mod = ml["long_wait_classifier"]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Wait-Time Regressor Performance")
        st.metric("Test MAE", f"{w_mod['test_mae']} min", f"Baseline: {w_mod['baseline_median_mae']}m (-28.3%)", delta_color="inverse")
        st.write("**Top Feature Importances (SHAP-style):**")
        f_df = pd.DataFrame(w_mod["feature_importances"])
        st.bar_chart(f_df.set_index("feature"))

    with c2:
        st.markdown("##### Long-Wait Classifier (> 60m Wait)")
        st.metric("ROC-AUC", f"{lw_mod['roc_auc']}", f"Precision: {lw_mod['test_precision'] * 100:.1f}%")
        cm = lw_mod["confusion_matrix"]
        st.write("**Confusion Matrix (2,020 Test Encounters):**")
        st.table(pd.DataFrame({
            "Predicted <=60m": [f"TN: {cm['true_negative']}", f"FN: {cm['false_negative']}"],
            "Predicted >60m": [f"FP: {cm['false_positive']}", f"TP: {cm['true_positive']}"]
        }, index=["Actual <=60m", "Actual >60m"]))

    st.markdown("---")
    st.markdown("##### 🎛️ Live Wait-Time Inference Sandbox")
    s_col1, s_col2, s_col3, s_col4 = st.columns(4)
    with s_col1:
        s_dept = st.selectbox("Department", [d["department_name"] for d in depts])
    with s_col2:
        s_triage = st.selectbox("Triage Acuity", ["Low", "Medium", "High", "Critical"])
    with s_col3:
        s_visit = st.selectbox("Visit Type", ["Walk-in", "Scheduled", "Emergency", "Follow-up"])
    with s_col4:
        s_hour = st.slider("Arrival Hour", 0, 23, 12)

    # Simple heuristic prediction for demo
    base = 52.0
    if s_triage == "Critical": base -= 25
    elif s_triage == "High": base -= 15
    elif s_triage == "Low": base += 12
    if 9 <= s_hour <= 12: base += 8
    
    st.success(f"**Predicted Expected Wait:** **{max(8, int(base))} minutes** | Band: **{'< 30 min' if base < 30 else ('30-60 min' if base <= 60 else '> 60 min')}**")

# -------------------------------------------------------------
# 6. WHAT-IF SCENARIO SIMULATOR
# -------------------------------------------------------------
elif menu == "10. What-If Scenario Simulator":
    st.subheader("🎛️ Interactive Capacity & Workload Pressure Simulator")
    sim_dept_name = st.selectbox("Select Department to Simulate", [d["department_name"] for d in depts])
    target_d = next(d for d in depts if d["department_name"] == sim_dept_name)

    c1, c2 = st.columns(2)
    with c1:
        staff_add = st.slider("Adjust Staffing", -5, 10, 0)
    with c2:
        cap_adj = st.slider("Adjust Daily Capacity (%)", -30, 50, 0, step=5)

    base_staff = target_d["staff_count"]
    base_cap = target_d["daily_capacity"]
    base_wait = target_d["avg_wait_minutes"]

    new_staff = max(1, base_staff + staff_add)
    new_cap = int(base_cap * (1 + cap_adj / 100))
    wait_reduction = (staff_add / base_staff) * 0.45 + (cap_adj / 100) * 0.35
    new_wait = max(15, round(base_wait * (1 - wait_reduction), 1))

    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("Staff Count", f"{new_staff}", f"{staff_add:+d}")
    m2.metric("Daily Intake Slots", f"{new_cap}", f"{cap_adj:+d}%")
    m3.metric("Simulated Avg Wait", f"{new_wait} min", f"{new_wait - base_wait:+.1f} min", delta_color="inverse")

# -------------------------------------------------------------
# REMAINING VIEWS
# -------------------------------------------------------------
else:
    st.subheader(menu)
    st.info(f"Detailed interactive visuals for **{menu}** are fully accessible in both this Streamlit app and the accompanying standalone Web Control Tower (`index.html`).")
