import streamlit as st


# ============================================================
# RESEARCHMIND AI — PREMIUM MIDNIGHT DESIGN SYSTEM
# ============================================================

def apply_theme():

    colors = {
        "bg": "#050B18",
        "sidebar": "#080F1E",
        "panel": "#0B1527",
        "panel_alt": "#101E34",
        "input": "#091326",
        "text": "#F1F5F9",
        "muted": "#94A3B8",
        "border": "#1C2D49",
        "accent": "#3B82F6",
        "accent_light": "#60A5FA",
        "cyan": "#22D3EE",
        "accent_hover": "#2563EB",
    }

    st.markdown(
        f"""
        <style>

        /* ==================================================
           GLOBAL DESIGN SYSTEM
        ================================================== */

        :root {{
            color-scheme: dark;

            --rm-bg: {colors["bg"]};
            --rm-sidebar: {colors["sidebar"]};
            --rm-panel: {colors["panel"]};
            --rm-panel-alt: {colors["panel_alt"]};
            --rm-input: {colors["input"]};
            --rm-text: {colors["text"]};
            --rm-muted: {colors["muted"]};
            --rm-border: {colors["border"]};
            --rm-accent: {colors["accent"]};
            --rm-cyan: {colors["cyan"]};
        }}

        html, body, .stApp {{
            background: {colors["bg"]} !important;
            color: {colors["text"]} !important;
        }}

        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        .main {{
            background:
                radial-gradient(
                    ellipse at 85% 5%,
                    rgba(30, 64, 175, 0.12),
                    transparent 35%
                ),
                {colors["bg"]} !important;

            color: {colors["text"]} !important;
        }}

        .block-container {{
            max-width: 1550px;
            padding-top: 2.2rem !important;
            padding-bottom: 3rem !important;
        }}

        /* ==================================================
           TOP HEADER
        ================================================== */

        header,
        [data-testid="stHeader"],
        .stAppHeader {{
            background: rgba(5, 11, 24, 0.94) !important;
            border-bottom: 1px solid {colors["border"]} !important;
            box-shadow: none !important;
        }}

        [data-testid="stToolbar"] {{
            background: transparent !important;
        }}

        [data-testid="stDecoration"] {{
            background: linear-gradient(
                90deg,
                {colors["accent"]},
                {colors["cyan"]}
            ) !important;
            height: 2px !important;
        }}

        /* ==================================================
           SIDEBAR
        ================================================== */

        section[data-testid="stSidebar"] {{
            background: {colors["sidebar"]} !important;
            border-right: 1px solid {colors["border"]} !important;
        }}

        section[data-testid="stSidebar"] > div {{
            background: {colors["sidebar"]} !important;
        }}

        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {{
            color: {colors["text"]} !important;
        }}

        [data-testid="stSidebar"] hr {{
            border-color: {colors["border"]} !important;
        }}

        [data-testid="stSidebar"] .stButton > button {{
            width: 100%;
            background: {colors["panel"]} !important;
            border: 1px solid {colors["border"]} !important;
            color: {colors["text"]} !important;
            border-radius: 10px !important;
        }}

        [data-testid="stSidebar"] .stButton > button:hover {{
            background: {colors["panel_alt"]} !important;
            border-color: {colors["accent"]} !important;
            color: {colors["accent_light"]} !important;
        }}

        /* ==================================================
           TYPOGRAPHY
        ================================================== */

        .stApp,
        .stApp p,
        .stApp li,
        .stApp label {{
            color: {colors["text"]};
        }}

        h1, h2, h3, h4, h5 {{
            color: {colors["text"]} !important;
            letter-spacing: -0.035em !important;
            font-weight: 700 !important;
        }}

        .main-title,
        .rm-title {{
            font-size: clamp(1.8rem, 3vw, 2.65rem);
            font-weight: 800 !important;
            letter-spacing: -0.055em !important;
            line-height: 1.15;
            margin: 0.3rem 0 0.6rem;
            color: {colors["text"]} !important;
        }}

        .subtitle,
        .rm-subtitle {{
            color: {colors["muted"]} !important;
            font-size: 1rem;
            line-height: 1.6;
            margin-bottom: 1.5rem;
        }}

        .rm-eyebrow {{
            color: {colors["accent_light"]} !important;
            text-transform: uppercase;
            letter-spacing: 0.15em;
            font-size: 0.72rem;
            font-weight: 750;
        }}

        .panel-heading {{
            color: {colors["text"]} !important;
            font-size: 1.15rem;
            font-weight: 750;
            letter-spacing: -0.025em;
            margin-bottom: 0.4rem;
        }}

        .rm-kicker {{
            color: {colors["muted"]} !important;
            font-size: 0.73rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }}

        /* ==================================================
           PREMIUM PANELS
        ================================================== */

        .rm-panel {{
            background: linear-gradient(
                145deg,
                rgba(15, 29, 51, 0.98),
                rgba(8, 18, 34, 0.98)
            ) !important;

            border: 1px solid {colors["border"]};
            border-radius: 17px;
            padding: 1.3rem;
            box-shadow: 0 12px 35px rgba(0, 0, 0, 0.20);
        }}

        .rm-card {{
            background: {colors["panel"]};
            border: 1px solid {colors["border"]};
            border-radius: 14px;
            padding: 1.15rem;
            transition: all 0.2s ease;
        }}

        .rm-card:hover {{
            border-color: rgba(59, 130, 246, 0.55);
            box-shadow: 0 8px 25px rgba(37, 99, 235, 0.10);
            transform: translateY(-2px);
        }}

        /* ==================================================
           STATUS INDICATORS
        ================================================== */

        .status {{
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.45rem 0.85rem;
            border-radius: 999px;

            background: rgba(59, 130, 246, 0.10);
            border: 1px solid rgba(59, 130, 246, 0.28);

            color: {colors["accent_light"]} !important;
            font-size: 0.77rem;
            font-weight: 700;
        }}

        .rm-online {{
            display: inline-flex;
            align-items: center;
            gap: 7px;
            color: #34D399 !important;
            font-size: 0.78rem;
            font-weight: 650;
        }}

        .rm-online::before {{
            content: "";
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #34D399;
            box-shadow: 0 0 10px rgba(52, 211, 153, 0.55);
        }}

        /* ==================================================
           METRIC CARDS
        ================================================== */

        div[data-testid="stMetric"] {{
            background: linear-gradient(
                145deg,
                {colors["panel_alt"]},
                {colors["panel"]}
            ) !important;

            border: 1px solid {colors["border"]} !important;
            border-radius: 14px !important;
            padding: 1rem 1.1rem !important;

            box-shadow: 0 5px 18px rgba(0, 0, 0, 0.16);
        }}

        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {{
            color: {colors["muted"]} !important;
        }}

        div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
            color: {colors["text"]} !important;
            font-weight: 750 !important;
        }}

        /* ==================================================
           BUTTONS
        ================================================== */

        .stButton > button,
        .stDownloadButton > button,
        .stFormSubmitButton > button {{
            background: {colors["panel_alt"]} !important;
            color: {colors["text"]} !important;

            border: 1px solid {colors["border"]} !important;
            border-radius: 10px !important;

            min-height: 2.65rem;
            font-weight: 650 !important;

            transition: all 0.2s ease !important;
        }}

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stFormSubmitButton > button:hover {{
            background: rgba(59, 130, 246, 0.12) !important;
            border-color: {colors["accent"]} !important;
            color: {colors["accent_light"]} !important;
            box-shadow: 0 0 16px rgba(59, 130, 246, 0.12);
        }}

        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"] {{
            background: linear-gradient(
                105deg,
                #2563EB,
                #0EA5E9
            ) !important;

            border: 1px solid #3B82F6 !important;
            color: white !important;
            font-weight: 750 !important;

            box-shadow: 0 5px 20px rgba(37, 99, 235, 0.22);
        }}

        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover {{
            background: linear-gradient(
                105deg,
                #1D4ED8,
                #0284C7
            ) !important;

            box-shadow: 0 6px 24px rgba(37, 99, 235, 0.35);
            color: white !important;
        }}

        /* ==================================================
           INPUTS
        ================================================== */

        .stTextInput input,
        .stTextArea textarea,
        .stNumberInput input,
        [data-testid="stChatInput"] textarea {{
            background: {colors["input"]} !important;
            color: {colors["text"]} !important;

            border: 1px solid {colors["border"]} !important;
            border-radius: 11px !important;

            caret-color: {colors["accent_light"]} !important;
        }}

        .stTextInput input::placeholder,
        .stTextArea textarea::placeholder,
        [data-testid="stChatInput"] textarea::placeholder {{
            color: {colors["muted"]} !important;
            opacity: 0.8;
        }}

        .stTextInput input:focus,
        .stTextArea textarea:focus,
        .stNumberInput input:focus {{
            border-color: {colors["accent"]} !important;
            box-shadow: 0 0 0 1px {colors["accent"]} !important;
        }}

        /* ==================================================
           SELECTBOX AND DROPDOWNS
        ================================================== */

        [data-baseweb="select"] > div {{
            background: {colors["input"]} !important;
            color: {colors["text"]} !important;
            border-color: {colors["border"]} !important;
            border-radius: 10px !important;
        }}

        [data-baseweb="select"] div,
        [data-baseweb="select"] span,
        [data-baseweb="select"] input {{
            color: {colors["text"]} !important;
        }}

        [data-baseweb="select"] svg {{
            fill: {colors["accent_light"]} !important;
        }}

        [data-baseweb="popover"],
        [data-baseweb="menu"],
        [role="listbox"] {{
            background: {colors["panel"]} !important;
            border: 1px solid {colors["border"]} !important;
        }}

        [role="option"] {{
            background: {colors["panel"]} !important;
            color: {colors["text"]} !important;
        }}

        [role="option"]:hover {{
            background: {colors["panel_alt"]} !important;
        }}

        /* ==================================================
           RADIO BUTTONS AND CHECKBOXES
        ================================================== */

        [data-testid="stWidgetLabel"],
        [data-testid="stWidgetLabel"] p,
        .stRadio label,
        .stCheckbox label {{
            color: {colors["text"]} !important;
        }}

        [data-testid="stRadio"] label,
        [data-testid="stCheckbox"] label {{
            color: {colors["text"]} !important;
        }}

        /* ==================================================
           FILE UPLOADER
        ================================================== */

        [data-testid="stFileUploader"] {{
            background: rgba(11, 21, 39, 0.85) !important;
            border: 1px dashed {colors["accent"]} !important;
            border-radius: 14px !important;
            padding: 0.8rem !important;
        }}

        [data-testid="stFileUploader"] section {{
            background: {colors["panel"]} !important;
            border-color: {colors["border"]} !important;
        }}

        [data-testid="stFileUploader"] small,
        [data-testid="stFileUploader"] span,
        [data-testid="stFileUploader"] label {{
            color: {colors["text"]} !important;
        }}

        [data-testid="stFileUploader"] button {{
            background: {colors["panel_alt"]} !important;
            color: {colors["text"]} !important;
            border: 1px solid {colors["border"]} !important;
            border-radius: 8px !important;
        }}

        /* ==================================================
           CHAT INTERFACE
        ================================================== */

        [data-testid="stChatMessage"] {{
            background: {colors["panel"]} !important;
            border: 1px solid {colors["border"]} !important;
            border-radius: 14px !important;
            padding: 1rem !important;
            margin-bottom: 0.8rem;
        }}

        [data-testid="stChatInput"] {{
            background: {colors["panel"]} !important;
            border: 1px solid {colors["border"]} !important;
            border-radius: 13px !important;
        }}

        [data-testid="stChatInput"] textarea {{
            background: transparent !important;
            border: none !important;
        }}

        /* ==================================================
           ALERTS
        ================================================== */

        [data-testid="stAlert"],
        [data-testid="stAlert"] > div,
        [data-testid="stAlertContent"],
        [data-baseweb="notification"] {{
            background: {colors["panel_alt"]} !important;
            color: {colors["text"]} !important;
            border-color: {colors["border"]} !important;
            border-radius: 11px !important;
        }}

        [data-testid="stAlert"] *,
        [data-testid="stAlertContent"] *,
        [data-baseweb="notification"] * {{
            color: {colors["text"]} !important;
        }}

        /* ==================================================
           EXPANDERS
        ================================================== */

        [data-testid="stExpander"] {{
            background: {colors["panel"]} !important;
            border: 1px solid {colors["border"]} !important;
            border-radius: 13px !important;
        }}

        [data-testid="stExpander"] summary {{
            color: {colors["text"]} !important;
        }}

        [data-testid="stExpander"] summary span {{
            color: {colors["text"]} !important;
        }}

        /* ==================================================
           CAPTIONS AND DIVIDERS
        ================================================== */

        .stCaption,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p {{
            color: {colors["muted"]} !important;
        }}

        hr {{
            border-color: {colors["border"]} !important;
        }}

        /* ==================================================
           PROGRESS BARS
        ================================================== */

        [data-testid="stProgressBar"] > div {{
            background: {colors["panel_alt"]} !important;
            border-radius: 20px !important;
        }}

        [data-testid="stProgressBar"] > div > div {{
            background: linear-gradient(
                90deg,
                {colors["accent"]},
                {colors["cyan"]}
            ) !important;
            border-radius: 20px !important;
        }}

        /* ==================================================
           SCROLLBAR
        ================================================== */

        ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}

        ::-webkit-scrollbar-track {{
            background: {colors["bg"]};
        }}

        ::-webkit-scrollbar-thumb {{
            background: #263A58;
            border-radius: 20px;
        }}

        ::-webkit-scrollbar-thumb:hover {{
            background: {colors["accent"]};
        }}

        /* ==================================================
           RESPONSIVE DESIGN
        ================================================== */

        @media (max-width: 800px) {{

            .block-container {{
                padding: 1rem 0.8rem 2rem !important;
            }}

            .main-title,
            .rm-title {{
                font-size: 1.75rem;
            }}

            .rm-panel {{
                padding: 0.85rem;
            }}
        }}

        </style>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# REUSABLE PAGE HEADER
# ============================================================

def page_header(eyebrow: str, title: str, subtitle: str):

    st.markdown(
        f"""
        <div class="rm-eyebrow">{eyebrow}</div>
        <div class="rm-title">{title}</div>
        <div class="rm-subtitle">{subtitle}</div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# AI PROVIDER PICKER
# ============================================================

def provider_picker(key="rm_feature_provider"):

    from app_config import PROVIDER_GEMINI, PROVIDER_QWEN

    return st.selectbox(
        "AI provider",
        [
            PROVIDER_GEMINI,
            PROVIDER_QWEN
        ],
        key=key
    )
