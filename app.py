"""Streamlit entry point for the NHAA survivor-support triage prototype."""

import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Must be the first Streamlit command
st.set_page_config(
    page_title="NHAA Support System",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Database initialization & seeding (runs once)
# ---------------------------------------------------------------------------
from src.database import init_db
from src.seed_data import seed_mock_data

init_db()
seed_mock_data()

# ---------------------------------------------------------------------------
# Custom CSS for premium look
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global font */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Main header styling */
    .main-header {
        background: linear-gradient(135deg, #6C63FF 0%, #3F3D56 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 20px rgba(108, 99, 255, 0.3);
    }
    .main-header h1 {
        color: white;
        font-size: 1.8rem;
        margin: 0;
        font-weight: 700;
    }
    .main-header p {
        color: rgba(255,255,255,0.8);
        font-size: 0.95rem;
        margin: 0.3rem 0 0 0;
    }
    
    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #1A1D23 0%, #2D2D3F 100%);
        border: 1px solid rgba(108, 99, 255, 0.2);
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(108, 99, 255, 0.2);
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0.5rem 0;
    }
    .metric-label {
        font-size: 0.85rem;
        color: rgba(255,255,255,0.6);
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Score display */
    .score-display {
        text-align: center;
        padding: 2rem;
        border-radius: 16px;
        margin: 1rem 0;
    }
    .score-number {
        font-size: 4rem;
        font-weight: 700;
        line-height: 1;
    }
    .score-band {
        font-size: 1.3rem;
        font-weight: 600;
        margin-top: 0.5rem;
    }
    .score-scale {
        font-size: 0.85rem;
        color: rgba(255,255,255,0.5);
        margin-top: 0.3rem;
    }
    
    /* Explanation cards */
    .explanation-card {
        background: rgba(108, 99, 255, 0.08);
        border-left: 3px solid #6C63FF;
        border-radius: 0 8px 8px 0;
        padding: 0.8rem 1.2rem;
        margin: 0.5rem 0;
    }
    .explanation-feature {
        font-weight: 600;
        font-size: 0.95rem;
    }
    .explanation-detail {
        font-size: 0.82rem;
        color: rgba(255,255,255,0.6);
        margin-top: 0.2rem;
    }
    
    /* Alert cards */
    .alert-critical {
        background: rgba(183, 28, 28, 0.15);
        border-left: 4px solid #B71C1C;
        border-radius: 0 8px 8px 0;
        padding: 1rem 1.2rem;
        margin: 0.5rem 0;
    }
    .alert-warning {
        background: rgba(255, 152, 0, 0.12);
        border-left: 4px solid #FF9800;
        border-radius: 0 8px 8px 0;
        padding: 1rem 1.2rem;
        margin: 0.5rem 0;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0E1117 0%, #151922 100%);
    }
    
    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 16px;
    }
    
    /* Severity band colors for inline use */
    .severity-minimal { color: #4CAF50; }
    .severity-mild { color: #FFC107; }
    .severity-moderate { color: #FF9800; }
    .severity-mod-severe { color: #FF5722; }
    .severity-severe { color: #B71C1C; }
    
    /* Prototype privacy and safety note */
    .safety-note {
        background: rgba(76, 175, 80, 0.08);
        border: 1px solid rgba(76, 175, 80, 0.3);
        border-radius: 8px;
        padding: 0.8rem;
        font-size: 0.75rem;
        line-height: 1.4;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0;">
        <div style="font-size: 2.5rem;">🧭</div>
        <div style="font-size: 1.1rem; font-weight: 700; color: #6C63FF; margin-top: 0.3rem;">
            NHAA Support System
        </div>
        <div style="font-size: 0.75rem; color: rgba(255,255,255,0.5); margin-top: 0.2rem;">
            Help and support for people we serve
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()

    from src.ui_access import configure_local_development_actor
    try:
        active_actor = configure_local_development_actor()
        st.caption(f"Logged in as: {active_actor.role.replace('_', ' ')} • {active_actor.user_id}")
    except Exception as error:
        st.error(f"Could not verify your login: {error}")
        st.stop()

    st.divider()
    
    # Language selector (Phase 6)
    from config import LANGUAGES
    selected_language = st.selectbox(
        "🌐 Language",
        options=list(LANGUAGES.keys()),
        index=0,
        help="Choose the language being spoken or written"
    )
    st.session_state["selected_language"] = selected_language
    st.session_state["language_code"] = LANGUAGES[selected_language]
    
    st.divider()
    
    # This avoids claiming legal compliance from a prototype privacy notice.
    from config import PRIVACY_AND_SAFETY_NOTE
    with st.expander("🔒 Privacy and safety information", expanded=False):
        st.markdown(PRIVACY_AND_SAFETY_NOTE)
    
    st.divider()
    
    st.markdown("""
    <div style="text-align: center; font-size: 0.7rem; color: rgba(255,255,255,0.3); padding: 1rem 0;">
        SIH26094 • Privacy-aware prototype<br/>
        Helps staff make decisions — does not decide for them • Uses sample data
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Page Navigation
# ---------------------------------------------------------------------------
pg = st.navigation([
    st.Page("pages/1_submit_interaction.py", title="Record a conversation", icon="📝"),
    st.Page("pages/7_validated_screening.py", title="Wellbeing check-in (PHQ-9 / GAD-7)", icon="📋"),
    st.Page("pages/8_privacy_governance.py", title="Privacy & data rules", icon="🔐"),
    st.Page("pages/2_case_timeline.py", title="Case history", icon="📈"),
    st.Page("pages/3_counsellor_alerts.py", title="Cases waiting for review", icon="👥"),
    st.Page("pages/4_state_dashboard.py", title="Overview", icon="🗺️"),
    st.Page("pages/5_crisis_workflow.py", title="Urgent help process", icon="🚨"),
    st.Page("pages/6_crisis_configuration.py", title="Urgent help settings", icon="⚙️"),
    st.Page("pages/9_checkin_journeys.py", title="Follow-up schedule", icon="💬"),
    st.Page("pages/10_pre_deployment_evaluation.py", title="AI oversight (admin)", icon="🛡️"),
])

pg.run()
