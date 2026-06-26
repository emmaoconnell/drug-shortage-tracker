"""
theme.py — Single source of truth for all visual design tokens.

Usage:
    import theme
    T = theme.get()           # returns the active ThemeTokens (light or dark)
    css = theme.css_block()   # returns <style> HTML for the active theme
"""

from dataclasses import dataclass
from typing import Callable
import streamlit as st


# ════════════════════════════════════════════════════════════════════════════
# Token dataclass
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ThemeTokens:
    name: str

    # Backgrounds
    bg_app: str
    bg_card: str
    bg_surface: str
    bg_sidebar: str
    bg_sidebar_end: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str
    text_sidebar: str
    text_sidebar_heading: str

    # Borders
    border: str
    border_sidebar: str

    # Accent palette (fixed — same in both themes)
    accent_blue: str = "#1A56DB"
    accent_teal: str = "#0694A2"
    accent_purple: str = "#6C2BD9"
    accent_green: str = "#057A55"
    accent_red: str = "#C81E1E"
    accent_amber: str = "#92400E"
    accent_navy: str = "#0F2B5B"

    # Chart specifics
    grid_color: str = "#E2E8F0"
    chart_bg: str = "#FFFFFF"
    chart_plot_bg: str = "#F8FAFC"


# ════════════════════════════════════════════════════════════════════════════
# Theme definitions
# ════════════════════════════════════════════════════════════════════════════

LIGHT = ThemeTokens(
    name="light",
    bg_app="#F5F7FA",
    bg_card="#FFFFFF",
    bg_surface="#EDF2F7",
    bg_sidebar="#0F2B5B",
    bg_sidebar_end="#1A3A6B",
    text_primary="#111827",
    text_secondary="#374151",
    text_muted="#6B7280",
    text_sidebar="#CBD5E1",
    text_sidebar_heading="#FFFFFF",
    border="#D1D5DB",
    border_sidebar="#1E3A8A",
    grid_color="#E5E7EB",
    chart_bg="rgba(0,0,0,0)",
    chart_plot_bg="rgba(0,0,0,0)",
)

DARK = ThemeTokens(
    name="dark",
    bg_app="#1A1B2E",
    bg_card="#2A2B3D",
    bg_surface="#252637",
    bg_sidebar="#12131F",
    bg_sidebar_end="#1A1B2E",
    text_primary="#ECEFF4",
    text_secondary="#B7C0D1",
    text_muted="#7C8FAC",
    text_sidebar="#8A95AB",
    text_sidebar_heading="#ECEFF4",
    border="#3A3D52",
    border_sidebar="#2A3A6A",
    grid_color="#343648",
    chart_bg="rgba(0,0,0,0)",
    chart_plot_bg="rgba(0,0,0,0)",
)


# ════════════════════════════════════════════════════════════════════════════
# Active theme accessor
# ════════════════════════════════════════════════════════════════════════════

def get() -> ThemeTokens:
    """Return the currently active ThemeTokens based on session state."""
    if st.session_state.get("dark_mode", False):
        return DARK
    return LIGHT


def is_dark() -> bool:
    return st.session_state.get("dark_mode", False)


# ════════════════════════════════════════════════════════════════════════════
# CSS generator
# ════════════════════════════════════════════════════════════════════════════

def css_block() -> str:
    T = get()
    dark = T.name == "dark"

    # Border token
    card_border = "#32363F" if dark else "#E2E8F0"

    # box-shadow tokens — used for KPI cards, expanders, and other HTML elements
    # (these are NOT used for Plotly chart cards — see drop-shadow tokens below)
    card_shadow = (
        "0 12px 30px rgba(0,0,0,0.45), 0 4px 12px rgba(0,0,0,0.30)"
        if dark else
        "0 10px 26px rgba(15,23,42,0.14), 0 4px 10px rgba(15,23,42,0.08)"
    )
    card_shadow_hover = (
        "0 20px 44px rgba(0,0,0,0.60), 0 8px 20px rgba(0,0,0,0.40)"
        if dark else
        "0 16px 36px rgba(15,23,42,0.20), 0 6px 14px rgba(15,23,42,0.10)"
    )

    return f"""
<style>
/* ── Google font ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', system-ui, sans-serif;
}}

/* ── App background ── */
.stApp {{
    background: {T.bg_app} !important;
}}

/* ── Main content area ── */
section[data-testid="stMain"] .block-container {{
    padding-top: 2rem !important;
    padding-bottom: 3rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    max-width: 1400px;
    overflow: visible !important;
}}

/* ── Top chrome — always dark navy regardless of theme ── */
header[data-testid="stHeader"],
[data-testid="stHeader"],
.stApp > header,
[data-testid="stAppViewContainer"] > header {{
    background: #0F172A !important;
    background-color: #0F172A !important;
    border-bottom: 1px solid #1E293B !important;
}}
[data-testid="stDecoration"] {{
    background: #0F172A !important;
    background-image: none !important;
}}
[data-testid="stToolbar"],
[data-testid="stToolbarActions"] {{
    background: #0F172A !important;
    background-color: #0F172A !important;
}}
header[data-testid="stHeader"] *,
[data-testid="stHeader"] *,
[data-testid="stToolbar"] *,
[data-testid="stToolbarActions"] * {{
    color: #F8FAFC !important;
}}
header[data-testid="stHeader"] svg,
[data-testid="stHeader"] svg,
[data-testid="stToolbar"] svg,
[data-testid="stToolbarActions"] svg {{
    fill: #F8FAFC !important;
    color: #F8FAFC !important;
    stroke: none !important;
}}
header[data-testid="stHeader"] button,
[data-testid="stHeader"] button,
[data-testid="stToolbar"] button,
[data-testid="stToolbarActions"] button {{
    background: transparent !important;
    border-color: rgba(248,250,252,0.3) !important;
}}

/* ════════════════════════════════════
   SIDEBAR
════════════════════════════════════ */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {T.bg_sidebar} 0%, {T.bg_sidebar_end} 100%) !important;
    border-right: 1px solid {T.border_sidebar};
}}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span {{
    color: {"#9AA5BB" if dark else T.text_sidebar} !important;
}}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{
    color: {T.text_sidebar_heading} !important;
}}
[data-testid="stSidebar"] hr {{ border-color: {T.border_sidebar} !important; }}

/* ── Static "Navigation" heading ── */
[data-testid="stSidebar"] p.nav-heading {{
    font-size: 0.70rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.10em !important;
    color: #64748B !important;
    margin: 0 0 8px 4px !important;
    padding: 0 !important;
    pointer-events: none !important;
    user-select: none !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}}

/* ── Pill-style sidebar navigation ── */

/* Options wrapper: stack pills vertically */
[data-testid="stSidebar"] .stRadio > div {{
    display: flex !important;
    flex-direction: column !important;
    gap: 4px !important;
}}

/* Hide radio circles and native input entirely */
[data-testid="stSidebar"] .stRadio input[type="radio"] {{
    display: none !important;
}}
[data-testid="stSidebar"] .stRadio > div label > div:first-child {{
    display: none !important;
}}

/* Each option label becomes a pill button — inactive */
[data-testid="stSidebar"] .stRadio > div label {{
    display: flex !important;
    align-items: center !important;
    width: 100% !important;
    padding: 10px 16px !important;
    border-radius: 10px !important;
    cursor: pointer !important;
    transition: background 0.18s ease, box-shadow 0.18s ease, color 0.18s ease !important;
    background: transparent !important;
    font-size: 0.97rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.01em !important;
    line-height: 1.3 !important;
    box-shadow: none !important;
    border: none !important;
    margin: 0 !important;
    user-select: none !important;
}}

/* ── Nav text color — target the markdown container and every element inside it.
   Uses 3 data-testid attributes for specificity (0,3,1) to beat emotion classes. ── */

[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stMarkdownContainer"] span,
[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stMarkdownContainer"] div,
[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stMarkdownContainer"] * {{
    color: {"#AEB8CC" if dark else "#D5DBE8"} !important;
    pointer-events: none !important;
}}

/* Hover */
[data-testid="stSidebar"] .stRadio > div label:hover {{
    background: rgba(255,255,255,0.10) !important;
    box-shadow: 0 0 0 1px rgba(99,179,237,0.25), 0 2px 8px rgba(0,0,0,0.25) !important;
}}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover [data-testid="stMarkdownContainer"] span,
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover [data-testid="stMarkdownContainer"] div,
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover [data-testid="stMarkdownContainer"] * {{
    color: #FFFFFF !important;
}}

/* Active / selected pill */
[data-testid="stSidebar"] .stRadio > div label:has(input:checked) {{
    background: linear-gradient(135deg, #1D4ED8 0%, #2563EB 60%, #3B82F6 100%) !important;
    font-weight: 600 !important;
    box-shadow: 0 0 0 1px rgba(59,130,246,0.50),
                0 0 12px rgba(59,130,246,0.30),
                0 2px 8px rgba(0,0,0,0.30) !important;
}}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) [data-testid="stMarkdownContainer"] span,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) [data-testid="stMarkdownContainer"] div,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) [data-testid="stMarkdownContainer"] * {{
    color: #FFFFFF !important;
}}

/* ── Sidebar utility buttons (theme toggle, Fetch, Load Cached) ── */
[data-testid="stSidebar"] .stButton button {{
    background: rgba(255,255,255,0.10) !important;
    border: 1px solid rgba(255,255,255,0.20) !important;
    color: white !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    outline: none !important;
    box-shadow: none !important;
    transition: background 0.2s !important;
}}
[data-testid="stSidebar"] .stButton button:hover {{
    background: rgba(255,255,255,0.18) !important;
    border-color: rgba(255,255,255,0.30) !important;
    box-shadow: none !important;
}}

/* ════════════════════════════════════
   MAIN CONTENT — text defaults
════════════════════════════════════ */
section[data-testid="stMain"] p {{
    color: {T.text_primary};
}}
section[data-testid="stMain"] li {{
    color: {T.text_primary};
}}
.rx-header h1,
.rx-header h2,
.rx-header h3 {{
    color: #FFFFFF !important;
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0;
}}
.rx-header p {{ color: #BFDBFE !important; font-size: 0.85rem; margin: 4px 0 0; }}
section[data-testid="stMain"] code {{
    background: {T.bg_surface};
    color: {T.text_primary};
    border: 1px solid {T.border};
    border-radius: 4px;
    padding: 1px 5px;
}}

/* ════════════════════════════════════
   CHART CARDS
   ─────────────────────────────────────
   Streamlit injects several wrapper divs between .block-container and the
   Plotly SVG. Each layer can independently carry overflow:hidden or a
   fixed height that triggers an internal scrollbar. The rules below force
   overflow:visible and remove max-height on every known wrapper so that:
     1. The card shadow is never clipped.
     2. No internal scrollbar appears beside or inside a chart card.
     3. Only the browser window itself scrolls.
════════════════════════════════════ */

/* Ensure no layout container clips the card shadow or creates internal scroll */
[data-testid="stVerticalBlock"],
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stHorizontalBlock"],
[data-testid="stColumn"],
[data-testid="element-container"],
[data-testid="stElementContainer"],
[data-testid="stBlock"],
[data-testid="stMainBlockContainer"] {{
    overflow: visible !important;
    max-height: none !important;
}}

/* Kill any auto/scroll overflow on direct children of the chart card —
   Streamlit injects height-constrained divs here that cause internal scrollbars */
[data-testid="stPlotlyChart"] > div,
[data-testid="stPlotlyChart"] > div > div,
[data-testid="stPlotlyChart"] iframe {{
    overflow: visible !important;
    max-height: none !important;
    height: auto !important;
}}

/* Side-by-side columns: stretch cards to equal height */
[data-testid="stHorizontalBlock"] {{
    align-items: stretch;
}}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    display: flex;
    flex-direction: column;
}}

/* Chart card */
[data-testid="stPlotlyChart"] {{
    background:    {T.bg_card} !important;
    border-radius: 20px !important;
    border:        1px solid {card_border} !important;
    margin:        16px 0 32px !important;
    padding:       16px !important;
    overflow:      visible !important;
    box-shadow:    {card_shadow} !important;
    transition:    box-shadow 0.2s ease, transform 0.2s ease !important;
}}
[data-testid="stPlotlyChart"]:hover {{
    box-shadow: {card_shadow_hover} !important;
    transform:  translateY(-2px) !important;
}}

/* Plotly internals — transparent so card background shows through */
[data-testid="stPlotlyChart"] .js-plotly-plot,
[data-testid="stPlotlyChart"] .plot-container,
[data-testid="stPlotlyChart"] .svg-container,
[data-testid="stPlotlyChart"] .main-svg {{
    background:  transparent !important;
    box-shadow:  none !important;
    border:      none !important;
    overflow:    visible !important;
    max-height:  none !important;
}}

/* .dashboard-card — matching style for any inline HTML wrappers */
.dashboard-card {{
    background:    {T.bg_card};
    border-radius: 20px;
    border:        1px solid {card_border};
    padding:       28px 32px;
    margin:        16px 0 32px;
    overflow:      visible;
    box-shadow:    {card_shadow};
    transition:    box-shadow 0.2s ease, transform 0.2s ease;
}}
.dashboard-card:hover {{
    box-shadow: {card_shadow_hover};
    transform:  translateY(-2px);
}}
.dashboard-card h3 {{
    font-size:   1rem;
    font-weight: 700;
    color:       {T.text_primary};
    margin:      0 0 16px;
}}
.chart-title {{
    font-size:   1rem;
    font-weight: 700;
    color:       {T.text_primary};
    margin:      0 0 16px;
}}

/* ════════════════════════════════════
   FORM WIDGETS — inputs, selects, sliders
════════════════════════════════════ */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {{
    background: {T.bg_card} !important;
    color: {T.text_primary} !important;
    border: 1px solid {T.border} !important;
    border-radius: 10px !important;
}}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {{
    border-color: #1A56DB !important;
    box-shadow: 0 0 0 3px rgba(26,86,219,0.15) !important;
}}
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stTextArea"] label,
[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label,
[data-testid="stSlider"] label,
[data-testid="stCheckbox"] label,
[data-testid="stRadio"] label {{
    color: {T.text_secondary} !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}}

/* Selectbox */
[data-testid="stSelectbox"] > div > div,
[data-baseweb="select"] > div {{
    background: {T.bg_card} !important;
    border: 1px solid {T.border} !important;
    border-radius: 10px !important;
}}
[data-baseweb="select"] span,
[data-baseweb="select"] div {{
    color: {T.text_primary} !important;
    background: transparent !important;
}}
[data-baseweb="popover"],
[data-baseweb="menu"],
ul[data-baseweb="menu"] {{
    background: {T.bg_card} !important;
    border: 1px solid {T.border} !important;
    border-radius: 10px !important;
    box-shadow: {card_shadow_hover} !important;
}}
[data-baseweb="menu"] li,
[data-baseweb="option"] {{
    background: {T.bg_card} !important;
    color: {T.text_primary} !important;
}}
[data-baseweb="menu"] li:hover,
[data-baseweb="option"]:hover {{
    background: {T.bg_surface} !important;
}}

/* Multiselect */
[data-testid="stMultiSelect"] > div > div {{
    background: {T.bg_card} !important;
    border: 1px solid {T.border} !important;
    border-radius: 10px !important;
}}
[data-testid="stMultiSelect"] span {{
    color: {T.text_primary} !important;
}}
[data-baseweb="tag"] {{
    background: {T.bg_surface} !important;
    color: {T.text_primary} !important;
    border: 1px solid {T.border} !important;
    border-radius: 6px !important;
}}

/* Slider — minimal override: only recolour the track and thumb,
   leave Streamlit's layout/sizing untouched so the value bubble
   stays pinned above the thumb and doesn't float. */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {{
    background: #1A56DB !important;
    border-color: #1A56DB !important;
}}
/* Unfilled track segment */
[data-testid="stSlider"] [data-baseweb="slider"] > div:first-child > div:first-child {{
    background: {T.border} !important;
}}
/* Filled track segment */
[data-testid="stSlider"] [data-baseweb="slider"] > div:first-child > div:nth-child(2) {{
    background: #1A56DB !important;
}}

/* Checkboxes and radio buttons */
[data-testid="stCheckbox"] span,
[data-testid="stRadio"] span {{
    color: {T.text_primary} !important;
}}

/* ════════════════════════════════════
   BUTTONS (main area)
════════════════════════════════════ */
section[data-testid="stMain"] .stButton button {{
    background: {"#3A3D52" if dark else "#3B82F6"} !important;
    color: #FFFFFF !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: background 0.15s;
}}
section[data-testid="stMain"] .stButton button:hover:not(:disabled) {{
    background: {"#4A4D62" if dark else "#2563EB"} !important;
    border: none !important;
    box-shadow: none !important;
}}
section[data-testid="stMain"] .stButton button:active:not(:disabled) {{
    background: {"#5A5D72" if dark else "#1D4ED8"} !important;
}}
section[data-testid="stMain"] .stButton button[kind="primary"] {{
    background: {"#1A56DB" if dark else "#3B82F6"} !important;
    color: #FFFFFF !important;
    border: none !important;
}}

/* ════════════════════════════════════
   EXPANDERS
════════════════════════════════════ */
[data-testid="stExpander"] {{
    background: {T.bg_card} !important;
    border: 1px solid {card_border} !important;
    border-radius: 18px !important;
    box-shadow: {card_shadow} !important;
    transition: box-shadow 0.2s ease, transform 0.2s ease !important;
    margin-bottom: 20px !important;
}}
[data-testid="stExpander"]:hover {{
    box-shadow: {card_shadow_hover} !important;
    transform: translateY(-1px) !important;
}}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary p,
.streamlit-expanderHeader,
.streamlit-expanderHeader span {{
    background: {T.bg_card} !important;
    color: {T.text_primary} !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    border-radius: 18px !important;
}}

/* ════════════════════════════════════
   INFO / WARNING / SUCCESS banners
════════════════════════════════════ */
[data-testid="stAlert"] {{
    background: {T.bg_card} !important;
    border: 1px solid {T.border} !important;
    border-radius: 12px !important;
    color: {T.text_primary} !important;
}}
[data-testid="stAlert"] p {{
    color: {T.text_primary} !important;
}}

/* ════════════════════════════════════
   TABS
════════════════════════════════════ */
[data-testid="stTabs"] [role="tab"] {{
    color: {T.text_secondary} !important;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
    color: #1A56DB !important;
    border-bottom: 2px solid #1A56DB !important;
}}

/* ════════════════════════════════════
   HERO HEADER
════════════════════════════════════ */
.rx-header {{
    background: linear-gradient(135deg, #0F2B5B 0%, #1A56DB 100%);
    border-radius: 18px;
    padding: 22px 32px;
    margin-top: 12px;
    margin-bottom: 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 8px 32px rgba(15,43,91,0.22);
}}
.rx-header-badge {{
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.30);
    color: #FFFFFF !important;
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 0.78rem;
    font-weight: 600;
    white-space: nowrap;
}}

/* ════════════════════════════════════
   KPI ROW + CARDS
   CSS grid: 6 across on desktop, responsive breakpoints below.
   Rendered as a single markdown block — Streamlit's column-stacking
   rule never touches it.
════════════════════════════════════ */
.kpi-row {{
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 18px;
    width: 100%;
    margin-bottom: 8px;
}}
.kpi-card {{
    min-width: 0;
    width: 100%;
    background: {T.bg_card};
    border-radius: 18px;
    padding: 18px 20px;
    border: 1px solid {card_border};
    box-shadow: {card_shadow};
    position: relative;
    overflow: hidden;
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}}
.kpi-card:hover {{
    box-shadow: {card_shadow_hover};
    transform: translateY(-3px);
}}
.kpi-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--accent, #1A56DB);
    border-radius: 18px 18px 0 0;
}}
@media (max-width: 1100px) {{
    .kpi-row {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
}}
@media (max-width: 700px) {{
    .kpi-row {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
}}
@media (max-width: 420px) {{
    .kpi-row {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
    }}
    .kpi-card {{
        padding: 12px 14px;
        border-radius: 14px;
    }}
    .kpi-card .kpi-value {{
        font-size: 1.35rem !important;
    }}
    .kpi-card .kpi-label {{
        font-size: 0.70rem !important;
    }}
}}
/* ── Forecast "Model Statistics" — auto-fit grid, up to 6 cards per row ── */
.model-stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 18px;
    margin-top: 4px;
    margin-bottom: 8px;
    align-items: stretch;
}}
@media (max-width: 900px) {{
    .model-stats-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
}}
@media (max-width: 600px) {{
    .model-stats-grid {{
        grid-template-columns: 1fr;
    }}
}}

/* ── Cause Analysis "Other at a Glance" — 4-col grid matching kpi-row ── */
.other-kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 18px;
    width: 100%;
    margin-bottom: 8px;
}}
@media (max-width: 1100px) {{
    .other-kpi-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
}}
@media (max-width: 700px) {{
    .other-kpi-grid {{
        grid-template-columns: 1fr;
    }}
}}

.kpi-label {{
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: {T.text_muted};
    margin-bottom: 8px;
}}
.kpi-value {{
    font-size: 2rem;
    font-weight: 700;
    color: {T.text_primary};
    line-height: 1;
}}
.kpi-sub {{
    font-size: 0.75rem;
    color: {T.text_muted};
    margin-top: 6px;
}}
.kpi-icon {{
    position: absolute;
    top: 18px; right: 18px;
    font-size: 1.6rem;
    opacity: 0.10;
}}

/* ════════════════════════════════════
   SECTION HEADINGS
════════════════════════════════════ */
.section-title {{
    font-size: 1rem;
    font-weight: 700;
    color: {T.text_primary} !important;
    margin: 36px 0 16px;
    padding-bottom: 10px;
    border-bottom: 2px solid {T.border};
    display: flex;
    align-items: center;
    gap: 8px;
}}

/* ════════════════════════════════════
   CHART WRAPPER CARD (.chart-card used in custom HTML)
════════════════════════════════════ */
.chart-card {{
    background: {T.bg_card};
    border-radius: 18px;
    padding: 24px;
    border: 1px solid {card_border};
    box-shadow: {card_shadow};
    margin-bottom: 24px;
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}}
.chart-card:hover {{
    box-shadow: {card_shadow_hover};
    transform: translateY(-2px);
}}

/* ════════════════════════════════════
   ALERT BADGES & CARDS
════════════════════════════════════ */
.badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}}
.badge-new      {{ background: #FEE2E2; color: #991B1B; }}
.badge-resolved {{ background: #D1FAE5; color: #065F46; }}
.badge-changed  {{ background: #FEF3C7; color: #92400E; }}

.alert-card {{
    background: {T.bg_card};
    border-radius: 12px;
    padding: 14px 18px;
    border: 1px solid {card_border};
    margin-bottom: 12px;
    border-left: 4px solid var(--al-color, #94A3B8);
    box-shadow: {card_shadow};
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}}
.alert-card:hover {{
    box-shadow: {card_shadow_hover};
    transform: translateY(-1px);
}}
.alert-card h4 {{ margin: 4px 0 0; font-size: 0.9rem; color: {T.text_primary} !important; }}
.alert-card p  {{ margin: 3px 0 0; font-size: 0.8rem; color: {T.text_secondary} !important; }}

/* ════════════════════════════════════
   RISK BADGES
════════════════════════════════════ */
.risk-high   {{ background:#FEE2E2; color:#991B1B; padding:3px 10px; border-radius:6px; font-size:0.75rem; font-weight:600; }}
.risk-medium {{ background:#FEF3C7; color:#92400E; padding:3px 10px; border-radius:6px; font-size:0.75rem; font-weight:600; }}
.risk-low    {{ background:#D1FAE5; color:#065F46; padding:3px 10px; border-radius:6px; font-size:0.75rem; font-weight:600; }}

/* ════════════════════════════════════
   ST.METRIC OVERRIDE
════════════════════════════════════ */
[data-testid="metric-container"] {{
    background: {T.bg_card} !important;
    border-radius: 18px !important;
    border: 1px solid {card_border} !important;
    padding: 24px !important;
    box-shadow: {card_shadow} !important;
    transition: box-shadow 0.2s ease, transform 0.2s ease !important;
}}
[data-testid="metric-container"]:hover {{
    box-shadow: {card_shadow_hover} !important;
    transform: translateY(-2px) !important;
}}
[data-testid="metric-container"] [data-testid="stMetricValue"] {{
    font-size: 1.8rem !important;
    font-weight: 700 !important;
    color: {T.text_primary} !important;
}}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {{
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
    color: {T.text_muted} !important;
}}

/* ════════════════════════════════════
   DOWNLOAD / ACTION BUTTONS
   st.download_button renders under [data-testid="stDownloadButton"].
   In dark mode the default Streamlit styling produces light-on-light text.
════════════════════════════════════ */
[data-testid="stDownloadButton"] button {{
    background: {"#2563EB" if dark else "#3B82F6"} !important;
    color: #FFFFFF !important;
    border: 1px solid {"#3B82F6" if dark else "#1A56DB"} !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: background 0.15s, box-shadow 0.15s !important;
}}
[data-testid="stDownloadButton"] button:hover:not(:disabled) {{
    background: {"#1D4ED8" if dark else "#1741B0"} !important;
    box-shadow: 0 4px 14px rgba(37,99,235,0.35) !important;
}}
[data-testid="stDownloadButton"] button:disabled {{
    background: {"#40445A" if dark else "#9CA3AF"} !important;
    color: {"#AEB7C6" if dark else "#E5E7EB"} !important;
    cursor: not-allowed !important;
}}

/* ════════════════════════════════════
   FORMS
════════════════════════════════════ */
[data-testid="stForm"] {{
    background: {T.bg_card} !important;
    border-radius: 18px !important;
    padding: 24px !important;
    border: 1px solid {card_border} !important;
    box-shadow: {card_shadow} !important;
}}

/* ════════════════════════════════════
   MISC
════════════════════════════════════ */
hr {{ border: none; border-top: 1px solid {T.border}; margin: 32px 0; }}

/* Caption / helper text */
[data-testid="stCaptionContainer"] p {{
    color: {T.text_muted} !important;
}}

/* ════════════════════════════════════
   INPUT PLACEHOLDER COLOR
════════════════════════════════════ */
[data-testid="stTextInput"] input::placeholder,
[data-testid="stNumberInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {{
    color: {"#AEB7C6" if dark else "#9CA3AF"} !important;
    opacity: 1 !important;
}}

/* Dark-mode input background — slightly deeper than card for contrast */
{"" if not dark else """
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
    background: #2F3145 !important;
    caret-color: #ECEFF4 !important;
}
"""}

/* ════════════════════════════════════
   FORM SUBMIT BUTTON
   st.form_submit_button renders under a different testid than st.button,
   so it needs its own selector.
════════════════════════════════════ */
[data-testid="stFormSubmitButton"] button {{
    background: {"#1A56DB" if dark else "#3B82F6"} !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: background 0.15s, box-shadow 0.15s !important;
}}
[data-testid="stFormSubmitButton"] button:hover:not(:disabled) {{
    background: {"#2F6BFF" if dark else "#2563EB"} !important;
    box-shadow: 0 4px 14px rgba(59,130,246,0.35) !important;
}}
[data-testid="stFormSubmitButton"] button:disabled {{
    background: {"#40445A" if dark else "#9CA3AF"} !important;
    color: {"#8D95A8" if dark else "#E5E7EB"} !important;
    cursor: not-allowed !important;
}}

/* ════════════════════════════════════
   ALERT BANNERS — type-specific dark-mode colors
   Streamlit renders st.success / warning / error / info as
   [data-testid="stAlert"] with a data-baseweb="notification" child.
   We can select the icon container to identify the type, but the most
   reliable cross-version approach is to override ALL alerts with a dark
   neutral base and then add type accents via the notification kind attr.
════════════════════════════════════ */
[data-testid="stAlert"] {{
    background: {"#23253A" if dark else T.bg_card} !important;
    border: 1px solid {T.border} !important;
    border-radius: 12px !important;
    color: {T.text_primary} !important;
}}
[data-testid="stAlert"] p,
[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {{
    color: {T.text_primary} !important;
}}

/* Success — green tint */
{"" if not dark else """
[data-testid="stAlert"][data-baseweb="notification"][kind="positive"],
[data-baseweb="notification"][kind="positive"] {
    background: rgba(46,160,67,0.18) !important;
    border-color: rgba(46,160,67,0.45) !important;
}
[data-baseweb="notification"][kind="positive"] p,
[data-baseweb="notification"][kind="positive"] [data-testid="stMarkdownContainer"] p {
    color: #D6F5DE !important;
}
/* Warning — amber tint */
[data-baseweb="notification"][kind="warning"] {
    background: rgba(180,100,10,0.22) !important;
    border-color: rgba(217,119,6,0.50) !important;
}
[data-baseweb="notification"][kind="warning"] p,
[data-baseweb="notification"][kind="warning"] [data-testid="stMarkdownContainer"] p {
    color: #FDE68A !important;
}
/* Error — red tint */
[data-baseweb="notification"][kind="negative"] {
    background: rgba(185,28,28,0.20) !important;
    border-color: rgba(239,68,68,0.45) !important;
}
[data-baseweb="notification"][kind="negative"] p,
[data-baseweb="notification"][kind="negative"] [data-testid="stMarkdownContainer"] p {
    color: #FCA5A5 !important;
}
/* Info — blue tint */
[data-baseweb="notification"][kind="info"] {
    background: rgba(26,86,219,0.18) !important;
    border-color: rgba(96,165,250,0.40) !important;
}
[data-baseweb="notification"][kind="info"] p,
[data-baseweb="notification"][kind="info"] [data-testid="stMarkdownContainer"] p {
    color: #BFDBFE !important;
}
"""}

/* ════════════════════════════════════
   WATCHLIST ROWS
════════════════════════════════════ */
.wl-row {{
    background: {"#2B2D42" if dark else T.bg_card};
    border-radius: 14px;
    padding: 14px 20px;
    border: 1px solid {card_border};
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: {card_shadow};
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}}
.wl-row:hover {{
    box-shadow: {card_shadow_hover};
    transform: translateY(-1px);
}}
/* Ensure watchlist text is always readable in dark mode */
{"" if not dark else """
.wl-row * { color: #ECEFF4 !important; }
"""}

/* Divider between watchlist rows */
[data-testid="stDivider"] hr {{
    border-top-color: {T.border} !important;
    opacity: 0.7 !important;
}}

/* ════════════════════════════════════
   VERTICAL SPACING — gap between stacked elements
════════════════════════════════════ */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stVerticalBlock"] > div {{
    margin-bottom: 8px;
}}

/* ════════════════════════════════════
   RESPONSIVE COLUMNS
════════════════════════════════════ */
@media (max-width: 900px) {{
    [data-testid="stHorizontalBlock"] {{
        flex-wrap: wrap !important;
        gap: 1.5rem 0 !important;
    }}
    [data-testid="stColumn"] {{
        width: 100% !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }}
}}
@media (max-width: 600px) {{
    [data-testid="stHorizontalBlock"] {{
        flex-wrap: wrap !important;
    }}
    [data-testid="stColumn"] {{
        width: 100% !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }}
    section[data-testid="stMain"] .block-container {{
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }}
}}

/* ════════════════════════════════════
   SCROLL-REVEAL ENTRANCE ANIMATIONS
   JS adds .scroll-reveal to cards, then .visible when they enter viewport.
════════════════════════════════════ */

.scroll-reveal {{
    opacity: 0;
    transform: translateY(18px);
    transition: opacity 0.6s ease-out, transform 0.6s ease-out;
}}
.scroll-reveal.visible {{
    opacity: 1;
    transform: translateY(0);
}}

@media (prefers-reduced-motion: reduce) {{
    .scroll-reveal,
    .scroll-reveal.visible {{
        opacity: 1 !important;
        transform: none !important;
        transition: none !important;
    }}
}}

</style>
"""


# ════════════════════════════════════════════════════════════════════════════
# Scroll-reveal JS (injected via st.components.v1.html)
# ════════════════════════════════════════════════════════════════════════════

def scroll_reveal_js() -> str:
    """
    Returns an HTML string (0-height iframe content) that wires up an
    IntersectionObserver on the parent Streamlit document.

    Cards matching SELECTORS get .scroll-reveal added by JS; the observer
    adds .visible when each card enters the viewport (once only).
    A MutationObserver re-scans after every Streamlit rerender so cards
    added by navigation or data refresh are picked up automatically.
    A guard flag (window.__rxRevealReady) prevents duplicate observers
    across multiple st.components.v1.html calls in the same session.
    """
    return """
<script>
(function () {
    var win = window.parent;
    var doc = win.document;

    // One-time setup per browser session — survive Streamlit reruns
    if (win.__rxRevealReady) return;
    win.__rxRevealReady = true;

    var SELECTORS = [
        '[data-testid="stPlotlyChart"]',
        '[data-testid="metric-container"]',
        '.dashboard-card',
        '.chart-card',
    ].join(', ');

    var io = new win.IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                io.unobserve(entry.target);
            }
        });
    }, { threshold: 0.08, rootMargin: '0px 0px -24px 0px' });

    function attachCards() {
        doc.querySelectorAll(SELECTORS).forEach(function (el) {
            if (!el.classList.contains('scroll-reveal')) {
                el.classList.add('scroll-reveal');
                io.observe(el);
            }
        });
    }

    function waitForMain() {
        var main = doc.querySelector('[data-testid="stMain"]') || doc.body;
        attachCards();
        // Re-scan whenever Streamlit mutates the main content area
        var mo = new win.MutationObserver(attachCards);
        mo.observe(main, { childList: true, subtree: true });
    }

    // Give Streamlit a moment to render its first batch of cards
    if (doc.readyState === 'loading') {
        doc.addEventListener('DOMContentLoaded', function () {
            setTimeout(waitForMain, 150);
        });
    } else {
        setTimeout(waitForMain, 150);
    }
})();
</script>
"""


# ════════════════════════════════════════════════════════════════════════════
# Plotly base layout builder
# ════════════════════════════════════════════════════════════════════════════

_FONT_FAMILY = "Inter, system-ui, -apple-system, sans-serif"


def plotly_base(
    title: str = "",
    height: int = 400,
    margin: dict | None = None,
    showlegend: bool = False,
) -> dict:
    """
    Return a Plotly layout dict using the active theme's colors.
    Merge with chart-specific overrides via:
        fig.update_layout(**theme.plotly_base(...), xaxis=..., yaxis=...)
    """
    T = get()
    dark = T.name == "dark"
    m = margin or dict(t=64, b=90, l=60, r=30)
    return dict(
        paper_bgcolor=T.chart_bg,
        plot_bgcolor=T.chart_plot_bg,
        font=dict(family=_FONT_FAMILY, size=12, color=T.text_primary),
        title=dict(
            text=title,
            font=dict(family=_FONT_FAMILY, size=18, color=T.text_primary),
            x=0,
            pad=dict(l=4, b=10),
        ),
        xaxis=dict(
            title_font=dict(family=_FONT_FAMILY, size=13, color=T.text_primary),
            tickfont=dict(family=_FONT_FAMILY, size=11, color=T.text_secondary),
            gridcolor=T.grid_color,
            linecolor=T.border,
            showgrid=True,
            zeroline=False,
            fixedrange=True,
        ),
        yaxis=dict(
            title_font=dict(family=_FONT_FAMILY, size=13, color=T.text_primary),
            tickfont=dict(family=_FONT_FAMILY, size=11, color=T.text_secondary),
            gridcolor=T.grid_color,
            linecolor=T.border,
            showgrid=True,
            zeroline=False,
            fixedrange=True,
        ),
        legend=dict(
            font=dict(family=_FONT_FAMILY, size=11, color=T.text_primary),
            bgcolor=T.chart_bg,
            bordercolor=T.border,
            borderwidth=1,
        ),
        hoverlabel=dict(
            bgcolor="#1F2937" if dark else "#FFFFFF",
            bordercolor="#374151" if dark else "#D1D5DB",
            font=dict(
                family=_FONT_FAMILY,
                size=13,
                color="#F9FAFB" if dark else "#111827",
            ),
            namelength=-1,
        ),
        dragmode=False,
        margin=m,
        height=height,
        showlegend=showlegend,
    )
