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
