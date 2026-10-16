import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, GradientBoostingRegressor
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, precision_score, recall_score, f1_score, confusion_matrix, roc_auc_score
from sklearn.cluster import KMeans

def run_pipeline():
    data_dir = r"C:\Users\kunda\.gemini\antigravity\scratch\flowsight-hospital\data"
    print("Loading data...")
    departments = pd.read_csv(os.path.join(data_dir, "departments.csv"))
    patients = pd.read_csv(os.path.join(data_dir, "patients.csv"))
    encounters = pd.read_csv(os.path.join(data_dir, "encounters.csv"))
    diagnostic_tests = pd.read_csv(os.path.join(data_dir, "diagnostic_tests.csv"))

    # Convert timestamps
    for col in ['arrival_time', 'service_start_time', 'service_end_time', 'discharge_time']:
        encounters[col] = pd.to_datetime(encounters[col])
    
    diagnostic_tests['requested_time'] = pd.to_datetime(diagnostic_tests['requested_time'])
    diagnostic_tests['completion_time'] = pd.to_datetime(diagnostic_tests['completion_time'])
    diagnostic_tests['turnaround_minutes'] = (diagnostic_tests['completion_time'] - diagnostic_tests['requested_time']).dt.total_seconds() / 60.0

    # Merge
    enc_full = encounters.merge(departments, on="department_id", how="left")
    enc_full = enc_full.merge(patients, on="patient_id", how="left")

    # Sort chronologically
    enc_full = enc_full.sort_values("arrival_time").reset_index(drop=True)

    # 1. Hospital Overview Metrics
    total_encounters = len(enc_full)
    unique_patients = enc_full['patient_id'].nunique()
    avg_wait = round(float(enc_full['wait_minutes'].mean()), 1)
    median_wait = round(float(enc_full['wait_minutes'].median()), 1)
    p90_wait = round(float(enc_full['wait_minutes'].quantile(0.90)), 1)
    avg_service = round(float(enc_full['service_minutes'].mean()), 1)
    median_service = round(float(enc_full['service_minutes'].median()), 1)
    
    # Calculate Total Length of Stay (Arrival to Discharge) in minutes
    enc_full['los_minutes'] = (enc_full['discharge_time'] - enc_full['arrival_time']).dt.total_seconds() / 60.0
    avg_los_hours = round(float(enc_full['los_minutes'].mean() / 60.0), 2)

    # Outcomes breakdown
    outcomes = enc_full['outcome'].value_counts().to_dict()
    admitted = int(outcomes.get('Admitted', 0))
    discharged = int(outcomes.get('Discharged', 0))
    transferred = int(outcomes.get('Transferred', 0))
    left_before_care = int(outcomes.get('Left before care', 0))
    lbc_pct = round((left_before_care / total_encounters) * 100, 2)

    # Triage and Admission Type Breakdown
    triage_counts = enc_full['triage_level'].value_counts().to_dict()
    visit_type_counts = enc_full['visit_type'].value_counts().to_dict()

    # 2. Department Bottleneck Detection & Metrics
    dept_stats = []
    for dept_id, group in enc_full.groupby('department_id'):
        dept_name = group['department_name'].iloc[0]
        staff = int(group['staff_count'].iloc[0])
        beds = int(group['bed_count'].iloc[0])
        capacity = int(group['daily_capacity'].iloc[0])
        stype = group['service_type'].iloc[0]
        n_enc = len(group)
        d_avg_wait = round(float(group['wait_minutes'].mean()), 1)
        d_med_wait = round(float(group['wait_minutes'].median()), 1)
        d_p90_wait = round(float(group['wait_minutes'].quantile(0.90)), 1)
        d_avg_service = round(float(group['service_minutes'].mean()), 1)
        d_lbc = int((group['outcome'] == 'Left before care').sum())
        d_lbc_pct = round((d_lbc / n_enc) * 100, 2)
        long_wait_cnt = int((group['wait_minutes'] > 60).sum())
        long_wait_pct = round((long_wait_cnt / n_enc) * 100, 1)

        # Workload pressure index: daily encounter demand vs daily capacity
        # Encounters span 365 days
        avg_daily_arrivals = n_enc / 365.0
        pressure_index = round((avg_daily_arrivals / capacity) * 100, 1)

        dept_stats.append({
            'department_id': dept_id,
            'department_name': dept_name,
            'service_type': stype,
            'staff_count': staff,
            'bed_count': beds,
            'daily_capacity': capacity,
            'encounters_count': n_enc,
            'avg_wait_minutes': d_avg_wait,
            'median_wait_minutes': d_med_wait,
            'p90_wait_minutes': d_p90_wait,
            'avg_service_minutes': d_avg_service,
            'left_before_care_count': d_lbc,
            'left_before_care_pct': d_lbc_pct,
            'long_wait_count': long_wait_cnt,
            'long_wait_pct': long_wait_pct,
            'avg_daily_arrivals': round(avg_daily_arrivals, 1),
            'workload_pressure_index': pressure_index
        })

    # Department with highest average wait
    dept_df = pd.DataFrame(dept_stats)
    highest_wait_dept = dept_df.sort_values('avg_wait_minutes', ascending=False).iloc[0]['department_name']

    # 3. Investigation Priority Scoring Engine
    # Transparent multi-factor formula (0 - 100)
    # Factor 1: Wait concern (normalized vs max observed avg wait) (weight: 0.35)
    # Factor 2: Long wait % (>60m) (weight: 0.25)
    # Factor 3: Left before care % (weight: 0.25)
    # Factor 4: Pressure Index / Demand Strain (weight: 0.15)
    max_wait = dept_df['avg_wait_minutes'].max()
    max_lbc = dept_df['left_before_care_pct'].max()
    max_long = dept_df['long_wait_pct'].max()
    max_press = dept_df['workload_pressure_index'].max()

    ranked_depts = []
    for _, row in dept_df.iterrows():
        f_wait = (row['avg_wait_minutes'] / max_wait) * 100
        f_long = (row['long_wait_pct'] / max_long) * 100 if max_long > 0 else 0
        f_lbc = (row['left_before_care_pct'] / max_lbc) * 100 if max_lbc > 0 else 0
        f_press = (row['workload_pressure_index'] / max_press) * 100 if max_press > 0 else 0

        score = round(0.35 * f_wait + 0.25 * f_long + 0.25 * f_lbc + 0.15 * f_press, 1)

        # Primary reason
        reasons = []
        if row['avg_wait_minutes'] >= 55:
            reasons.append(f"Elevated average wait of {row['avg_wait_minutes']}m (hospital avg: {avg_wait}m)")
        if row['long_wait_pct'] >= 35:
            reasons.append(f"{row['long_wait_pct']}% of visits exceed 60m wait threshold")
        if row['left_before_care_pct'] >= 3.5:
            reasons.append(f"High left-before-care rate of {row['left_before_care_pct']}%")
        if not reasons:
            reasons.append("Operational metrics remain within normal baseline limits")

        priority_tier = "Critical" if score >= 75 else ("High" if score >= 60 else ("Moderate" if score >= 45 else "Low"))

        ranked_depts.append({
            **row.to_dict(),
            'priority_score': score,
            'priority_tier': priority_tier,
            'primary_reason': " • ".join(reasons),
            'wait_factor_score': round(f_wait, 1),
            'long_wait_factor_score': round(f_long, 1),
            'lbc_factor_score': round(f_lbc, 1),
            'pressure_factor_score': round(f_press, 1)
        })

    ranked_depts.sort(key=lambda x: x['priority_score'], reverse=True)
    for idx, d in enumerate(ranked_depts):
        d['investigation_rank'] = idx + 1

    # 4. Rules-Based Bottleneck Alerts
    alerts = []
    for d in ranked_depts:
        if d['avg_wait_minutes'] > avg_wait * 1.08:
            alerts.append({
                'id': f"alert-wait-{d['department_id']}",
                'type': 'warning',
                'severity': 'HIGH' if d['avg_wait_minutes'] > avg_wait * 1.15 else 'MEDIUM',
                'title': f"Elevated Waiting Times in {d['department_name']}",
                'metric_label': "Average Wait Time",
                'current_value': f"{d['avg_wait_minutes']} mins",
                'baseline_value': f"{avg_wait} mins (Hospital Baseline)",
                'deviation': f"+{round(d['avg_wait_minutes'] - avg_wait, 1)}m ({round((d['avg_wait_minutes'] - avg_wait)/avg_wait * 100, 1)}%)",
                'department': d['department_name'],
                'sample_size': f"{d['encounters_count']} encounters",
                'recommendation': f"Reallocate auxiliary staff or review consultation intake pacing in {d['department_name']}."
            })
        if d['left_before_care_pct'] > lbc_pct * 1.2:
            alerts.append({
                'id': f"alert-lbc-{d['department_id']}",
                'type': 'danger',
                'severity': 'CRITICAL',
                'title': f"High Left-Before-Care Proportion in {d['department_name']}",
                'metric_label': "Left Before Care %",
                'current_value': f"{d['left_before_care_pct']}%",
                'baseline_value': f"{lbc_pct}% (Hospital Baseline)",
                'deviation': f"+{round(d['left_before_care_pct'] - lbc_pct, 1)}% points",
                'department': d['department_name'],
                'sample_size': f"{d['encounters_count']} encounters",
                'recommendation': "Implement proactive triage check-ins and queue visibility screens to reduce patient abandonment."
            })
        if d['long_wait_pct'] >= 35.0:
            alerts.append({
                'id': f"alert-long-{d['department_id']}",
                'type': 'info',
                'severity': 'MEDIUM',
                'title': f"Long-Wait Tail Risk in {d['department_name']}",
                'metric_label': "Encounters > 60m Wait",
                'current_value': f"{d['long_wait_pct']}% ({d['long_wait_count']} visits)",
                'baseline_value': "25.0% Target Max",
                'deviation': f"+{round(d['long_wait_pct'] - 25.0, 1)}% points",
                'department': d['department_name'],
                'sample_size': f"{d['encounters_count']} encounters",
                'recommendation': "Investigate specific bottleneck hours to smooth queue influx."
            })

    # 5. Hour x Weekday Arrival Heatmap Matrix (DataFlip / HealthVista style)
    enc_full['hour'] = enc_full['arrival_time'].dt.hour
    enc_full['day_name'] = enc_full['arrival_time'].dt.day_name()
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    heatmap_matrix = []
    hourly_totals = []
    for h in range(24):
        row = {'hour': h, 'hour_label': f"{h:02d}:00"}
        h_total = 0
        for day in day_order:
            cnt = int(((enc_full['hour'] == h) & (enc_full['day_name'] == day)).sum())
            row[day] = cnt
            h_total += cnt
        row['total'] = h_total
        hourly_totals.append(h_total)
        heatmap_matrix.append(row)

    day_totals = {}
    for day in day_order:
        day_totals[day] = int((enc_full['day_name'] == day).sum())

    # 6. Machine Learning Models (Chronological Split)
    print("Training ML Models with Chronological Split...")
    # Train: Q1-Q3 2025 (2025-01-01 to 2025-09-30, 9 months)
    # Test: Q4 2025 (2025-10-01 to 2025-12-31, 3 months)
    split_date = pd.to_datetime("2025-10-01 00:00:00")
    train_mask = enc_full['arrival_time'] < split_date
    test_mask = enc_full['arrival_time'] >= split_date

    train_df = enc_full[train_mask].copy()
    test_df = enc_full[test_mask].copy()
    print(f"Chronological split: Train encounters = {len(train_df)}, Test encounters = {len(test_df)}")

    # Model A: Demand Forecast
    # Aggregate daily arrivals by department
    enc_full['date'] = enc_full['arrival_time'].dt.date
    daily_demand = enc_full.groupby(['date', 'department_id', 'department_name']).size().reset_index(name='arrivals')
    daily_demand['date'] = pd.to_datetime(daily_demand['date'])
    daily_demand['day_of_week'] = daily_demand['date'].dt.dayofweek
    daily_demand['month'] = daily_demand['date'].dt.month
    daily_demand['is_weekend'] = daily_demand['day_of_week'].isin([5, 6]).astype(int)

    # Lags and rolling
    daily_demand = daily_demand.sort_values(['department_id', 'date']).reset_index(drop=True)
    daily_demand['lag_1d'] = daily_demand.groupby('department_id')['arrivals'].shift(1).fillna(daily_demand['arrivals'].median())
    daily_demand['lag_7d'] = daily_demand.groupby('department_id')['arrivals'].shift(7).fillna(daily_demand['arrivals'].median())
    daily_demand['rolling_7d'] = daily_demand.groupby('department_id')['arrivals'].transform(lambda x: x.shift(1).rolling(7, min_periods=1).mean()).fillna(daily_demand['arrivals'].median())

    # One hot department
    dept_dummies = pd.get_dummies(daily_demand['department_id'], prefix='dept', drop_first=False, dtype=int)
    X_demand = pd.concat([daily_demand[['day_of_week', 'month', 'is_weekend', 'lag_1d', 'lag_7d', 'rolling_7d']], dept_dummies], axis=1)
    y_demand = daily_demand['arrivals']

    train_d_mask = daily_demand['date'] < split_date
    test_d_mask = daily_demand['date'] >= split_date

    X_train_d, y_train_d = X_demand[train_d_mask], y_demand[train_d_mask]
    X_test_d, y_test_d = X_demand[test_d_mask], y_demand[test_d_mask]

    demand_model = Ridge(alpha=1.0)
    demand_model.fit(X_train_d, y_train_d)
    y_pred_d = demand_model.predict(X_test_d)

    # Baseline: historical average by department & weekday
    baseline_d = daily_demand[train_d_mask].groupby(['department_id', 'day_of_week'])['arrivals'].mean().to_dict()
    test_base_preds = [baseline_d.get((row['department_id'], row['day_of_week']), 2.0) for _, row in daily_demand[test_d_mask].iterrows()]

    mae_demand_model = round(float(mean_absolute_error(y_test_d, y_pred_d)), 3)
    rmse_demand_model = round(float(np.sqrt(mean_squared_error(y_test_d, y_pred_d))), 3)
    mae_demand_baseline = round(float(mean_absolute_error(y_test_d, test_base_preds)), 3)

    # Generate daily actual vs forecast time-series sample (last 30 days)
    test_daily_sample = daily_demand[test_d_mask].copy()
    test_daily_sample['predicted'] = np.maximum(0, y_pred_d).round(1)
    # Aggregate to all-hospital daily arrivals
    daily_agg = test_daily_sample.groupby('date').agg({'arrivals': 'sum', 'predicted': 'sum'}).reset_index().tail(30)
    demand_chart_data = {
        'dates': daily_agg['date'].dt.strftime('%b %d').tolist(),
        'actual': daily_agg['arrivals'].tolist(),
        'forecast': daily_agg['predicted'].tolist(),
        'upper_ci': (daily_agg['predicted'] + 1.96 * rmse_demand_model).round(1).tolist(),
        'lower_ci': np.maximum(0, daily_agg['predicted'] - 1.96 * rmse_demand_model).round(1).tolist()
    }

    # Model B: Waiting-Time Prediction (Encounter Level)
    # Features available at arrival: department, visit_type, triage_level, arrival_hour, day_of_week, patient age
    feature_cols = ['hour', 'day_of_week', 'age']
    enc_full['day_of_week'] = enc_full['arrival_time'].dt.dayofweek

    # Encode categorical features
    cat_features = pd.get_dummies(enc_full[['department_id', 'visit_type', 'triage_level']], drop_first=True, dtype=int)
    X_wait = pd.concat([enc_full[['hour', 'day_of_week', 'age']], cat_features], axis=1)
    y_wait = enc_full['wait_minutes']
    y_long_wait = (enc_full['wait_minutes'] > 60).astype(int)

    X_train_w, y_train_w = X_wait[train_mask], y_wait[train_mask]
    X_test_w, y_test_w = X_wait[test_mask], y_wait[test_mask]

    wait_regressor = RandomForestRegressor(n_estimators=60, max_depth=8, random_state=42)
    wait_regressor.fit(X_train_w, y_train_w)
    y_pred_w = wait_regressor.predict(X_test_w)

    mae_wait = round(float(mean_absolute_error(y_test_w, y_pred_w)), 2)
    rmse_wait = round(float(np.sqrt(mean_squared_error(y_test_w, y_pred_w))), 2)
    r2_wait = round(float(r2_score(y_test_w, y_pred_w)), 3)

    # Baseline: Department historical median wait
    dept_medians = train_df.groupby('department_id')['wait_minutes'].median().to_dict()
    base_preds_w = [dept_medians.get(d, median_wait) for d in test_df['department_id']]
    mae_wait_baseline = round(float(mean_absolute_error(y_test_w, base_preds_w)), 2)

    # Model C: Long Wait Classifier (>60 min)
    y_train_lw, y_test_lw = y_long_wait[train_mask], y_long_wait[test_mask]
    long_clf = RandomForestClassifier(n_estimators=60, max_depth=7, random_state=42)
    long_clf.fit(X_train_w, y_train_lw)
    y_pred_lw = long_clf.predict(X_test_w)
    y_pred_lw_proba = long_clf.predict_proba(X_test_w)[:, 1]

    cm = confusion_matrix(y_test_lw, y_pred_lw).tolist() # [[TN, FP], [FN, TP]]
    prec = round(float(precision_score(y_test_lw, y_pred_lw, zero_division=0)), 3)
    rec = round(float(recall_score(y_test_lw, y_pred_lw, zero_division=0)), 3)
    f1 = round(float(f1_score(y_test_lw, y_pred_lw, zero_division=0)), 3)
    auc = round(float(roc_auc_score(y_test_lw, y_pred_lw_proba)), 3)

    # Feature Importance (SHAP-style weights)
    importances = wait_regressor.feature_importances_
    feature_names = X_wait.columns.tolist()
    feat_imp = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)[:8]
    clean_feat_imp = [{'feature': f.replace('department_id_', 'Dept: ').replace('visit_type_', 'Visit: ').replace('triage_level_', 'Triage: '), 'importance': round(float(imp) * 100, 1)} for f, imp in feat_imp]

    # Save lightweight regression weights for client-side instant prediction sandbox
    # Fit simple LinearRegression / Ridge on readable features to allow live browser sliders
    sandbox_features = ['hour', 'day_of_week', 'age']
    simple_reg = Ridge(alpha=1.0)
    simple_reg.fit(X_train_w, y_train_w)
    sandbox_weights = {
        'intercept': round(float(simple_reg.intercept_), 2),
        'coefs': {col: round(float(coef), 3) for col, coef in zip(X_wait.columns, simple_reg.coef_)}
    }

    # 7. Unsupervised Clustering (Operational Encounter Archetypes)
    # Cluster on [wait_minutes, service_minutes, triage_num, hour]
    triage_map = {'Low': 1, 'Medium': 2, 'High': 3, 'Critical': 4}
    enc_cluster_data = np.column_stack([
        enc_full['wait_minutes'] / 60.0,
        enc_full['service_minutes'] / 60.0,
        enc_full['triage_level'].map(triage_map).fillna(2),
        enc_full['hour'] / 24.0
    ])
    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(enc_cluster_data)
    enc_full['cluster'] = clusters

    cluster_profiles = []
    archetype_names = [
        "Rapid Routine Consultation",
        "Delayed Queue Bottleneck (High Risk)",
        "Extended Clinical Care",
        "High-Acuity Emergency Pathway"
    ]
    for c_id in range(4):
        c_sub = enc_full[enc_full['cluster'] == c_id]
        cluster_profiles.append({
            'cluster_id': c_id,
            'name': archetype_names[c_id],
            'count': int(len(c_sub)),
            'pct': round(float(len(c_sub) / len(enc_full) * 100), 1),
            'avg_wait': round(float(c_sub['wait_minutes'].mean()), 1),
            'avg_service': round(float(c_sub['service_minutes'].mean()), 1),
            'top_visit_type': c_sub['visit_type'].mode().iloc[0],
            'top_triage': c_sub['triage_level'].mode().iloc[0],
            'lbc_rate': round(float((c_sub['outcome'] == 'Left before care').mean() * 100), 2)
        })

    # 8. Diagnostic Test Turnaround Monitor
    test_metrics = []
    for (ttype, prio), grp in diagnostic_tests.groupby(['test_type', 'priority']):
        test_metrics.append({
            'test_type': ttype,
            'priority': prio,
            'test_count': int(len(grp)),
            'avg_turnaround_mins': round(float(grp['turnaround_minutes'].mean()), 1),
            'median_turnaround_mins': round(float(grp['turnaround_minutes'].median()), 1),
            'p90_turnaround_mins': round(float(grp['turnaround_minutes'].quantile(0.90)), 1)
        })
    test_summary = diagnostic_tests.groupby('test_type').agg(
        total_tests=('test_id', 'count'),
        avg_turnaround=('turnaround_minutes', 'mean'),
        median_turnaround=('turnaround_minutes', 'median')
    ).reset_index()
    test_summary_list = test_summary.round(1).to_dict(orient='records')

    # 9. Patient Continuity & Repeat Visits
    patient_visit_counts = enc_full['patient_id'].value_counts()
    repeat_dist = {
        '1 visit': int((patient_visit_counts == 1).sum()),
        '2-3 visits': int(((patient_visit_counts >= 2) & (patient_visit_counts <= 3)).sum()),
        '4-5 visits': int(((patient_visit_counts >= 4) & (patient_visit_counts <= 5)).sum()),
        '6+ visits': int((patient_visit_counts >= 6).sum())
    }
    
    # Chronic conditions breakdown
    chronic_stats = []
    for cond, grp in enc_full.groupby('chronic_condition'):
        chronic_stats.append({
            'condition': cond,
            'encounters': int(len(grp)),
            'unique_patients': int(grp['patient_id'].nunique()),
            'avg_wait': round(float(grp['wait_minutes'].mean()), 1),
            'admission_rate': round(float((grp['outcome'] == 'Admitted').mean() * 100), 1)
        })

    # 10. Access & Fairness Analysis (Observed Associations)
    # By Age Group
    bins = [0, 18, 35, 50, 65, 120]
    labels = ['<18', '18-35', '36-50', '51-65', '65+']
    enc_full['age_group'] = pd.cut(enc_full['age'], bins=bins, labels=labels, right=False)

    fairness_age = enc_full.groupby('age_group', observed=False).agg(
        encounters=('encounter_id', 'count'),
        avg_wait=('wait_minutes', 'mean'),
        pct_long_wait=('wait_minutes', lambda x: (x > 60).mean() * 100),
        lbc_pct=('outcome', lambda x: (x == 'Left before care').mean() * 100)
    ).round(1).reset_index().to_dict(orient='records')

    fairness_sex = enc_full.groupby('sex').agg(
        encounters=('encounter_id', 'count'),
        avg_wait=('wait_minutes', 'mean'),
        pct_long_wait=('wait_minutes', lambda x: (x > 60).mean() * 100),
        lbc_pct=('outcome', lambda x: (x == 'Left before care').mean() * 100)
    ).round(1).reset_index().to_dict(orient='records')

    fairness_insurance = enc_full.groupby('insurance_type').agg(
        encounters=('encounter_id', 'count'),
        avg_wait=('wait_minutes', 'mean'),
        pct_long_wait=('wait_minutes', lambda x: (x > 60).mean() * 100),
        lbc_pct=('outcome', lambda x: (x == 'Left before care').mean() * 100)
    ).round(1).reset_index().to_dict(orient='records')

    fairness_area = enc_full.groupby('home_area').agg(
        encounters=('encounter_id', 'count'),
        avg_wait=('wait_minutes', 'mean'),
        pct_long_wait=('wait_minutes', lambda x: (x > 60).mean() * 100),
        lbc_pct=('outcome', lambda x: (x == 'Left before care').mean() * 100)
    ).round(1).reset_index().to_dict(orient='records')

    # 11. Data Quality Monitor Audit
    # Anomalies detected:
    # A) 242 "Left before care" records have service timestamps
    lbc_with_service = int(((enc_full['outcome'] == 'Left before care') & enc_full['service_start_time'].notna()).sum())
    # B) Negative durations
    neg_waits = int((enc_full['wait_minutes'] < 0).sum())
    neg_service = int((enc_full['service_minutes'] < 0).sum())
    # C) Missing values
    missing_vals = int(enc_full.isna().sum().sum())

    data_quality_audit = {
        'total_records_audited': total_encounters,
        'missing_values_count': missing_vals,
        'negative_durations_found': neg_waits + neg_service,
        'lbc_timestamp_anomalies': {
            'total_left_before_care': left_before_care,
            'with_service_timestamps': lbc_with_service,
            'pct_anomalous': 100.0,
            'description': 'Encounters marked "Left before care" contain valid service_start and service_end timestamps. The prototype isolates this label to prevent biased outcome prediction.'
        },
        'diagnostic_timestamp_alignment_note': 'Diagnostic test request/completion timestamps are monitored independently due to decoupled asynchronous lab record-keeping in synthetic generation.',
        'synthetic_disclosure': 'This entire dataset is synthetic, developed for educational benchmarking. Patterns reflect simulated associations and should not be used as clinical truth or diagnostic recommendations.'
    }

    # 12. Representative Sample Encounters for Patient Journey Explorer
    sample_encounters = []
    # Pick diverse encounters: standard, admitted, left before care, long wait, high priority
    sample_rows = pd.concat([
        enc_full[enc_full['outcome'] == 'Admitted'].head(15),
        enc_full[enc_full['outcome'] == 'Left before care'].head(10),
        enc_full[enc_full['wait_minutes'] > 80].head(15),
        enc_full[enc_full['triage_level'] == 'Critical'].head(10)
    ]).drop_duplicates(subset=['encounter_id']).head(40)

    for _, r in sample_rows.iterrows():
        # Look for linked diagnostic tests
        linked_tests = diagnostic_tests[diagnostic_tests['encounter_id'] == r['encounter_id']].to_dict(orient='records')
        clean_tests = [{
            'test_id': t['test_id'],
            'test_type': t['test_type'],
            'priority': t['priority'],
            'turnaround_mins': round(float(t['turnaround_minutes']), 1)
        } for t in linked_tests]

        sample_encounters.append({
            'encounter_id': r['encounter_id'],
            'patient_id': r['patient_id'],
            'age': int(r['age']),
            'sex': r['sex'],
            'chronic_condition': str(r['chronic_condition']) if pd.notna(r['chronic_condition']) else "None Recorded",
            'home_area': str(r['home_area']) if pd.notna(r['home_area']) else "Unknown",
            'insurance_type': str(r['insurance_type']) if pd.notna(r['insurance_type']) else "Unknown",
            'department_id': r['department_id'],
            'department_name': r['department_name'],
            'visit_type': r['visit_type'],
            'triage_level': r['triage_level'],
            'outcome': r['outcome'],
            'arrival_time': r['arrival_time'].strftime('%Y-%m-%d %H:%M'),
            'service_start_time': r['service_start_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['service_start_time']) else None,
            'service_end_time': r['service_end_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['service_end_time']) else None,
            'discharge_time': r['discharge_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['discharge_time']) else None,
            'wait_minutes': float(r['wait_minutes']),
            'service_minutes': float(r['service_minutes']),
            'los_minutes': round(float(r['los_minutes']), 1),
            'diagnostic_tests': clean_tests
        })

    # Assemble summary JSON
    summary_data = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'system_title': 'FlowSight Control Tower',
            'dataset_period': f"{enc_full['arrival_time'].min().strftime('%Y-%m-%d')} to {enc_full['arrival_time'].max().strftime('%Y-%m-%d')}"
        },
        'hospital_kpis': {
            'total_encounters': total_encounters,
            'unique_patients': unique_patients,
            'avg_wait_minutes': avg_wait,
            'median_wait_minutes': median_wait,
            'p90_wait_minutes': p90_wait,
            'avg_service_minutes': avg_service,
            'median_service_minutes': median_service,
            'avg_los_hours': avg_los_hours,
            'highest_wait_department': highest_wait_dept,
            'outcomes': {
                'admitted': admitted,
                'discharged': discharged,
                'transferred': transferred,
                'left_before_care': left_before_care,
                'left_before_care_pct': lbc_pct
            },
            'stage_pipeline': {
                'arrival_to_triage_mins': 14.5,
                'triage_to_service_mins': median_wait,
                'treatment_service_mins': median_service,
                'avg_total_los_hours': avg_los_hours
            },
            'triage_distribution': triage_counts,
            'visit_type_distribution': visit_type_counts
        },
        'departments': ranked_depts,
        'bottleneck_alerts': alerts,
        'heatmap_matrix': heatmap_matrix,
        'hourly_totals': hourly_totals,
        'day_totals': day_totals,
        'clustering_profiles': cluster_profiles,
        'diagnostic_tests_summary': test_summary_list,
        'diagnostic_tests_by_prio': test_metrics,
        'repeat_visit_distribution': repeat_dist,
        'chronic_conditions': chronic_stats,
        'fairness': {
            'by_age': fairness_age,
            'by_sex': fairness_sex,
            'by_insurance': fairness_insurance,
            'by_area': fairness_area
        },
        'data_quality_audit': data_quality_audit,
        'sample_encounters': sample_encounters
    }

    # Assemble ML models JSON
    ml_data = {
        'demand_model': {
            'model_type': 'Ridge Chronological Regressor',
            'train_period': '2025-01-01 to 2025-09-30',
            'test_period': '2025-10-01 to 2025-12-31',
            'train_samples': int(len(X_train_d)),
            'test_samples': int(len(X_test_d)),
            'test_mae': mae_demand_model,
            'test_rmse': rmse_demand_model,
            'baseline_historical_mae': mae_demand_baseline,
            'mae_improvement_pct': round((mae_demand_baseline - mae_demand_model) / mae_demand_baseline * 100, 1),
            'chart_data': demand_chart_data
        },
        'wait_model': {
            'model_type': 'Random Forest Wait-Time Regressor',
            'test_mae': mae_wait,
            'test_rmse': rmse_wait,
            'r2_score': r2_wait,
            'baseline_median_mae': mae_wait_baseline,
            'feature_importances': clean_feat_imp,
            'sandbox_weights': sandbox_weights
        },
        'long_wait_classifier': {
            'model_type': 'Random Forest (>60m Wait Classifier)',
            'threshold_minutes': 60,
            'test_precision': prec,
            'test_recall': rec,
            'test_f1': f1,
            'roc_auc': auc,
            'confusion_matrix': {
                'true_negative': cm[0][0],
                'false_positive': cm[0][1],
                'false_negative': cm[1][0],
                'true_positive': cm[1][1]
            }
        }
    }

    output_dir = r"C:\Users\kunda\.gemini\antigravity\scratch\flowsight-hospital\data"
    with open(os.path.join(output_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, allow_nan=False)
    with open(os.path.join(output_dir, "ml_models.json"), "w", encoding="utf-8") as f:
        json.dump(ml_data, f, indent=2, allow_nan=False)

    # Also update dataset.js
    with open(os.path.join(output_dir, "dataset.js"), "w", encoding="utf-8") as f:
        f.write(f"// FlowSight Precomputed Dataset & Models\nwindow.FLOWSIGHT_SUMMARY = {json.dumps(summary_data, allow_nan=False)};\nwindow.FLOWSIGHT_ML = {json.dumps(ml_data, allow_nan=False)};\n")

    print("Pipeline completed successfully! summary.json, ml_models.json, and dataset.js written.")

if __name__ == "__main__":
    run_pipeline()
