"""District-level aggregate coordination dashboard.

Scoped exclusively to the authenticated district officer's own district.
Aggregate counts pass through the same small-cell suppression as the state
and national dashboards — no individual case details are exposed.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import SUPPORT_PRIORITY_BANDS
from src.database import export_deidentified_dashboard, get_deidentified_dashboard
from src.privacy_architecture import AccessDenied
from src.translations import t
from src.ui_access import get_active_actor


st.markdown(
    """
    <div class="main-header">
        <h1>🏘️ District Overview</h1>
        <p>Summary of case volumes and urgency within your district.
           Counts are grouped for privacy; no individual details are shown.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(
    "Available to district officers only. Numbers below the minimum group size "
    "are suppressed to protect privacy."
)

try:
    actor = get_active_actor()
    dashboard = get_deidentified_dashboard(actor, purpose="service_coordination", scope="district")
except AccessDenied as error:
    st.error(
        f"Access denied: {error}  \n\n"
        "This dashboard is only available to district officers viewing their own district."
    )
    st.stop()
except Exception as error:
    st.error(f"{t('p4_load_error')}: {error}")
    st.stop()

district_label = dashboard.get("district") or actor.district or "your district"
state_label = dashboard.get("state") or actor.state or ""

kpi_data = [
    ("Cases being followed", dashboard["total_cases"], "#6C63FF"),
    ("District", f"{district_label}, {state_label}".strip(", "), "#3F8EFC"),
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
    st.markdown("#### Cases in this district")
    location_rows = dashboard.get("location_counts", [])
    if location_rows:
        loc_df = pd.DataFrame(location_rows)
        chart = go.Figure(
            go.Bar(
                x=loc_df["count"],
                y=loc_df["location"],
                orientation="h",
                marker_color="#6C63FF",
                text=loc_df["count"],
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
        st.info(
            "No aggregate data is available for this district yet, "
            "or all counts are below the minimum group size for privacy."
        )

with right:
    st.markdown(f"#### {t('p4_urgency')}")
    priority_rows = dashboard.get("priority_distribution", [])
    counts = {row["priority_band"]: row["count"] for row in priority_rows}
    labels = [band["label"] for band in SUPPORT_PRIORITY_BANDS if counts.get(band["label"], 0)]
    values = [counts[label] for label in labels]
    if labels:
        chart = go.Figure(
            go.Pie(
                labels=labels,
                values=values,
                marker=dict(colors=[band["color"] for band in SUPPORT_PRIORITY_BANDS if band["label"] in labels]),
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
    else:
        st.info("No priority data available yet.")

st.divider()
st.markdown("#### Priority breakdown")
if priority_rows:
    dist_df = pd.DataFrame(priority_rows)
    figure = go.Figure()
    for band in SUPPORT_PRIORITY_BANDS:
        band_rows = dist_df[dist_df["priority_band"] == band["label"]]
        if not band_rows.empty:
            figure.add_trace(
                go.Bar(
                    name=band["label"],
                    x=band_rows["location"],
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
    st.info("No priority distribution available yet.")

st.divider()
if st.button(t("p4_download_button")):
    try:
        exported = export_deidentified_dashboard(
            actor, purpose="authorised_reporting", scope="district"
        )
        st.download_button(
            t("p4_download_json_button"),
            data=pd.Series(exported).to_json(),
            file_name=f"nhaa-district-{district_label}-aggregate.json",
            mime="application/json",
        )
        st.success(t("p4_download_success"))
    except Exception as error:
        st.error(str(error))
