
import streamlit as st


def apply_theme():
    if "rm_dark_mode" not in st.session_state:
        st.session_state.rm_dark_mode = False

    with st.sidebar:
        st.checkbox(
            "Dark mode",
            key="rm_dark_mode",
            help="Switch the workspace between light and dark appearance."
        )

    dark = bool(st.session_state.rm_dark_mode)

    if dark:
        colors = {
            "bg": "#101918",
            "panel": "#192522",
            "panel_alt": "#202f2a",
            "text": "#e8f0ec",
            "muted": "#a0b2aa",
            "border": "#34463f",
            "accent": "#65bd96",
            "accent_hover": "#4da77e",
            "input": "#202e29",
            "shadow": "rgba(0,0,0,0.18)",
        }
    else:
        colors = {
            "bg": "#f4f7f5",
            "panel": "#ffffff",
            "panel_alt": "#edf3ef",
            "text": "#20332b",
            "muted": "#65756c",
            "border": "#dce6df",
            "accent": "#28765b",
            "accent_hover": "#1d6048",
            "input": "#ffffff",
            "shadow": "rgba(30,60,45,0.05)",
        }

    bg = colors["bg"]
    panel = colors["panel"]
    panel_alt = colors["panel_alt"]
    text = colors["text"]
    muted = colors["muted"]
    border = colors["border"]
    accent = colors["accent"]
    accent_hover = colors["accent_hover"]
    input_bg = colors["input"]
    shadow = colors["shadow"]

    st.markdown(
        f"""
        <style>

        /* =========================================
           GLOBAL THEME
        ========================================= */

        :root {{
            color-scheme: {"dark" if dark else "light"};

            --rm-bg: {bg};
            --rm-panel: {panel};
            --rm-panel-alt: {panel_alt};
            --rm-text: {text};
            --rm-muted: {muted};
            --rm-border: {border};
            --rm-accent: {accent};
            --rm-accent-hover: {accent_hover};
        }}

        html, body, .stApp {{
            background-color: {bg} !important;
            color: {text} !important;
        }}

        .stApp,
        .main,
        [data-testid="stAppViewContainer"] {{
            background: {bg} !important;
            color: {text} !important;
        }}

        .block-container {{
            max-width: 1500px;
            padding-top: 2rem !important;
            padding-bottom: 3rem !important;
        }}

        /* =========================================
           TOP HEADER AND TOOLBAR
        ========================================= */

        header,
        header[data-testid="stHeader"],
        [data-testid="stHeader"],
        .stAppHeader {{
            background: {bg} !important;
            background-color: {bg} !important;
            border-bottom: 1px solid {border} !important;
            box-shadow: none !important;
        }}

        [data-testid="stToolbar"] {{
            background: transparent !important;
        }}

        [data-testid="stDecoration"] {{
            background: {accent} !important;
        }}

        [data-testid="stToolbar"] button,
        [data-testid="stHeader"] button {{
            color: {text} !important;
        }}

        /* =========================================
           SIDEBAR
        ========================================= */

        section[data-testid="stSidebar"] {{
            background: {panel} !important;
            border-right: 1px solid {border} !important;
        }}

        section[data-testid="stSidebar"] > div {{
            background: {panel} !important;
        }}

        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {{
            color: {text} !important;
        }}

        /* =========================================
           TYPOGRAPHY
        ========================================= */

        .stApp,
        .stApp p,
        .stApp li,
        .stApp label {{
            color: {text};
        }}

        h1, h2, h3, h4 {{
            color: {text} !important;
            letter-spacing: -0.035em;
        }}

        .main-title,
        .rm-title {{
            color: {text} !important;
            font-size: 2.15rem;
            font-weight: 780;
            letter-spacing: -0.055em;
            line-height: 1.2;
            margin: 0.25rem 0 0.45rem;
        }}

        .subtitle,
        .rm-subtitle {{
            color: {muted} !important;
            font-size: 0.98rem;
            margin-bottom: 1.15rem;
        }}

        .rm-eyebrow {{
            color: {accent} !important;
            text-transform: uppercase;
            letter-spacing: 0.13em;
            font-size: 0.72rem;
            font-weight: 750;
        }}

        .panel-heading {{
            color: {text} !important;
            font-size: 1.12rem;
            font-weight: 720;
            letter-spacing: -0.025em;
            margin-bottom: 0.3rem;
        }}

        .rm-kicker {{
            color: {muted} !important;
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}

        /* =========================================
           STATUS BADGES AND PANELS
        ========================================= */

        .status {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            border: 1px solid {border};
            background: {panel_alt};
            color: {accent} !important;
            border-radius: 999px;
            padding: 0.4rem 0.75rem;
            font-size: 0.76rem;
            font-weight: 700;
        }}

        .rm-panel {{
            background: {panel};
            border: 1px solid {border};
            border-radius: 16px;
            padding: 1rem 1.1rem;
            box-shadow: 0 3px 12px {shadow};
        }}

        /* =========================================
           METRICS
        ========================================= */

        div[data-testid="stMetric"] {{
            background: {panel} !important;
            border: 1px solid {border} !important;
            border-radius: 13px;
            padding: 0.85rem 1rem;
            box-shadow: 0 2px 8px {shadow};
        }}

        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {{
            color: {muted} !important;
        }}

        div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
            color: {text} !important;
        }}

        /* =========================================
           BUTTONS
        ========================================= */

        .stButton > button,
        .stDownloadButton > button,
        .stFormSubmitButton > button {{
            background: {panel} !important;
            color: {text} !important;
            border: 1px solid {border} !important;
            border-radius: 10px !important;
            min-height: 2.55rem;
            font-weight: 650;
            transition: all 0.18s ease;
        }}

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stFormSubmitButton > button:hover {{
            border-color: {accent} !important;
            color: {accent} !important;
            background: {panel_alt} !important;
        }}

        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"] {{
            background: {accent} !important;
            border-color: {accent} !important;
            color: #ffffff !important;
        }}

        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover {{
            background: {accent_hover} !important;
            border-color: {accent_hover} !important;
            color: #ffffff !important;
        }}

        /* =========================================
           INPUTS AND TEXT AREAS
        ========================================= */

        .stTextInput input,
        .stTextArea textarea,
        .stNumberInput input,
        [data-testid="stChatInput"] textarea {{
            background: {input_bg} !important;
            color: {text} !important;
            border: 1px solid {border} !important;
            border-radius: 10px !important;
            caret-color: {accent};
        }}

        .stTextInput input::placeholder,
        .stTextArea textarea::placeholder,
        [data-testid="stChatInput"] textarea::placeholder {{
            color: {muted} !important;
            opacity: 0.85;
        }}

        .stTextInput input:focus,
        .stTextArea textarea:focus,
        .stNumberInput input:focus {{
            border-color: {accent} !important;
            box-shadow: 0 0 0 1px {accent} !important;
        }}

        /* =========================================
           SELECTBOX AND DROPDOWNS
        ========================================= */

        [data-baseweb="select"] > div {{
            background: {input_bg} !important;
            background-color: {input_bg} !important;
            color: {text} !important;
            border-color: {border} !important;
            border-radius: 10px !important;
        }}

        [data-baseweb="select"] div,
        [data-baseweb="select"] span,
        [data-baseweb="select"] input {{
            color: {text} !important;
        }}

        [data-baseweb="select"] svg {{
            fill: {text} !important;
        }}

        [data-baseweb="popover"],
        [data-baseweb="menu"],
        [role="listbox"] {{
            background: {panel} !important;
            background-color: {panel} !important;
            border: 1px solid {border} !important;
        }}

        [role="option"] {{
            background: {panel} !important;
            color: {text} !important;
        }}

        [role="option"]:hover {{
            background: {panel_alt} !important;
        }}

        /* =========================================
           RADIO BUTTONS AND CHECKBOXES
        ========================================= */

        [data-testid="stWidgetLabel"],
        [data-testid="stWidgetLabel"] p,
        .stRadio label,
        .stCheckbox label {{
            color: {text} !important;
        }}

        [data-testid="stRadio"] label,
        [data-testid="stCheckbox"] label {{
            color: {text} !important;
        }}

        /* =========================================
           FILE UPLOADER
        ========================================= */

        [data-testid="stFileUploader"] {{
            background: {panel} !important;
            border: 1px dashed {accent} !important;
            border-radius: 13px !important;
            padding: 0.7rem !important;
        }}

        [data-testid="stFileUploader"] section {{
            background: {panel} !important;
            border-color: {border} !important;
        }}

        [data-testid="stFileUploader"] small,
        [data-testid="stFileUploader"] span,
        [data-testid="stFileUploader"] label {{
            color: {text} !important;
        }}

        [data-testid="stFileUploader"] button {{
            background: {panel_alt} !important;
            color: {text} !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
        }}

        /* =========================================
           CHAT
        ========================================= */

        [data-testid="stChatMessage"] {{
            background: {panel} !important;
            border: 1px solid {border} !important;
            border-radius: 13px !important;
            padding: 0.8rem !important;
        }}

        [data-testid="stChatInput"] {{
            background: {panel} !important;
            border: 1px solid {border} !important;
            border-radius: 12px !important;
        }}

        /* =========================================
           ALERTS AND NOTIFICATIONS
        ========================================= */

        [data-testid="stAlert"],
        [data-testid="stAlert"] > div,
        [data-testid="stAlertContent"],
        [data-baseweb="notification"] {{
            background: {panel_alt} !important;
            background-color: {panel_alt} !important;
            color: {text} !important;
            border-color: {border} !important;
            border-radius: 11px !important;
        }}

        [data-testid="stAlert"] *,
        [data-testid="stAlertContent"] *,
        [data-baseweb="notification"] * {{
            color: {text} !important;
        }}

        [data-testid="stAlert"] svg,
        [data-testid="stAlert"] path {{
            fill: {accent} !important;
            color: {accent} !important;
        }}

        /* =========================================
           EXPANDERS AND CAPTIONS
        ========================================= */

        [data-testid="stExpander"] {{
            background: {panel} !important;
            border: 1px solid {border} !important;
            border-radius: 12px !important;
        }}

        [data-testid="stExpander"] summary {{
            color: {text} !important;
        }}

        [data-testid="stExpander"] summary span {{
            color: {text} !important;
        }}

        .stCaption,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p {{
            color: {muted} !important;
        }}

        hr {{
            border-color: {border} !important;
        }}

        /* =========================================
           RESPONSIVE LAYOUT
        ========================================= */

        @media (max-width: 800px) {{
            .block-container {{
                padding: 1rem 0.8rem 2rem !important;
            }}

            .main-title,
            .rm-title {{
                font-size: 1.65rem;
            }}
        }}

        </style>
        """,
        unsafe_allow_html=True
    )


def page_header(eyebrow: str, title: str, subtitle: str):
    st.markdown(
        f"""
        <div class="rm-eyebrow">{eyebrow}</div>
        <div class="rm-title">{title}</div>
        <div class="rm-subtitle">{subtitle}</div>
        """,
        unsafe_allow_html=True
    )


def provider_picker(key="rm_feature_provider"):
    from app_config import PROVIDER_GEMINI, PROVIDER_QWEN

    return st.selectbox(
        "AI provider",
        [PROVIDER_GEMINI, PROVIDER_QWEN],
        key=key
    )
