import streamlit as st


def apply_theme():

    # =========================================
    # THEME SETTINGS
    # =========================================

    if "rm_dark_mode" not in st.session_state:
        st.session_state.rm_dark_mode = True

    with st.sidebar:

        st.markdown(
            """
            <div style="
                font-size:11px;
                font-weight:700;
                letter-spacing:2px;
                color:#80C9BD;
                margin-bottom:8px;
            ">
                APPEARANCE
            </div>
            """,
            unsafe_allow_html=True
        )

        st.checkbox(
            "Dark mode",
            key="rm_dark_mode",
            help="Switch between dark and light appearance."
        )

    dark = bool(st.session_state.rm_dark_mode)

    # =========================================
    # PREMIUM COLOR PALETTE
    # =========================================

    if dark:

        colors = {
            "bg": "#0B1220",
            "panel": "#111C2E",
            "panel_alt": "#172438",
            "input": "#101B2D",

            "text": "#E8EEF6",
            "muted": "#94A5BA",

            "border": "#26364C",

            "accent": "#55B9A8",
            "accent_hover": "#3F9E90",

            "accent_soft": "#193B3C",

            "shadow": "rgba(0,0,0,0.28)"
        }

    else:

        colors = {
            "bg": "#F3F6F8",
            "panel": "#FFFFFF",
            "panel_alt": "#EDF2F5",
            "input": "#FFFFFF",

            "text": "#172638",
            "muted": "#697B8E",

            "border": "#DCE5EB",

            "accent": "#287F78",
            "accent_hover": "#206B65",

            "accent_soft": "#E1F1ED",

            "shadow": "rgba(25,45,65,0.06)"
        }

    bg = colors["bg"]
    panel = colors["panel"]
    panel_alt = colors["panel_alt"]
    input_bg = colors["input"]

    text = colors["text"]
    muted = colors["muted"]
    border = colors["border"]

    accent = colors["accent"]
    accent_hover = colors["accent_hover"]
    accent_soft = colors["accent_soft"]

    shadow = colors["shadow"]

    # =========================================
    # PREMIUM CSS
    # =========================================

    st.markdown(
        f"""
        <style>

        :root {{

            color-scheme: {"dark" if dark else "light"};

            --rm-bg: {bg};
            --rm-panel: {panel};
            --rm-panel-alt: {panel_alt};
            --rm-input: {input_bg};

            --rm-text: {text};
            --rm-muted: {muted};

            --rm-border: {border};

            --rm-accent: {accent};
            --rm-accent-hover: {accent_hover};
            --rm-accent-soft: {accent_soft};

        }}

        /* =====================================
           GLOBAL APPLICATION
        ===================================== */

        html,
        body,
        .stApp,
        [data-testid="stAppViewContainer"] {{

            background: {bg} !important;
            color: {text} !important;

        }}

        .stApp {{

            font-family:
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;

        }}

        .main .block-container {{

            max-width: 1550px;

            padding-top: 2.3rem !important;
            padding-bottom: 3rem !important;
            padding-left: 2.5rem !important;
            padding-right: 2.5rem !important;

        }}

        /* =====================================
           TOP HEADER
        ===================================== */

        header,
        [data-testid="stHeader"],
        .stAppHeader {{

            background: {bg} !important;
            border-bottom: 1px solid {border} !important;

        }}

        [data-testid="stToolbar"] {{

            background: transparent !important;

        }}

        [data-testid="stDecoration"] {{

            background: {accent} !important;

        }}

        /* =====================================
           SIDEBAR
        ===================================== */

        section[data-testid="stSidebar"] {{

            background: {panel} !important;

            border-right:
                1px solid {border} !important;

        }}

        section[data-testid="stSidebar"] > div {{

            background: {panel} !important;

        }}

        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{

            gap: 0.8rem;

        }}

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label {{

            color: {text} !important;

        }}

        [data-testid="stSidebar"] hr {{

            border-color: {border} !important;

        }}

        /* =====================================
           TYPOGRAPHY
        ===================================== */

        h1,
        h2,
        h3,
        h4 {{

            color: {text} !important;

            letter-spacing: -0.035em;

            font-weight: 700 !important;

        }}

        .main-title,
        .rm-title {{

            color: {text} !important;

            font-size: 2.35rem;

            font-weight: 780;

            letter-spacing: -0.055em;

            line-height: 1.2;

            margin: 0.2rem 0 0.55rem;

        }}

        .subtitle,
        .rm-subtitle {{

            color: {muted} !important;

            font-size: 1rem;

            line-height: 1.6;

            margin-bottom: 1.5rem;

        }}

        .rm-eyebrow {{

            color: {accent} !important;

            text-transform: uppercase;

            letter-spacing: 0.16em;

            font-size: 0.72rem;

            font-weight: 750;

            margin-bottom: 0.5rem;

        }}

        .panel-heading {{

            color: {text} !important;

            font-size: 1.2rem;

            font-weight: 730;

            letter-spacing: -0.035em;

            margin-bottom: 0.4rem;

        }}

        .rm-kicker {{

            color: {muted} !important;

            font-size: 0.72rem;

            font-weight: 700;

            text-transform: uppercase;

            letter-spacing: 0.12em;

        }}

        /* =====================================
           STATUS BADGES
        ===================================== */

        .status {{

            display: inline-flex;

            align-items: center;

            gap: 0.5rem;

            background: {accent_soft};

            border: 1px solid {border};

            color: {accent} !important;

            border-radius: 999px;

            padding: 0.48rem 0.85rem;

            font-size: 0.76rem;

            font-weight: 700;

        }}

        /* =====================================
           RESEARCH PANELS
        ===================================== */

        .rm-panel {{

            background: {panel};

            border: 1px solid {border};

            border-radius: 16px;

            padding: 1.25rem;

            box-shadow:
                0 8px 25px {shadow};

        }}

        [data-testid="stVerticalBlockBorderWrapper"] {{

            border-color: {border} !important;

            border-radius: 15px !important;

            background: {panel} !important;

        }}

        /* =====================================
           BUTTONS
        ===================================== */

        .stButton > button,
        .stDownloadButton > button,
        .stFormSubmitButton > button {{

            background: {panel_alt} !important;

            color: {text} !important;

            border: 1px solid {border} !important;

            border-radius: 10px !important;

            min-height: 2.65rem;

            font-weight: 650;

            transition: all 0.2s ease;

        }}

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stFormSubmitButton > button:hover {{

            border-color: {accent} !important;

            color: {accent} !important;

            background: {accent_soft} !important;

            transform: translateY(-1px);

        }}

        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"] {{

            background: {accent} !important;

            color: #071A19 !important;

            border: 1px solid {accent} !important;

            font-weight: 750;

        }}

        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover {{

            background: {accent_hover} !important;

            color: #FFFFFF !important;

        }}

        /* =====================================
           INPUT FIELDS
        ===================================== */

        .stTextInput input,
        .stTextArea textarea,
        .stNumberInput input,
        [data-testid="stChatInput"] textarea {{

            background: {input_bg} !important;

            color: {text} !important;

            border: 1px solid {border} !important;

            border-radius: 10px !important;

            caret-color: {accent} !important;

        }}

        .stTextInput input:focus,
        .stTextArea textarea:focus,
        .stNumberInput input:focus {{

            border-color: {accent} !important;

            box-shadow:
                0 0 0 1px {accent} !important;

        }}

        .stTextInput input::placeholder,
        .stTextArea textarea::placeholder,
        [data-testid="stChatInput"] textarea::placeholder {{

            color: {muted} !important;

        }}

        /* =====================================
           SELECTBOX
        ===================================== */

        [data-baseweb="select"] > div {{

            background: {input_bg} !important;

            border-color: {border} !important;

            border-radius: 10px !important;

        }}

        [data-baseweb="select"] * {{

            color: {text} !important;

        }}

        [data-baseweb="select"] svg {{

            fill: {muted} !important;

        }}

        [data-baseweb="popover"],
        [data-baseweb="menu"],
        [role="listbox"] {{

            background: {panel} !important;

            border: 1px solid {border} !important;

        }}

        [role="option"] {{

            background: {panel} !important;

            color: {text} !important;

        }}

        [role="option"]:hover {{

            background: {panel_alt} !important;

        }}

        /* =====================================
           RADIO AND CHECKBOX
        ===================================== */

        [data-testid="stWidgetLabel"],
        [data-testid="stWidgetLabel"] p,
        [data-testid="stRadio"] label,
        [data-testid="stCheckbox"] label {{

            color: {text} !important;

        }}

        /* =====================================
           FILE UPLOADER
        ===================================== */

        [data-testid="stFileUploader"] {{

            background: {panel};

            border: 1px dashed {accent} !important;

            border-radius: 13px !important;

            padding: 0.8rem !important;

        }}

        [data-testid="stFileUploader"] section {{

            background: {panel_alt} !important;

            border-color: {border} !important;

        }}

        [data-testid="stFileUploader"] button {{

            background: {panel} !important;

            color: {text} !important;

            border: 1px solid {border} !important;

            border-radius: 8px !important;

        }}

        [data-testid="stFileUploader"] * {{

            color: {text};

        }}

        /* =====================================
           METRICS
        ===================================== */

        div[data-testid="stMetric"] {{

            background: {panel};

            border: 1px solid {border};

            border-radius: 13px;

            padding: 1rem;

            box-shadow:
                0 4px 15px {shadow};

        }}

        [data-testid="stMetricLabel"] {{

            color: {muted} !important;

        }}

        [data-testid="stMetricValue"] {{

            color: {text} !important;

            font-weight: 750 !important;

        }}

        /* =====================================
           CHAT INTERFACE
        ===================================== */

        [data-testid="stChatMessage"] {{

            background: {panel};

            border: 1px solid {border};

            border-radius: 13px;

            padding: 1rem;

            margin-bottom: 0.75rem;

        }}

        [data-testid="stChatInput"] {{

            background: {panel};

            border: 1px solid {border};

            border-radius: 12px;

        }}

        /* =====================================
           ALERTS
        ===================================== */

        [data-testid="stAlert"],
        [data-testid="stAlert"] > div,
        [data-testid="stAlertContent"] {{

            background: {panel_alt} !important;

            color: {text} !important;

            border-color: {border} !important;

            border-radius: 11px !important;

        }}

        [data-testid="stAlert"] * {{

            color: {text} !important;

        }}

        /* =====================================
           EXPANDERS
        ===================================== */

        [data-testid="stExpander"] {{

            background: {panel};

            border: 1px solid {border};

            border-radius: 12px;

        }}

        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary span {{

            color: {text} !important;

        }}

        /* =====================================
           TABLES
        ===================================== */

        [data-testid="stTable"],
        [data-testid="stDataFrame"] {{

            border: 1px solid {border};

            border-radius: 10px;

        }}

        /* =====================================
           CAPTIONS AND DIVIDERS
        ===================================== */

        .stCaption,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p {{

            color: {muted} !important;

        }}

        hr {{

            border-color: {border} !important;

        }}

        /* =====================================
           LINKS
        ===================================== */

        .stApp a {{

            color: {accent} !important;

            text-decoration: none;

        }}

        .stApp a:hover {{

            color: {accent_hover} !important;

            text-decoration: underline;

        }}

        /* =====================================
           SCROLLBAR
        ===================================== */

        ::-webkit-scrollbar {{

            width: 7px;
            height: 7px;

        }}

        ::-webkit-scrollbar-track {{

            background: {bg};

        }}

        ::-webkit-scrollbar-thumb {{

            background: {border};

            border-radius: 10px;

        }}

        ::-webkit-scrollbar-thumb:hover {{

            background: {accent};

        }}

        /* =====================================
           RESPONSIVE DESIGN
        ===================================== */

        @media (max-width: 900px) {{

            .main .block-container {{

                padding: 1.2rem 1rem 2rem !important;

            }}

            .main-title,
            .rm-title {{

                font-size: 1.8rem;

            }}

        }}

        </style>
        """,
        unsafe_allow_html=True
    )


# =============================================
# REUSABLE PAGE HEADER
# =============================================

def page_header(
    eyebrow: str,
    title: str,
    subtitle: str
):

    st.markdown(
        f"""
        <div class="rm-eyebrow">
            {eyebrow}
        </div>

        <div class="rm-title">
            {title}
        </div>

        <div class="rm-subtitle">
            {subtitle}
        </div>
        """,
        unsafe_allow_html=True
    )


# =============================================
# AI PROVIDER PICKER
# =============================================

def provider_picker(
    key="rm_feature_provider"
):

    from app_config import (
        PROVIDER_GEMINI,
        PROVIDER_QWEN
    )

    return st.selectbox(
        "AI provider",
        [
            PROVIDER_GEMINI,
            PROVIDER_QWEN
        ],
        key=key
    )
