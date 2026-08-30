"""Aggregate support-coordination dashboard for authorised users."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import SUPPORT_PRIORITY_BANDS
from src.database import export_deidentified_dashboard, get_deidentified_dashboard
from src.translations import t
from src.ui_access import get_active_actor


st.markdown(
    f"""
    <div class="main-header">
        <h1>{t("p4_heading")}</h1>
        <p>{t("p4_subheading")}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(t("p4_caption"))

try:
    actor = get_active_actor()
    dashboard = get_deidentified_dashboard(actor, purpose="service_coordination")
except Exception as error:
    st.error(f"{t('p4_load_error')}: {error}")
    st.stop()

state_rows = dashboard["state_counts"]
priority_rows = dashboard["priority_distribution"]
kpi_data = [
    (t("p4_cases_followed"), dashboard["total_cases"], "#6C63FF"),
    (t("p4_scope"), dashboard["scope"].title(), "#3F8EFC"),
    (t("p4_privacy_threshold"), dashboard["small_cell_threshold"], "#FF5722"),
]
for col, (label, value, color) in zip(st.columns(3), kpi_data):
    with col:
        st.markdown(
            f"""<div class="metric-card"><div class="metric-label">{label}</div>
            <div class="metric-value" style="color:{color};">{value}</div></div>""",
            unsafe_allow_html=True,
        )

st.divider()
left, right = st.columns(2)
with left:
    st.markdown(f"#### {t('p4_by_state')}")
    if state_rows:
        state_df = pd.DataFrame(state_rows)
        chart = go.Figure(
            go.Bar(
                x=state_df["count"],
                y=state_df["state"],
                orientation="h",
                marker_color="#6C63FF",
                text=state_df["count"],
                textposition="auto",
                hovertemplate="<b>%{y}</b><br>Cases being followed: %{x}<extra></extra>",
            )
        )
        chart.update_layout(
            height=320, margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(chart, use_container_width=True)
    else:
        st.info("No aggregate data available.")

with right:
    st.markdown(f"#### {t('p4_urgency')}")
    counts = {row["priority_band"]: row["count"] for row in priority_rows}
    labels = [band["label"] for band in SUPPORT_PRIORITY_BANDS if counts.get(band["label"], 0)]
    values = [counts[label] for label in labels]
    chart = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            marker=dict(colors=[band["color"] for band in SUPPORT_PRIORITY_BANDS]),
            hole=0.5,
            textinfo="label+value",
            hovertemplate="<b>%{label}</b><br>Latest records: %{value}<extra></extra>",
        )
    )
    chart.update_layout(
        height=320, margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    st.plotly_chart(chart, use_container_width=True)

st.divider()
st.markdown(f"#### {t('p4_urgency_by_state')}")
distribution = priority_rows
if distribution:
    distribution_df = pd.DataFrame(distribution)
    figure = go.Figure()
    for band in SUPPORT_PRIORITY_BANDS:
        band_rows = distribution_df[distribution_df["priority_band"] == band["label"]]
        if not band_rows.empty:
            figure.add_trace(
                go.Bar(
                    name=band["label"],
                    x=band_rows["state"],
                    y=band_rows["count"],
                    marker_color=band["color"],
                    hovertemplate=f"<b>{band['label']}</b><br>%{{x}}: %{{y}} records<extra></extra>",
                )
            )
    figure.update_layout(
        barmode="stack", height=360, margin=dict(l=10, r=10, t=30, b=70),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(title="Latest records"), xaxis=dict(tickangle=-35),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(figure, use_container_width=True)
else:
    st.info("No priority distribution is available yet.")

st.divider()
st.markdown("#### Case category breakdown")
case_type_rows = dashboard.get("case_type_distribution", [])
ct_p_rows = dashboard.get("case_type_priority_distribution", [])

if case_type_rows:
    ct_df = pd.DataFrame(case_type_rows)
    ct_labels = {
        "rape_or_gang_rape": "Rape or gang rape",
        "murder_grievous_hurt_or_arson": "Murder, grievous hurt, or arson",
        "witness_intimidation_or_threats": "Witness intimidation or threats",
        "caste_based_violence_family": "Caste based violence/family",
        "compensation_rehabilitation_beneficiary": "Compensation/rehabilitation beneficiary",
        "other": "Other"
    }
    ct_df["case_type_label"] = ct_df["case_type"].map(lambda x: ct_labels.get(x, x.replace("_", " ").title()))
    
    urgent_counts = {}
    if ct_p_rows:
        ct_p_df = pd.DataFrame(ct_p_rows)
        urgent_df = ct_p_df[ct_p_df["priority_band"] == "Urgent human review"]
        urgent_counts = dict(zip(urgent_df["case_type"], urgent_df["count"]))
    
    ct_df["urgent_count"] = ct_df["case_type"].map(lambda x: urgent_counts.get(x, 0))
    ct_df["hover_text"] = ct_df.apply(lambda row: f"Cases: {row['count']}<br>Flagged urgent: {row['urgent_count']}", axis=1)

    chart = go.Figure(
        go.Bar(
            x=ct_df["count"],
            y=ct_df["case_type_label"],
            orientation="h",
            marker_color="#3F8EFC",
            text=ct_df["count"],
            textposition="auto",
            hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>",
            customdata=ct_df["hover_text"]
        )
    )
    chart.update_layout(
        height=320, margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(chart, use_container_width=True)
else:
    st.info("No aggregate case category data is available yet, or counts are below the minimum group size for privacy.")

st.divider()
if st.button(t("p4_download_button")):
    try:
        exported = export_deidentified_dashboard(actor, purpose="authorised_reporting")
        st.download_button(
            t("p4_download_json_button"),
            data=pd.Series(exported).to_json(),
            file_name="nhaa-deidentified-aggregate.json",
            mime="application/json",
        )
        st.success(t("p4_download_success"))
    except Exception as error:
        st.error(str(error))
