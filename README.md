# FlowSight: Hospital Patient-Flow Intelligence & Control Tower

> **DATATHON 2026 · Track: The Forgotten Patient**  
> Operational Patient-Flow Decision-Support System combining arrival telemetry, diagnostic turnaround monitoring, and machine learning delay forecasting.

---

## 🏥 Overview

Hospitals frequently manage clinical departments in operational silos, causing scan and lab bottlenecks to cascade into delayed consultations, blocked beds, and inflated waiting times. **FlowSight** provides an end-to-end control tower to answer one central operational question:

> *"What will get delayed next, why, and what should we investigate first?"*

---

## 🌟 Key Features

1. **Executive Operations Dashboard**: High-level KPIs (8,000 encounters, 2,000 unique patients, 52.0m avg wait), stage pipeline milestones, daily volume/wait trend combo chart, and outcome breakdown.
2. **"What Should We Investigate First?"**: Transparent composite **Investigation Priority Score (0–100)**:
   $$\text{Score} = 35\% \cdot \text{Wait Concern} + 25\% \cdot \text{Long-Wait Tail} + 25\% \cdot \text{Left-Before-Care} + 15\% \cdot \text{Workload Pressure}$$
3. **Automated Bottleneck Alerts**: Rules-based operational alerts with baselines, deviations, sample size evidence, and actionable recommendations.
4. **Department Bottlenecks & 24h × 7d Heatmap Matrix**: Benchmarking across all 12 hospital departments with interactive department and visit-type filters.
5. **Demand Forecasting (ML)**: Chronological Ridge regression model (Jan–Sep 2025 train, Oct–Dec 2025 test) with 95% confidence intervals and peak-demand period advisories.
6. **Wait-Time Prediction & Long-Wait Classifier (>60 min)**: Random Forest model achieving **14.06 min Test MAE** (+28.3% error reduction over baseline) and classifier with **0.829 ROC-AUC / 72.1% Precision**.
7. **Live Interactive Prediction Sandbox**: Real-time simulation of expected wait minutes upon arrival.
8. **Patient Journey Explorer**: Sequential timeline visualizer (Arrival $\to$ Triage $\to$ Service $\to$ Discharge) with linked diagnostic test turnarounds.
9. **Diagnostic Lab Monitor**: Standalone turnaround tracker across 5,000 tests (6 test types × Urgent/Routine).
10. **Continuity & Archetype Clustering**: Unsupervised K-Means clustering into 4 operational patient archetypes.
11. **Access & Fairness Lens**: Observed associations across age groups, sex, insurance types, and home areas.
12. **What-If Scenario Simulator**: Interactive sliders for testing staff and capacity reallocations.
13. **Data Quality & Audit**: Transparent verification and reporting of synthetic dataset anomalies.

---

## 🚀 Quick Start

### 1. Standalone Web Dashboard (Zero Dependencies)
Simply open `index.html` in any web browser:
```bash
# Or serve locally using Python:
python -m http.server 8088
```
Navigate to `http://localhost:8088/`.

### 2. Streamlit Analytical Workbench
```bash
pip install -r requirements.txt
streamlit run app.py
```

### 3. Retrain ML Models
```bash
python pipeline.py
```

---

## 🛡️ Data Governance & Integrity Principles
- **Synthetic Data**: Developed for educational benchmarking in Datathon 2026.
- **Chronological Split**: Models are evaluated strictly on future Q4 2025 data to eliminate lookahead bias.
- **Operational Decision Support**: System assists queue management; it does not provide medical diagnosis or treatment advice.
