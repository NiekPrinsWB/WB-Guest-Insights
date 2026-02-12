"""
Westerbergen Guest Insights - Streamlit Custom CSS & Styling
Based on Westerbergen Brandbook 2025
"""
from app.config import COLORS

CUSTOM_CSS = f"""
<style>
    /* ---- Import Google Fonts ---- */
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500;600;700&display=swap');

    /* ---- Global ---- */
    .stApp {{
        background-color: {COLORS['licht_beige']};
    }}

    /* Main content area */
    .main .block-container {{
        padding-top: 2rem;
        max-width: 1200px;
    }}

    /* ---- Typography ---- */
    h1, h2, h3 {{
        font-family: 'Playfair Display', Georgia, serif !important;
        color: {COLORS['diep_bosgroen']} !important;
    }}

    h1 {{
        font-size: 2rem !important;
        font-weight: 700 !important;
    }}

    h2 {{
        font-size: 1.5rem !important;
        font-weight: 700 !important;
    }}

    h3 {{
        font-size: 1.15rem !important;
        font-weight: 600 !important;
    }}

    p, span, label, .stMarkdown {{
        font-family: 'Inter', Helvetica, Arial, sans-serif !important;
        color: {COLORS['tekst_donker']} !important;
    }}

    /* ---- Sidebar ---- */
    section[data-testid="stSidebar"] {{
        background-color: {COLORS['diep_bosgroen']} !important;
    }}

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown {{
        color: {COLORS['wit']} !important;
    }}

    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stMultiSelect label,
    section[data-testid="stSidebar"] .stDateInput label {{
        color: {COLORS['natuurlijk_beige']} !important;
    }}

    /* ---- Metric cards ---- */
    div[data-testid="stMetric"] {{
        background-color: {COLORS['wit']};
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 4px rgba(59, 78, 55, 0.08);
        border-left: 4px solid {COLORS['diep_bosgroen']};
    }}

    div[data-testid="stMetric"] label {{
        font-family: 'Inter', Helvetica, sans-serif !important;
        color: {COLORS['tekst_licht']} !important;
        font-size: 0.8rem !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
        font-family: 'Playfair Display', Georgia, serif !important;
        color: {COLORS['diep_bosgroen']} !important;
        font-size: 2rem !important;
    }}

    /* ---- Tabs ---- */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
    }}

    .stTabs [data-baseweb="tab"] {{
        background-color: {COLORS['natuurlijk_beige']};
        border-radius: 8px 8px 0 0;
        padding: 8px 20px;
        font-family: 'Inter', Helvetica, sans-serif;
        color: {COLORS['diep_bosgroen']};
    }}

    .stTabs [aria-selected="true"] {{
        background-color: {COLORS['diep_bosgroen']} !important;
        color: {COLORS['wit']} !important;
    }}

    /* ---- Buttons ---- */
    .stButton > button {{
        background-color: {COLORS['diep_bosgroen']};
        color: {COLORS['wit']};
        border: none;
        border-radius: 8px;
        font-family: 'Inter', Helvetica, sans-serif;
        font-weight: 500;
        padding: 8px 24px;
        transition: all 0.2s;
    }}

    .stButton > button:hover {{
        background-color: {COLORS['zandgroen']};
        color: {COLORS['wit']};
    }}

    /* ---- DataFrames ---- */
    .stDataFrame {{
        border-radius: 8px;
        overflow: hidden;
    }}

    /* ---- Expander ---- */
    .streamlit-expanderHeader {{
        background-color: {COLORS['natuurlijk_beige']};
        border-radius: 8px;
        font-family: 'Inter', Helvetica, sans-serif;
        color: {COLORS['diep_bosgroen']};
    }}

    /* ---- File uploader ---- */
    .stFileUploader {{
        border: 2px dashed {COLORS['zandgroen']};
        border-radius: 12px;
        padding: 12px;
    }}

    /* ---- Divider ---- */
    hr {{
        border-color: {COLORS['natuurlijk_beige']};
    }}

    /* ---- Download button ---- */
    .stDownloadButton > button {{
        background-color: {COLORS['zandgroen']};
        color: {COLORS['wit']};
        border: none;
        border-radius: 8px;
    }}

    .stDownloadButton > button:hover {{
        background-color: {COLORS['diep_bosgroen']};
    }}

    /* ---- Success/Warning/Error ---- */
    .stSuccess {{
        background-color: #e8f5e9;
        border-left-color: {COLORS['diep_bosgroen']};
    }}

    /* Hide Streamlit branding */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
</style>
"""


def apply_style():
    """Return the custom CSS to be injected into the app."""
    return CUSTOM_CSS
