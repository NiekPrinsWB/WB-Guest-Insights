"""
Westerbergen Guest Insights - Streamlit Custom CSS & Styling
Based on Westerbergen Brandbook 2025 — Redesign v2
"""
from app.config import COLORS

CUSTOM_CSS = f"""
<style>
    /* ---- Import Google Fonts ---- */
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&display=swap');

    /* ============================================================
       GLOBAL & RESET
    ============================================================ */
    html, body, .stApp {{
        font-family: 'DM Sans', Helvetica, Arial, sans-serif;
    }}

    .stApp {{
        background-color: #F0EBE3;
        background-image:
            radial-gradient(ellipse at 0% 0%, rgba(59,78,55,0.06) 0%, transparent 55%),
            radial-gradient(ellipse at 100% 100%, rgba(167,161,88,0.05) 0%, transparent 50%);
    }}

    /* Main content area */
    .main .block-container {{
        padding-top: 2.5rem;
        padding-bottom: 3rem;
        max-width: 1280px;
    }}

    /* ============================================================
       TYPOGRAPHY
    ============================================================ */
    h1 {{
        font-family: 'Cormorant Garamond', Georgia, serif !important;
        color: {COLORS['diep_bosgroen']} !important;
        font-size: 2.6rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
        line-height: 1.15 !important;
        margin-bottom: 0.15em !important;
    }}

    h2 {{
        font-family: 'Cormorant Garamond', Georgia, serif !important;
        color: {COLORS['diep_bosgroen']} !important;
        font-size: 1.75rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em;
    }}

    h3 {{
        font-family: 'DM Sans', Helvetica, sans-serif !important;
        color: {COLORS['diep_bosgroen']} !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
    }}

    p, span, label, div {{
        font-family: 'DM Sans', Helvetica, Arial, sans-serif !important;
        color: {COLORS['tekst_donker']} !important;
    }}

    .stMarkdown p {{
        font-size: 0.95rem;
        line-height: 1.7;
        color: {COLORS['tekst_donker']} !important;
    }}

    /* ============================================================
       SIDEBAR
    ============================================================ */
    section[data-testid="stSidebar"] {{
        background-color: {COLORS['diep_bosgroen']} !important;
        background-image:
            radial-gradient(ellipse at 50% 0%, rgba(167,161,88,0.12) 0%, transparent 60%),
            linear-gradient(180deg, rgba(0,0,0,0.08) 0%, transparent 30%);
        border-right: none !important;
    }}

    section[data-testid="stSidebar"] > div {{
        padding-top: 1.5rem;
    }}

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{
        color: {COLORS['wit']} !important;
        font-family: 'Cormorant Garamond', Georgia, serif !important;
    }}

    section[data-testid="stSidebar"] h3 {{
        font-family: 'DM Sans', Helvetica, sans-serif !important;
        letter-spacing: 0.12em !important;
        font-size: 0.7rem !important;
        color: rgba(226,214,200,0.6) !important;
        text-transform: uppercase !important;
        padding-top: 1rem;
    }}

    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown {{
        color: rgba(226,214,200,0.9) !important;
        font-size: 0.9rem !important;
    }}

    section[data-testid="stSidebar"] .stMarkdown p {{
        color: rgba(226,214,200,0.9) !important;
    }}

    /* Sidebar radio navigation */
    section[data-testid="stSidebar"] .stRadio > div {{
        gap: 2px;
    }}

    section[data-testid="stSidebar"] .stRadio label {{
        color: rgba(226,214,200,0.85) !important;
        font-size: 0.9rem !important;
        font-weight: 400 !important;
        padding: 7px 12px !important;
        border-radius: 6px !important;
        transition: background 0.15s, color 0.15s;
        letter-spacing: 0 !important;
        text-transform: none !important;
    }}

    section[data-testid="stSidebar"] .stRadio label:hover {{
        background: rgba(255,255,255,0.07) !important;
        color: {COLORS['wit']} !important;
    }}

    section[data-testid="stSidebar"] .stRadio label[data-selected="true"] {{
        background: rgba(167,161,88,0.2) !important;
        color: {COLORS['wit']} !important;
        font-weight: 500 !important;
        border-left: 2px solid {COLORS['zandgroen']};
        padding-left: 10px !important;
    }}

    /* Sidebar select/multiselect labels */
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stMultiSelect label,
    section[data-testid="stSidebar"] .stDateInput label {{
        color: rgba(226,214,200,0.6) !important;
        font-size: 0.72rem !important;
        font-weight: 500 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
    }}

    /* Sidebar divider */
    section[data-testid="stSidebar"] hr {{
        border-color: rgba(255,255,255,0.1) !important;
        margin: 1rem 0 !important;
    }}

    /* ============================================================
       METRIC CARDS
    ============================================================ */
    div[data-testid="stMetric"] {{
        background: #FFFFFF;
        border-radius: 10px;
        padding: 18px 22px 16px;
        box-shadow:
            0 1px 2px rgba(44,62,40,0.05),
            0 4px 16px rgba(44,62,40,0.06);
        border-top: 3px solid {COLORS['diep_bosgroen']};
        position: relative;
        overflow: hidden;
    }}

    div[data-testid="stMetric"]::after {{
        content: '';
        position: absolute;
        bottom: 0; right: 0;
        width: 60px; height: 60px;
        background: radial-gradient(circle at 100% 100%, rgba(167,161,88,0.08), transparent 70%);
        pointer-events: none;
    }}

    div[data-testid="stMetric"] label {{
        font-family: 'DM Sans', Helvetica, sans-serif !important;
        color: {COLORS['tekst_licht']} !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.09em !important;
    }}

    div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
        font-family: 'Cormorant Garamond', Georgia, serif !important;
        color: {COLORS['diep_bosgroen']} !important;
        font-size: 2.4rem !important;
        font-weight: 600 !important;
        line-height: 1.1 !important;
        letter-spacing: -0.02em;
    }}

    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {{
        font-family: 'DM Sans', Helvetica, sans-serif !important;
        font-size: 0.8rem !important;
    }}

    /* ============================================================
       TABS
    ============================================================ */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px;
        background: transparent;
        border-bottom: 2px solid rgba(59,78,55,0.12);
        padding-bottom: 0;
    }}

    .stTabs [data-baseweb="tab"] {{
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 10px 20px !important;
        font-family: 'DM Sans', Helvetica, sans-serif !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        color: {COLORS['tekst_licht']} !important;
        letter-spacing: 0.02em;
        border-bottom: 2px solid transparent !important;
        margin-bottom: -2px;
        transition: color 0.15s;
    }}

    .stTabs [data-baseweb="tab"]:hover {{
        color: {COLORS['diep_bosgroen']} !important;
    }}

    .stTabs [aria-selected="true"] {{
        background: transparent !important;
        color: {COLORS['diep_bosgroen']} !important;
        border-bottom: 2px solid {COLORS['diep_bosgroen']} !important;
        font-weight: 600 !important;
    }}

    /* ============================================================
       BUTTONS
    ============================================================ */
    .stButton > button {{
        background-color: {COLORS['diep_bosgroen']};
        color: {COLORS['wit']};
        border: none;
        border-radius: 6px;
        font-family: 'DM Sans', Helvetica, sans-serif;
        font-weight: 500;
        font-size: 0.875rem;
        letter-spacing: 0.02em;
        padding: 9px 24px;
        transition: background 0.2s, box-shadow 0.2s, transform 0.1s;
        box-shadow: 0 1px 4px rgba(44,62,40,0.18);
    }}

    .stButton > button:hover {{
        background-color: #4a6144;
        box-shadow: 0 3px 12px rgba(44,62,40,0.22);
        transform: translateY(-1px);
    }}

    .stButton > button:active {{
        transform: translateY(0);
        box-shadow: 0 1px 4px rgba(44,62,40,0.18);
    }}

    /* ---- Download button ---- */
    .stDownloadButton > button {{
        background-color: transparent;
        color: {COLORS['diep_bosgroen']};
        border: 1.5px solid {COLORS['diep_bosgroen']};
        border-radius: 6px;
        font-family: 'DM Sans', Helvetica, sans-serif;
        font-weight: 500;
        font-size: 0.875rem;
        padding: 8px 22px;
        transition: background 0.2s, color 0.2s;
    }}

    .stDownloadButton > button:hover {{
        background-color: {COLORS['diep_bosgroen']};
        color: {COLORS['wit']};
    }}

    /* ============================================================
       FORM INPUTS
    ============================================================ */
    .stTextInput input,
    .stSelectbox select,
    .stNumberInput input {{
        background: #FFFFFF;
        border: 1.5px solid rgba(59,78,55,0.18);
        border-radius: 6px;
        font-family: 'DM Sans', Helvetica, sans-serif;
        font-size: 0.9rem;
        color: {COLORS['tekst_donker']};
        transition: border-color 0.15s, box-shadow 0.15s;
    }}

    .stTextInput input:focus,
    .stSelectbox select:focus {{
        border-color: {COLORS['diep_bosgroen']};
        box-shadow: 0 0 0 3px rgba(59,78,55,0.12);
        outline: none;
    }}

    /* Slider */
    .stSlider [data-baseweb="slider"] {{
        padding: 8px 2px;
    }}

    /* ============================================================
       DATAFRAMES
    ============================================================ */
    .stDataFrame {{
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid rgba(59,78,55,0.1);
        box-shadow: 0 1px 8px rgba(44,62,40,0.05);
    }}

    .stDataFrame thead tr th {{
        background-color: {COLORS['diep_bosgroen']} !important;
        color: white !important;
        font-family: 'DM Sans', Helvetica, sans-serif !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        padding: 10px 14px !important;
    }}

    /* ============================================================
       EXPANDER
    ============================================================ */
    .streamlit-expanderHeader {{
        background-color: #FFFFFF !important;
        border-radius: 8px !important;
        border: 1.5px solid rgba(59,78,55,0.12) !important;
        font-family: 'DM Sans', Helvetica, sans-serif !important;
        color: {COLORS['diep_bosgroen']} !important;
        font-weight: 500 !important;
        transition: border-color 0.15s, background 0.15s;
    }}

    .streamlit-expanderHeader:hover {{
        border-color: {COLORS['diep_bosgroen']} !important;
        background-color: rgba(59,78,55,0.03) !important;
    }}

    .streamlit-expanderContent {{
        border: 1.5px solid rgba(59,78,55,0.12) !important;
        border-top: none !important;
        border-radius: 0 0 8px 8px !important;
        background: #FDFDFC !important;
    }}

    /* ============================================================
       FILE UPLOADER
    ============================================================ */
    .stFileUploader {{
        border: 2px dashed rgba(167,161,88,0.45);
        border-radius: 10px;
        padding: 16px;
        background: rgba(226,214,200,0.15);
        transition: border-color 0.2s, background 0.2s;
    }}

    .stFileUploader:hover {{
        border-color: {COLORS['zandgroen']};
        background: rgba(226,214,200,0.25);
    }}

    /* ============================================================
       ALERTS & MESSAGES
    ============================================================ */
    .stSuccess {{
        background: linear-gradient(135deg, #EEF4ED 0%, #E8F0E7 100%);
        border-left: 4px solid {COLORS['diep_bosgroen']};
        border-radius: 0 8px 8px 0;
    }}

    .stWarning {{
        background: linear-gradient(135deg, #FDF6EC 0%, #FAEED8 100%);
        border-left: 4px solid {COLORS['oranje_bruin']};
        border-radius: 0 8px 8px 0;
    }}

    .stError {{
        background: linear-gradient(135deg, #FDF0F0 0%, #F9E0E0 100%);
        border-left: 4px solid {COLORS['heide_paars']};
        border-radius: 0 8px 8px 0;
    }}

    .stInfo {{
        background: linear-gradient(135deg, #EEF4ED 0%, #E6EFE5 100%);
        border-left: 4px solid {COLORS['zandgroen']};
        border-radius: 0 8px 8px 0;
    }}

    /* ============================================================
       DIVIDERS
    ============================================================ */
    hr {{
        border: none !important;
        border-top: 1px solid rgba(59,78,55,0.12) !important;
        margin: 1.75rem 0 !important;
    }}

    /* ============================================================
       SPINNER
    ============================================================ */
    .stSpinner > div {{
        border-top-color: {COLORS['diep_bosgroen']} !important;
    }}

    /* ============================================================
       MULTISELECT TAGS
    ============================================================ */
    .stMultiSelect [data-baseweb="tag"] {{
        background-color: {COLORS['diep_bosgroen']} !important;
        color: {COLORS['wit']} !important;
        border-radius: 4px !important;
        font-size: 0.78rem !important;
    }}

    /* ============================================================
       PAGE TITLE STYLING — decorative rule under h1
    ============================================================ */
    .main h1 {{
        padding-bottom: 0.6rem;
        border-bottom: 1px solid rgba(59,78,55,0.15);
        margin-bottom: 1.4rem !important;
    }}

    /* ============================================================
       SIDEBAR "Guest Insights" title
    ============================================================ */
    section[data-testid="stSidebar"] .stMarkdown h3 {{
        font-family: 'Cormorant Garamond', Georgia, serif !important;
        font-size: 1.1rem !important;
        font-weight: 400 !important;
        color: rgba(226,214,200,0.75) !important;
        letter-spacing: 0.04em !important;
        text-transform: none !important;
        font-style: italic;
    }}

    /* ============================================================
       HIDE STREAMLIT CHROME
    ============================================================ */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
</style>
"""


def apply_style():
    """Return the custom CSS to be injected into the app."""
    return CUSTOM_CSS
