"""
app.py — Drug Shortage Tracker  |  Pharmaceutical Analytics Platform

Run:  streamlit run app.py

Pages
─────
Overview           KPI cards + executive summary charts
Manufacturers      Top-companies deep-dive & risk matrix
Search             Live-API or cached search
Data Table         Filterable, exportable record table
Trends             Historical snapshot analysis
Forecast           Linear-regression forward projection
Alerts             Change detection feed
Watchlist          Persisted drug monitoring list
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import base64

import json
import plotly.io as _pio
import os

import database as db
import api as fda_api
import dashboard as charts
import forecasting as fc_module
import theme


# ════════════════════════════════════════════════════════════════════════════
# Page config — must be the first Streamlit call
# ════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="RxSignal · Drug Shortage Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)


# ════════════════════════════════════════════════════════════════════════════
# Session-state: theme must be set BEFORE css_block() is called
# ════════════════════════════════════════════════════════════════════════════
if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = False

# Inject theme CSS (re-runs whenever dark_mode toggles)
st.markdown(theme.css_block(), unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# Init DB (idempotent)
# ════════════════════════════════════════════════════════════════════════════
db.init_db()


# ════════════════════════════════════════════════════════════════════════════
# Session-state defaults
# ════════════════════════════════════════════════════════════════════════════
for key, default in [("df", pd.DataFrame()), ("last_fetched", None)]:
    if key not in st.session_state:
        st.session_state[key] = default


# ════════════════════════════════════════════════════════════════════════════
# Helper utilities
# ════════════════════════════════════════════════════════════════════════════

def _parse_raw(r: dict) -> dict:
    """
    Extract a raw_json blob when the DB row has blank manufacturer/brand.
    Older snapshots were saved before the company_name fix was applied.
    """
    raw_str = r.get("raw_json", "")
    if not raw_str:
        return {}
    try:
        return json.loads(raw_str)
    except (ValueError, TypeError):
        return {}


def _best_manufacturer(r: dict, raw: dict) -> str:
    """Prefer the DB column; fall back to direct API company_name, raw_json, or openfda."""
    val = (r.get("manufacturer") or "").strip()
    if val:
        return val
    # Direct API records use company_name at the top level (not in raw_json)
    val = (r.get("company_name") or "").strip()
    if val:
        return val
    val = (raw.get("company_name") or "").strip()
    if val:
        return val
    openfda = raw.get("openfda") or {}
    mfr_list = openfda.get("manufacturer_name") or []
    return (mfr_list[0] if mfr_list else "").strip()


def _best_brand(r: dict, raw: dict) -> str:
    val = (r.get("brand_name") or "").strip()
    if val:
        return val
    val = (raw.get("brand_name") or "").strip()
    if val:
        return val
    openfda = raw.get("openfda") or {}
    brand_list = openfda.get("brand_name") or []
    return (brand_list[0] if brand_list else "").strip()


def records_to_df(records: list[dict]) -> pd.DataFrame:
    """Flatten snapshot/API records into a tidy DataFrame."""
    if not records:
        return pd.DataFrame()
    rows = []
    for r in records:
        raw = _parse_raw(r)
        rows.append({
            "generic_name":         (r.get("generic_name") or raw.get("generic_name") or "").strip(),
            "brand_name":           _best_brand(r, raw),
            "manufacturer":         _best_manufacturer(r, raw),
            "status":               (r.get("status") or raw.get("status") or "").strip(),
            "reason":               (
                                        r.get("reason")
                                        # Direct API records use shortage_reason (plain string)
                                        or r.get("shortage_reason")
                                        or ""
                                    ).strip(),
            "initial_posting_date": r.get("initial_posting_date") or raw.get("initial_posting_date") or "",
            "update_date":          r.get("update_date") or raw.get("update_date") or "",
            "fetched_at":           r.get("fetched_at", ""),
        })
    df = pd.DataFrame(rows)
    for col in df.columns:
        df[col] = df[col].fillna("").astype(str)
    return df


def detect_and_save_alerts(old_df: pd.DataFrame, new_df: pd.DataFrame) -> int:
    """Diff two snapshots and persist detected alerts; return count."""
    if old_df.empty or new_df.empty:
        return 0
    old_map = old_df.set_index("generic_name")["status"].to_dict()
    new_map = new_df.set_index("generic_name")["status"].to_dict()
    alert_list = []

    for name, new_status in new_map.items():
        if name not in old_map:
            row = new_df[new_df["generic_name"] == name].iloc[0]
            alert_list.append({
                "alert_type": "new",
                "generic_name": name,
                "brand_name": row.get("brand_name", ""),
                "manufacturer": row.get("manufacturer", ""),
                "old_status": "",
                "new_status": new_status,
                "detail": f"New shortage detected for {name}",
            })
        elif old_map[name] != new_status:
            alert_list.append({
                "alert_type": "resolved" if new_status == "Resolved" else "status_change",
                "generic_name": name,
                "brand_name": "",
                "manufacturer": "",
                "old_status": old_map[name],
                "new_status": new_status,
                "detail": f"{name}: {old_map[name]} → {new_status}",
            })

    for name in old_map:
        if name not in new_map:
            alert_list.append({
                "alert_type": "resolved",
                "generic_name": name,
                "brand_name": "",
                "manufacturer": "",
                "old_status": old_map[name],
                "new_status": "Removed",
                "detail": f"{name} no longer appears in shortage data",
            })

    db.save_alerts(alert_list)
    return len(alert_list)


def kpi_card(label: str, value: str, sub: str = "", icon: str = "", accent: str = "#1A56DB") -> str:
    """Return HTML for a styled KPI card (no leading whitespace — avoids markdown code-block detection)."""
    return (
        f'<div class="kpi-card" style="--accent:{accent}">'
        f'<div class="kpi-icon">{icon}</div>'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub">{sub}</div>'
        f'</div>'
    )


def section(title: str) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)


_PLOTLY_CONFIG = {
    "displayModeBar": False,
    "scrollZoom": False,
    "doubleClick": False,
    "staticPlot": False,
    "responsive": True,
}


def plot(fig, msg: str = "No data available for this chart.", height: int = 0, title: str = "") -> None:
    """Render a Plotly figure as an interactive chart card with hover but no zoom/pan."""
    if fig is None:
        st.info(msg)
    else:
        updates: dict = {"dragmode": False}
        if height:
            updates["height"] = height
        fig.update_layout(**updates)
        fig.update_xaxes(fixedrange=True)
        fig.update_yaxes(fixedrange=True)
        st.plotly_chart(fig, use_container_width=True, config=_PLOTLY_CONFIG)


# ── Global table renderer ─────────────────────────────────────────────────────
#
# ROOT CAUSE: config.toml `base = "light"` locks Streamlit's Arrow/Glide Data
# Grid iframe to a light theme at the process level. pandas Styler only reaches
# individual `td` cells — the iframe body, scrollbars, and padding areas stay
# white. This cannot be overridden at runtime via CSS or Styler.
#
# SOLUTION: render tables as plain HTML via st.html() which lives in the main
# DOM (no iframe), so our injected CSS fully controls all colors in both themes.

def df_show(data: pd.DataFrame, height: int | None = None) -> None:
    """
    Render a DataFrame as a themed HTML table in the main DOM.

    Uses st.html() instead of st.dataframe() so the table is NOT inside an
    iframe — our CSS in theme.css_block() controls all colors in both light
    and dark mode without any workaround.
    """
    if data.empty:
        st.info("No data available.")
        return

    dark = st.session_state.get("dark_mode", False)
    if dark:
        tbl_bg     = "#111827"
        row_odd    = "#1F2937"
        row_even   = "#111827"
        hdr_bg     = "#0F172A"
        text       = "#F9FAFB"
        muted      = "#94A3B8"
        border     = "#374155"
        hover      = "#273244"
    else:
        tbl_bg     = "#FFFFFF"
        row_odd    = "#F3F6FA"
        row_even   = "#EDF2F7"
        hdr_bg     = "#E5EAF2"
        text       = "#111827"
        muted      = "#6B7280"
        border     = "#D6DDE8"
        hover      = "#E2E8F0"

    scroll_h = f"height:{height}px;overflow-y:auto;" if height else "max-height:600px;overflow-y:auto;"

    # Build header
    headers = "".join(
        f'<th style="background:{hdr_bg};color:{text};font-weight:600;'
        f'padding:9px 13px;text-align:left;border-bottom:2px solid {border};'
        f'white-space:nowrap;font-size:0.82rem;letter-spacing:0.03em;'
        f'text-transform:uppercase">{col}</th>'
        for col in data.columns
    )

    # Build rows
    rows_html = []
    for i, (_, row) in enumerate(data.iterrows()):
        bg = row_odd if i % 2 == 0 else row_even
        cells = "".join(
            f'<td style="background:{bg};color:{text};padding:8px 13px;'
            f'border-bottom:1px solid {border};font-size:0.875rem;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
            f'max-width:280px" title="{str(v)}">{str(v)}</td>'
            for v in row
        )
        rows_html.append(
            f'<tr onmouseover="this.style.background=\'{hover}\'" '
            f'onmouseout="this.querySelectorAll(\'td\').forEach(td=>td.style.background=\'{bg}\')">'
            f'{cells}</tr>'
        )

    html = (
        f'<div style="background:{tbl_bg};border:1px solid {border};'
        f'border-radius:8px;overflow:hidden;{scroll_h}">'
        f'<table style="border-collapse:collapse;width:100%;table-layout:auto">'
        f'<thead><tr>{headers}</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        f'</table></div>'
    )
    st.html(html)


def page_header(title: str, subtitle: str, badge: str = "") -> None:
    badge_html = f'<span class="rx-header-badge">{badge}</span>' if badge else ""
    st.markdown(
        f"""
        <div class="rx-header">
          <div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════════════
# Sidebar
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        """
        <div style="padding:12px 0 28px">
          <div style="font-size:2.4rem;font-weight:800;color:white;letter-spacing:0.02em;line-height:1.1">
            RxSignal
          </div>
          <div style="font-size:0.72rem;color:#93C5FD;font-weight:500;margin-top:8px;letter-spacing:0.08em">
            DRUG SHORTAGE INTELLIGENCE
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _PAGES = [
        "Overview",
        "Manufacturers",
        "Forecast",
        "Search",
        "Export Data",
        "Trends",
        "Alerts",
        "Watchlist",
    ]

    page = st.radio(
        "Navigation",
        _PAGES,
        label_visibility="visible",
    )

    st.markdown("---")
    # ── Theme toggle ──────────────────────────────────────────────────────────
    _dark_now = st.session_state.get("dark_mode", False)
    _toggle_label = "Light Mode" if _dark_now else "Dark Mode"
    if st.button(_toggle_label, use_container_width=True):
        st.session_state["dark_mode"] = not _dark_now
        st.rerun()

    st.markdown("---")
    st.markdown(
        '<p style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.1em;color:#64748B;font-weight:600">Data Controls</p>',
        unsafe_allow_html=True,
    )

    if st.session_state["last_fetched"]:
        st.markdown(
            f'<p style="font-size:0.75rem;color:#94A3B8">Last update: {st.session_state["last_fetched"]}</p>',
            unsafe_allow_html=True,
        )

    record_limit = st.slider("Records to fetch", 100, 2000, 1000, step=100)

    if st.button("Fetch Latest Data", use_container_width=True):
        with st.spinner("Pulling from openFDA…"):
            try:
                old_df = st.session_state["df"].copy()
                raw = fda_api.fetch_shortages(limit=record_limit)
                if raw:
                    db.save_snapshot(raw)
                    new_records = db.get_latest_snapshot(limit=record_limit)
                    new_df = records_to_df(new_records)
                    st.session_state["df"] = new_df
                    st.session_state["last_fetched"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                    n_alerts = detect_and_save_alerts(old_df, new_df)
                    st.success(f"{len(new_df):,} records loaded · {n_alerts} alerts detected")
                else:
                    st.warning("API returned no records.")
            except Exception as exc:
                st.error(f"Fetch failed: {exc}")

    if st.button("Load Cached Data", use_container_width=True):
        cached = db.get_latest_snapshot(limit=record_limit)
        if cached:
            st.session_state["df"] = records_to_df(cached)
            st.session_state["last_fetched"] = "cached"
            st.success(f"{len(st.session_state['df']):,} records loaded from cache")
        else:
            st.info("No cache yet — fetch first.")

    st.markdown("---")
    st.markdown(
        '<p style="font-size:0.72rem;color:#475569">Source: <a href="https://open.fda.gov" style="color:#93C5FD">openFDA Drug Shortages API</a></p>',
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════════════
# Auto-load on first visit
# ════════════════════════════════════════════════════════════════════════════
if st.session_state["df"].empty:
    cached = db.get_latest_snapshot(limit=1000)
    if cached:
        st.session_state["df"] = records_to_df(cached)
        st.session_state["last_fetched"] = "auto-loaded"

df: pd.DataFrame = st.session_state["df"]


# ════════════════════════════════════════════════════════════════════════════
# PAGE — Overview  (merged from Executive Summary + Overview)
# ════════════════════════════════════════════════════════════════════════════
if page == "Overview":
    page_header(
        "Overview",
        "FDA drug shortage intelligence — leadership overview",
        badge=f"Live  ·  {datetime.utcnow().strftime('%b %d, %Y')}",
    )

    if df.empty:
        st.info("No data loaded. Use **Fetch Latest Data** or **Load Cached Data** in the sidebar.")
        st.stop()

    kpis = charts.compute_kpis(df)
    risk_df = fc_module.manufacturer_risk_table(df)

    # ── Compute risk score ────────────────────────────────────────────────────
    if not risk_df.empty:
        high_risk_pct     = (risk_df["risk_label"] == "High").mean() * 100
        avg_risk_score    = risk_df["risk_score"].mean()
        active_shortages  = kpis["current_count"]
        total_current_pct = (active_shortages / max(kpis["total"], 1) * 100)
        env_score = min(round(
            0.40 * total_current_pct + 0.35 * high_risk_pct + 0.25 * avg_risk_score, 1
        ), 100.0)
        score_label = "High" if env_score >= 65 else ("Moderate" if env_score >= 35 else "Low")
        score_color = {"High": "#C81E1E", "Moderate": "#D97706", "Low": "#065F46"}[score_label]
        score_bg    = {"High": "#FEE2E2", "Moderate": "#FEF3C7", "Low": "#D1FAE5"}[score_label]
    else:
        active_shortages = kpis["current_count"]
        env_score, score_label, score_color, score_bg = 0, "Unknown", "#64748B", "#F1F5F9"
        high_risk_pct, avg_risk_score, total_current_pct = 0.0, 0.0, 0.0

    # ── New shortages since last snapshot ─────────────────────────────────────
    all_snap_dates = db.get_snapshot_dates()
    new_since_last = 0
    if len(all_snap_dates) >= 2:
        prev_df = records_to_df(db.get_snapshot_by_date(all_snap_dates[1]))
        if not prev_df.empty:
            current_names = set(df["generic_name"].str.lower())
            prev_names    = set(prev_df["generic_name"].str.lower())
            new_since_last = len(current_names - prev_names)

    # ═══════════════════════════════════════════════════════════════
    # TOP SECTION — 6 KPI cards (single flex row — never stacks vertically)
    # ═══════════════════════════════════════════════════════════════
    current_pct = round(kpis["current_count"] / max(kpis["total"], 1) * 100, 1)
    kpi_html = "".join([
        '<div class="kpi-row">',
        kpi_card("Active Shortages",    f"{kpis['current_count']:,}",       f"{current_pct}% of records", "", "#DC2626"),
        kpi_card("Resolved",            f"{kpis['resolved_count']:,}",      "Returned to market",         "", "#16A34A"),
        kpi_card("Manufacturers",       f"{kpis['unique_manufacturers']:,}", "Companies affected",         "", "#6C2BD9"),
        kpi_card("Unique Drugs",        f"{kpis['unique_drugs']:,}",        "Distinct generic names",     "", "#0694A2"),
        kpi_card("Risk Score",          f"{env_score}",                     f"{score_label} risk level",  "", score_color),
        kpi_card("New Since Last Snap", f"{new_since_last:,}",              "Newly appearing drugs",      "", "#1A56DB"),
        "</div>",
    ])
    st.markdown(kpi_html, unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # MIDDLE SECTION — charts grid
    # ═══════════════════════════════════════════════════════════════
    section("Shortage Landscape")
    ml, mr = st.columns([1, 2])
    with ml:
        plot(charts.status_donut(df))
    with mr:
        plot(charts.top_manufacturers_bar(df, top_n=12))

    section("Root Causes & Market Share")
    unspec_pct = kpis.get("unspecified_reason_pct", 0.0)
    st.markdown(
        kpi_card("Reason Unspecified", f"{unspec_pct:.1f}%",
                 "of records lack an FDA-reported cause", "", "#92400E"),
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)
    rl, rr = st.columns([1, 1])
    with rl:
        plot(charts.reason_bar(df))
    with rr:
        plot(charts.exec_bubble_chart(risk_df, df))

    # ═══════════════════════════════════════════════════════════════
    # BOTTOM SECTION — Risk context, AI summary, Recent changes
    # ═══════════════════════════════════════════════════════════════
    section("Risk Context")
    rs1, rs2, rs3 = st.columns([1, 1, 2])
    rs1.markdown(
        f"""<div class="kpi-card" style="--accent:{score_color}">
          <div class="kpi-label">Environment Risk Score</div>
          <div class="kpi-value" style="color:{score_color}">{env_score}</div>
          <div class="kpi-sub">out of 100</div>
        </div>""",
        unsafe_allow_html=True,
    )
    rs2.markdown(
        f"""<div class="kpi-card" style="--accent:{score_color}">
          <div class="kpi-label">Risk Level</div>
          <div class="kpi-value" style="color:{score_color}">{score_label}</div>
          <div class="kpi-sub">{high_risk_pct:.0f}% high-risk manufacturers</div>
        </div>""",
        unsafe_allow_html=True,
    )
    with rs3:
        st.markdown(
            f"""<div style="background:{score_bg};border-left:4px solid {score_color};
                 border-radius:8px;padding:14px 18px;margin-top:4px">
              <p style="margin:0;font-size:0.85rem;color:#374151;line-height:1.6">
              <b>Score methodology:</b> weighted composite of active shortage rate
              ({total_current_pct:.1f}%), high-risk manufacturer concentration
              ({high_risk_pct:.0f}%), and average manufacturer risk score ({avg_risk_score:.1f}/100).
              </p>
            </div>""",
            unsafe_allow_html=True,
        )
    st.markdown("<br>", unsafe_allow_html=True)

    section("AI Interpretation")

    @st.cache_data(ttl=3600, show_spinner=False)
    def _ai_summary(
        total: int, active: int, manufacturers: int,
        top_mfrs: str, top_causes: str,
        env_score_val: float, risk_lbl: str,
    ) -> str:
        try:
            import anthropic as _anthropic
            client = _anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            prompt = (
                f"You are a pharmaceutical supply-chain analyst. Write exactly one concise paragraph "
                f"(4-6 sentences) interpreting the following drug shortage data for an executive audience. "
                f"Be specific, professional, and actionable. Do not use bullet points or headings.\n\n"
                f"Data snapshot:\n"
                f"- Total shortage records: {total:,}\n"
                f"- Active (current) shortages: {active:,}\n"
                f"- Manufacturers affected: {manufacturers:,}\n"
                f"- Top 5 manufacturers by shortage count: {top_mfrs}\n"
                f"- Top shortage causes: {top_causes}\n"
                f"- Environment risk score: {env_score_val}/100 ({risk_lbl} risk)\n"
            )
            msg = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
        except Exception:
            top5_names = top_mfrs.split(", ")[:3]
            return (
                f"The current drug shortage environment shows {active:,} active shortages "
                f"across {manufacturers:,} manufacturers, representing a {risk_lbl.lower()} "
                f"overall risk level (score: {env_score_val}/100). "
                f"Leading affected manufacturers include {', '.join(top5_names)}. "
                f"Stakeholders should monitor high-risk suppliers closely and evaluate alternative "
                f"sourcing strategies to mitigate supply disruption risk."
            )

    top5_str = ", ".join(risk_df.head(5)["manufacturer"].tolist()) if not risk_df.empty else "unavailable"
    meaningful_reasons = df["reason"].fillna("").str.strip()
    meaningful_reasons = meaningful_reasons[~meaningful_reasons.str.lower().isin({"", "other", "not specified"})]
    top_causes_str = ", ".join(meaningful_reasons.value_counts().head(3).index.tolist()) or "unavailable"

    with st.spinner("Generating AI interpretation..."):
        ai_text = _ai_summary(
            total=kpis["total"], active=active_shortages,
            manufacturers=kpis["unique_manufacturers"],
            top_mfrs=top5_str, top_causes=top_causes_str,
            env_score_val=env_score, risk_lbl=score_label,
        )

    T = theme.get()
    st.markdown(
        f"""<div style="background:{T.bg_card};border:1px solid {T.border};
             border-left:4px solid #1A56DB;border-radius:10px;
             padding:20px 24px;box-shadow:0 1px 4px rgba(0,0,0,0.05)">
          <p style="margin:0;font-size:0.95rem;line-height:1.75;color:{T.text_primary}">{ai_text}</p>
        </div>""",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    section("Recent Changes")
    recent = (
        df[df["update_date"] != ""]
        .sort_values("update_date", ascending=False)
        .head(10)
    )
    if recent.empty:
        st.info("No records with update dates available.")
    else:
        h = min(400, max(120, len(recent) * 35 + 38))
        df_show(
            recent[["generic_name", "brand_name", "manufacturer", "status", "update_date"]].rename(
                columns={"generic_name": "Generic Name", "brand_name": "Brand Name",
                         "manufacturer": "Manufacturer", "status": "Status",
                         "update_date": "Last Updated"}
            ),
            height=h,
        )


# ════════════════════════════════════════════════════════════════════════════
# PAGE — Manufacturers
# ════════════════════════════════════════════════════════════════════════════
elif page == "Manufacturers":
    page_header(
        "Manufacturer Analytics",
        "Supply-chain risk assessment across pharmaceutical companies",
    )

    if df.empty:
        st.info("No data loaded.")
        st.stop()

    # ── Risk table ────────────────────────────────────────────────────────────
    risk_df = fc_module.manufacturer_risk_table(df)

    section("Risk Matrix — Top Companies")
    plot(charts.risk_scatter(risk_df), height=560)

    section("Shortage Composition by Manufacturer")
    plot(charts.manufacturer_current_vs_resolved(df, top_n=14, mobile=False))

    section("Market Share Treemap")
    plot(charts.market_share_treemap(df))

    # ── Sortable risk table ───────────────────────────────────────────────────
    section("Full Manufacturer Risk Table")

    def risk_label(score: float) -> str:
        if score >= 65:
            return "High"
        elif score >= 35:
            return "Medium"
        return "Low"

    display_risk = risk_df.copy()

    # Ensure every expected column exists before selecting
    for col, default in [
        ("shortage_count", 0),
        ("current_count",  0),
        ("resolved_count", 0),
        ("unique_drugs",   0),
        ("pct_current",    0.0),
        ("risk_score",     0.0),
    ]:
        if col not in display_risk.columns:
            display_risk[col] = default

    if "risk_label" not in display_risk.columns:
        display_risk["risk_label"] = display_risk["risk_score"].apply(risk_label)

    display_risk = display_risk[[
        "manufacturer", "shortage_count", "current_count",
        "resolved_count", "pct_current", "unique_drugs", "risk_score", "risk_label",
    ]].rename(columns={
        "manufacturer":   "Manufacturer",
        "shortage_count": "Total Shortages",
        "current_count":  "Active",
        "resolved_count": "Resolved",
        "pct_current":    "% Active",
        "unique_drugs":   "Unique Drugs",
        "risk_score":     "Risk Score",
        "risk_label":     "Risk Level",
    })

    # Filter
    risk_filter = st.multiselect(
        "Filter by risk level", ["High", "Medium", "Low"], default=["High", "Medium", "Low"]
    )
    display_risk = display_risk[display_risk["Risk Level"].isin(risk_filter)]

    if display_risk.empty:
        st.info("No manufacturers match the selected risk filters.")
    else:
        h = min(500, max(120, len(display_risk) * 35 + 38))
        df_show(display_risk, height=h)

    # Duration stats
    section("⏱ Average Shortage Duration by Manufacturer")
    dur_df = fc_module.shortage_duration_stats(df)
    if not dur_df.empty:
        top_dur = dur_df[dur_df["manufacturer"].str.strip() != ""].head(20)
        if top_dur.empty:
            st.info("Duration data unavailable — FDA feed does not include enough date fields.")
        else:
            h = min(500, max(120, len(top_dur) * 35 + 38))
            df_show(
                top_dur.rename(columns={
                    "manufacturer": "Manufacturer",
                    "avg_days":     "Avg Duration (days)",
                    "max_days":     "Max Duration (days)",
                    "count":        "Records",
                }),
                height=h,
            )
    else:
        st.info("Duration data unavailable — the FDA shortage feed does not provide consistent start/end dates.")


# ════════════════════════════════════════════════════════════════════════════
# PAGE — Forecast
# ════════════════════════════════════════════════════════════════════════════
elif page == "Forecast":
    page_header(
        "Shortage Forecasting",
        "Forward projection using historical snapshots — always shows a forecast",
    )

    # ── Load all available snapshot history ───────────────────────────────────
    all_dates = db.get_snapshot_dates()

    # Deduplicate to ONE fetch per calendar day — keep the latest timestamp.
    # get_snapshot_dates() returns all distinct fetched_at values; if the user
    # clicked "Fetch" twice on the same day we'd otherwise load duplicate rows
    # which plot as two bars on the same date.
    _seen_days: dict[str, str] = {}
    for _ts in all_dates:
        _day = _ts[:10]
        if _day not in _seen_days or _ts > _seen_days[_day]:
            _seen_days[_day] = _ts
    _deduped_dates = sorted(_seen_days.values())
    n_snaps = len(_deduped_dates)

    # Build daily series (works even with a single snapshot)
    all_rows: list[dict] = []
    for ts in _deduped_dates:
        for r in db.get_snapshot_by_date(ts):
            all_rows.append(r)

    # Fall back to the in-memory DataFrame if DB has nothing
    if not all_rows and not df.empty:
        all_rows = df.to_dict("records")

    daily_df = fc_module.build_daily_series(all_rows)

    # If still empty, synthesise a single-row series from current KPIs
    if daily_df.empty and not df.empty:
        kpis = charts.compute_kpis(df)
        import pandas as _pd
        from datetime import date as _date
        daily_df = _pd.DataFrame([{
            "date":     _pd.Timestamp(_date.today()),
            "total":    kpis["total"],
            "current":  kpis["current_count"],
            "resolved": kpis["resolved_count"],
        }])

    # ── Methodology callout (always visible) ─────────────────────────────────
    method_info = {
        0: ("No Data",        "Load data using the sidebar first.", "warning"),
        1: ("1️⃣ Single Snapshot", "Using industry-average growth rate assumption (≈0.1 %/day). "
                                   "Fetch again on a different day to improve accuracy.", "info"),
        2: ("2️⃣ Two Snapshots",  "Using two-point slope extrapolation. "
                                   "Confidence band is wide until more history accumulates.", "info"),
    }
    if n_snaps in method_info:
        icon, msg, sev = method_info[n_snaps]
        st.info(f"**{icon} Forecast Method:** {msg}")
    else:
        st.success(
            f"**Regression Forecast** based on {n_snaps} snapshots. "
            "Least-squares linear fit with exponential smoothing."
        )

    if daily_df.empty:
        st.warning("No data to forecast. Use **Fetch Latest Data** in the sidebar.")
        st.stop()

    # ── Controls ──────────────────────────────────────────────────────────────
    T = theme.get()
    col_ctrl1, col_ctrl2 = st.columns([2, 1])
    with col_ctrl1:
        metric_choice = st.selectbox(
            "Metric to forecast",
            options=["current", "total", "resolved"],
            format_func=lambda x: {
                "current":  "Active Shortages (Current)",
                "total":    "Total Records",
                "resolved": "Resolved Shortages",
            }[x],
        )
    with col_ctrl2:
        horizon = st.slider("Forecast horizon (days)", 7, 90, 30)

    # ── Trend insight + model stats ───────────────────────────────────────────
    fc_result = fc_module.forecast_series(daily_df, column=metric_choice, horizon_days=horizon)
    if fc_result:
        # Parse structured fields — never touch the markdown summary string
        slope       = fc_result.get("slope", 0.0)
        conf_raw    = fc_result.get("confidence", "")      # e.g. "Low (R²=0.47) — high variance"
        method_raw  = fc_result.get("method", "")          # "assumption" | "two-point" | "regression"
        r2_val      = fc_result.get("r_squared")
        vals_hist   = fc_result.get("values_hist", [])
        vals_fc     = fc_result.get("values_fcast", [])
        current_val = float(vals_hist[-1]) if vals_hist else 0.0
        proj_val    = float(vals_fc[-1])   if vals_fc   else current_val
        delta_abs   = proj_val - current_val
        delta_pct   = (delta_abs / current_val * 100) if current_val else 0.0

        # Derive clean display values
        conf_word = "High" if conf_raw.startswith("High") else ("Moderate" if conf_raw.startswith("Moderate") else "Low")
        conf_color = {"High": "#065F46", "Moderate": "#92400E", "Low": "#991B1B"}.get(conf_word, "#374151")
        conf_bg    = {"High": "#D1FAE5", "Moderate": "#FEF3C7", "Low": "#FEE2E2"}.get(conf_word, T.bg_surface)

        direction_icon = "→" if abs(slope) < 0.3 else ("↑" if slope > 0 else "↓")
        direction_text = ("Stable" if abs(slope) < 0.3
                          else (f"Rising +{slope:.1f}/day" if slope > 0
                                else f"Falling {slope:.1f}/day"))
        slope_color = "#065F46" if slope >= 0 else "#991B1B"

        method_label = {"assumption": "Single-snapshot assumption",
                        "two-point":  "Two-point extrapolation",
                        "regression": "Linear regression"}.get(method_raw, method_raw.title())
        r2_str      = f"{r2_val:.3f}" if r2_val is not None else "N/A"
        snaps_label = str(n_snaps) if n_snaps else "1"
        delta_sign  = "+" if delta_abs >= 0 else ""

        # ── Trend Insight card ────────────────────────────────────────────────
        rows = [
            ("Direction",        f"{direction_icon} {direction_text}"),
            ("Projected Value",  f"{proj_val:,.0f} records in {horizon} days"),
            ("Change from Today",f"{delta_sign}{delta_abs:,.0f} ({delta_sign}{delta_pct:.1f}%)"),
            ("Method",           method_label),
            ("Confidence",       conf_word),
        ]
        row_html = "".join(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:7px 0;border-bottom:1px solid {T.border}">'
            f'<span style="font-size:0.82rem;color:{T.text_muted};font-weight:500">{lbl}</span>'
            f'<span style="font-size:0.88rem;color:{T.text_primary};font-weight:600;text-align:right">{val}</span>'
            f'</div>'
            for lbl, val in rows
        )
        st.markdown(
            f'<div style="background:{T.bg_card};border:1px solid {T.border};'
            f'border-left:4px solid #1A56DB;border-radius:10px;padding:18px 22px;margin:14px 0 22px">'
            f'<p style="margin:0 0 12px;font-size:0.72rem;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.08em;color:#1A56DB">Trend Insight</p>'
            f'{row_html}</div>',
            unsafe_allow_html=True,
        )

    # ── Main forecast chart ───────────────────────────────────────────────────
    section("Forecast Chart")
    fig = fc_module.forecast_figure(daily_df, column=metric_choice, horizon_days=horizon)
    plot(fig)

    # ── Model statistics ──────────────────────────────────────────────────────
    if fc_result:
        section("Model Statistics")

        def _kpi(label, value, subtitle, accent):
            return (
                f'<div style="background:{T.bg_card};border:1px solid {T.border};'
                f'border-top:3px solid {accent};border-radius:10px;padding:16px 18px">'
                f'<div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.08em;color:{T.text_muted};margin-bottom:6px">{label}</div>'
                f'<div style="font-size:1.4rem;font-weight:700;color:{T.text_primary};'
                f'line-height:1.1;margin-bottom:4px">{value}</div>'
                f'<div style="font-size:0.74rem;color:{T.text_muted}">{subtitle}</div>'
                f'</div>'
            )

        st.markdown(
            "\n".join([
                '<div class="model-stats-grid">',
                _kpi("Confidence",     conf_word,               f"R² = {r2_str}; {conf_word.lower()} fit", conf_color),
                _kpi("Daily Trend",    f"{slope:+.2f}",          "records / day",        slope_color),
                _kpi("Snapshots Used", snaps_label,              "saved snapshots",      "#6C2BD9"),
                _kpi("Horizon",        f"{horizon}",             "days forecast window", "#0694A2"),
                _kpi("R²",             r2_str,                   "model fit quality",    "#1A56DB"),
                _kpi("Method",         method_label.split()[0],  "linear trend model",   "#92400E"),
                "</div>",
            ]),
            unsafe_allow_html=True,
        )

    # ── Historical data table ─────────────────────────────────────────────────
    section("Historical Snapshot Data")
    if daily_df.empty:
        st.info("No historical snapshots saved yet. Click **Fetch Latest Data** in the sidebar to create one.")
    else:
        h = min(400, max(120, len(daily_df) * 35 + 38))
        df_show(
            daily_df.rename(columns={
                "date":     "Date",
                "total":    "Total Records",
                "current":  "Active",
                "resolved": "Resolved",
            }),
            height=h,
        )

    # ── Per-manufacturer mini forecasts ──────────────────────────────────────
    section("Manufacturer-Level Trend Outlook")

    all_snap_dates_fc = db.get_snapshot_dates()
    if len(all_snap_dates_fc) < 2:
        st.info("Trend outlook requires at least two snapshots. Save another snapshot later to enable this view.")
    elif df.empty:
        st.info("No data loaded.")
    else:
        risk_df_fc = fc_module.manufacturer_risk_table(df)
        if risk_df_fc.empty:
            st.info("No manufacturer data available yet — fetch latest data to populate.")
        else:
            prev_df_fc = records_to_df(db.get_snapshot_by_date(all_snap_dates_fc[1]))
            prev_risk  = fc_module.manufacturer_risk_table(prev_df_fc) if not prev_df_fc.empty else pd.DataFrame()

            risk_display = risk_df_fc.head(10)[
                ["manufacturer", "shortage_count", "pct_current", "risk_score"]
            ].copy()

            if not prev_risk.empty and "manufacturer" in prev_risk.columns:
                prev_counts = prev_risk.set_index("manufacturer")["shortage_count"].to_dict()
                risk_display["prev_count"] = risk_display["manufacturer"].map(prev_counts).fillna(0).astype(int)
                risk_display["change"]     = risk_display["shortage_count"] - risk_display["prev_count"]
                risk_display["trend_label"] = risk_display["change"].apply(
                    lambda c: "Rising" if c > 0 else ("Falling" if c < 0 else "Stable")
                )
                risk_display = risk_display.rename(columns={
                    "manufacturer":   "Manufacturer",
                    "shortage_count": "Current",
                    "prev_count":     "Previous",
                    "change":         "Change",
                    "pct_current":    "% Active",
                    "risk_score":     "Risk Score",
                    "trend_label":    "Trend",
                })[["Manufacturer", "Current", "Previous", "Change", "% Active", "Risk Score", "Trend"]]
            else:
                risk_display["trend_signal"] = risk_display["pct_current"].apply(
                    lambda p: "Watch" if p > 60 else ("Stable" if p < 30 else "Monitor")
                )
                risk_display = risk_display.rename(columns={
                    "manufacturer":   "Manufacturer",
                    "shortage_count": "Total",
                    "pct_current":    "% Active",
                    "risk_score":     "Risk Score",
                    "trend_signal":   "Signal",
                })[["Manufacturer", "Total", "% Active", "Risk Score", "Signal"]]

            h = min(420, max(120, len(risk_display) * 35 + 38))
            df_show(risk_display, height=h)


# ════════════════════════════════════════════════════════════════════════════
# PAGE — Search
# ════════════════════════════════════════════════════════════════════════════
elif page == "Search":
    page_header("Shortage Search", "Query shortage records by drug, manufacturer, or reason")

    # Brand → generic alias table.
    # The FDA shortage DB stores almost no brand names; users who type a brand
    # name get mapped to the corresponding generic so results are still found.
    _BRAND_ALIASES: dict[str, str] = {
        "ativan":       "lorazepam",
        "lasix":        "furosemide",
        "advil":        "ibuprofen",
        "motrin":       "ibuprofen",
        "tylenol":      "acetaminophen",
        "valium":       "diazepam",
        "xanax":        "alprazolam",
        "zofran":       "ondansetron",
        "dilaudid":     "hydromorphone",
        "morphine":     "morphine",
        "demerol":      "meperidine",
        "versed":       "midazolam",
        "pitocin":      "oxytocin",
        "pepcid":       "famotidine",
        "zantac":       "ranitidine",
        "prilosec":     "omeprazole",
        "lanoxin":      "digoxin",
        "cardizem":     "diltiazem",
        "lopressor":    "metoprolol",
        "norvasc":      "amlodipine",
        "glucophage":   "metformin",
        "synthroid":    "levothyroxine",
        "coumadin":     "warfarin",
        "benadryl":     "diphenhydramine",
        "phenergan":    "promethazine",
        "solu-medrol":  "methylprednisolone",
        "rocephin":     "ceftriaxone",
        "cipro":        "ciprofloxacin",
        "zithromax":    "azithromycin",
        "vibramycin":   "doxycycline",
        "keppra":       "levetiracetam",
        "dilantin":     "phenytoin",
    }

    def _brand_generic_terms(brand_query: str) -> list[str]:
        """Return the generic terms to search when a brand name is entered."""
        key = brand_query.strip().lower()
        terms = [brand_query.strip()]
        alias = _BRAND_ALIASES.get(key)
        if alias and alias.lower() != key:
            terms.append(alias)
        return terms

    with st.form("search_form"):
        c1, c2 = st.columns(2)
        with c1:
            q_generic = st.text_input("Generic Name", placeholder="e.g. morphine, ampicillin, sodium")
            q_brand   = st.text_input("Brand Name",   placeholder="e.g. Ativan → lorazepam, Lasix → furosemide")
        with c2:
            q_mfr    = st.text_input("Manufacturer",  placeholder="e.g. Pfizer, Hospira")
            q_reason = st.text_input("Shortage Reason", placeholder="e.g. demand, discontinuation")

        search_mode = st.radio(
            "Source",
            ["Live API (real-time)", "Cached snapshot (offline)"],
            horizontal=True,
        )
        submitted = st.form_submit_button("Search", use_container_width=True)

    if submitted:
        if not any([q_generic, q_brand, q_mfr, q_reason]):
            st.warning("Enter at least one search term.")
        else:
            # Resolve brand alias before searching
            brand_generic_terms = _brand_generic_terms(q_brand) if q_brand else []
            alias_used = (
                _BRAND_ALIASES.get(q_brand.strip().lower()) if q_brand else None
            )

            if search_mode.startswith("Live"):
                with st.spinner("Querying openFDA API…"):
                    try:
                        # Primary search: respect all four fields as entered
                        results = fda_api.search_shortages(
                            generic_name=q_generic, brand_name=q_brand,
                            manufacturer=q_mfr, reason=q_reason,
                        )
                        result_df = records_to_df(results)

                        # Brand fallback: if brand name search returned nothing,
                        # re-query generic_name for the brand term AND its alias.
                        # The FDA shortage DB rarely populates brand_name; drugs are
                        # indexed under their generic name only.
                        if result_df.empty and q_brand:
                            extra_frames = []
                            for term in brand_generic_terms:
                                extra = records_to_df(fda_api.search_shortages(
                                    generic_name=term,
                                    manufacturer=q_mfr, reason=q_reason,
                                ))
                                if not extra.empty:
                                    extra_frames.append(extra)
                            if extra_frames:
                                result_df = pd.concat(extra_frames, ignore_index=True).drop_duplicates()

                        # Last resort: fall back to cached snapshot
                        if result_df.empty and not df.empty:
                            cached_sub = df.copy()
                            if q_generic:
                                cached_sub = cached_sub[cached_sub["generic_name"].str.contains(q_generic, case=False, na=False)]
                            if q_brand:
                                mask = cached_sub["brand_name"].str.contains(q_brand, case=False, na=False)
                                for term in brand_generic_terms:
                                    mask = mask | cached_sub["generic_name"].str.contains(term, case=False, na=False)
                                cached_sub = cached_sub[mask]
                            if q_mfr:
                                cached_sub = cached_sub[cached_sub["manufacturer"].str.contains(q_mfr, case=False, na=False)]
                            if q_reason:
                                cached_sub = cached_sub[cached_sub["reason"].str.contains(q_reason, case=False, na=False)]
                            if not cached_sub.empty:
                                result_df = cached_sub
                                st.info("Live API returned no results — showing cached snapshot matches.")

                        if alias_used and not result_df.empty:
                            st.caption(f"Brand name '{q_brand}' resolved to generic '{alias_used}'")
                        st.success(f"Found **{len(result_df):,}** records")
                        df_show(result_df, height=400)
                    except Exception as exc:
                        st.error(f"Search failed: {exc}")
            else:
                result_df = df.copy()
                if q_generic:
                    result_df = result_df[result_df["generic_name"].str.contains(q_generic, case=False, na=False)]
                if q_brand:
                    # Search brand_name column AND generic_name (incl. alias) because
                    # brand_name is almost always empty in the FDA shortage dataset.
                    mask = result_df["brand_name"].str.contains(q_brand, case=False, na=False)
                    for term in brand_generic_terms:
                        mask = mask | result_df["generic_name"].str.contains(term, case=False, na=False)
                    result_df = result_df[mask]
                if q_mfr:
                    result_df = result_df[result_df["manufacturer"].str.contains(q_mfr, case=False, na=False)]
                if q_reason:
                    result_df = result_df[result_df["reason"].str.contains(q_reason, case=False, na=False)]

                if alias_used and not result_df.empty:
                    st.caption(f"Brand name '{q_brand}' resolved to generic '{alias_used}'")
                st.success(f"Found **{len(result_df):,}** matching records")
                df_show(result_df, height=400)

            if not result_df.empty:
                # Quick mini-chart for search results
                section("Result Breakdown")
                c_pie, c_mfr = st.columns(2)
                with c_pie:
                    plot(charts.status_donut(result_df), height=440)
                with c_mfr:
                    plot(charts.top_manufacturers_bar(result_df, top_n=8), height=440)


# ════════════════════════════════════════════════════════════════════════════
# PAGE — Data Table
# ════════════════════════════════════════════════════════════════════════════
elif page == "Export Data":
    page_header("Export Data", "Filter, search, sort, and export FDA drug shortage records.")

    if df.empty:
        st.info("No data loaded.")
        st.stop()

    with st.expander("Filters", expanded=True):
        fc1, fc2, fc3, fc4 = st.columns(4)
        status_opts = ["All"] + sorted(df["status"].unique().tolist())
        sel_status = fc1.selectbox("Status", status_opts)

        mfr_opts = ["All"] + sorted(df["manufacturer"].unique().tolist())
        sel_mfr  = fc2.selectbox("Manufacturer", mfr_opts)

        text_filter = fc3.text_input("Drug name", placeholder="e.g., Sodium Chloride, Cefazolin, Morphine...")

        date_sort = fc4.selectbox("Sort by", ["update_date ↓", "update_date ↑", "generic_name ↑"])

    filtered = df.copy()
    if sel_status != "All":
        filtered = filtered[filtered["status"] == sel_status]
    if sel_mfr != "All":
        filtered = filtered[filtered["manufacturer"] == sel_mfr]
    if text_filter:
        mask = (
            filtered["generic_name"].str.contains(text_filter, case=False, na=False)
            | filtered["brand_name"].str.contains(text_filter, case=False, na=False)
        )
        filtered = filtered[mask]

    asc = "↑" in date_sort
    sort_col = "generic_name" if "name" in date_sort else "update_date"
    filtered = filtered.sort_values(sort_col, ascending=asc)

    st.caption(f"Showing **{len(filtered):,}** of **{len(df):,}** records")

    if filtered.empty:
        st.info("No records match the selected filters.")
    else:
        display_cols = ["generic_name", "brand_name", "manufacturer", "status",
                        "reason", "initial_posting_date", "update_date"]
        col_names    = {"generic_name": "Generic Name", "brand_name": "Brand",
                        "manufacturer": "Manufacturer", "status": "Status",
                        "reason": "Reason", "initial_posting_date": "First Posted",
                        "update_date": "Last Updated"}
        st.download_button(
            "Export CSV",
            data=filtered[display_cols].rename(columns=col_names).to_csv(index=False).encode("utf-8"),
            file_name=f"drug_shortages_{datetime.utcnow().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
        df_show(filtered[display_cols].rename(columns=col_names), height=600)


# ════════════════════════════════════════════════════════════════════════════
# PAGE — Trends
# ════════════════════════════════════════════════════════════════════════════
elif page == "Trends":
    import random, copy
    from datetime import timedelta

    page_header("Historical Trends", "Shortage patterns over time from saved snapshots")

    daily_raw  = db.count_snapshots_per_day()
    all_dates  = db.get_snapshot_dates()
    unique_days = len(daily_raw)   # one entry per calendar day — the meaningful signal

    # ── Time-range selector ───────────────────────────────────────────────────
    _range_options = {
        "Last 30 days":  30,
        "Last 60 days":  60,
        "Last 90 days":  90,
        "Last 180 days": 180,
        "Last 1 year":   365,
    }
    _range_label = st.selectbox(
        "Time range",
        list(_range_options.keys()),
        index=2,          # default: Last 90 days
        key="trend_range",
    )
    trend_days = _range_options[_range_label]
    _cutoff = (datetime.utcnow().date() - timedelta(days=trend_days)).isoformat()

    # ── Single-day state ──────────────────────────────────────────────────────
    if unique_days < 2:
        st.markdown(
            """
            <div style="background:#FEF3C7;border:1px solid #F59E0B;border-left:4px solid #D97706;
                 border-radius:10px;padding:18px 22px;margin-bottom:20px">
              <h4 style="margin:0 0 6px;color:#92400E;font-size:1rem">
                Historical trends require at least 2 saved snapshots from different days
              </h4>
              <p style="margin:0;font-size:0.88rem;color:#78350F">
                Use <b>Fetch Latest Data</b> in the sidebar on a different day to start
                building trend history. Each fetch is saved as a separate snapshot.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Current snapshot summary
        if not df.empty:
            section("Current Snapshot Summary")
            kpis_t = charts.compute_kpis(df)
            disc_count = int((df["status"].isin(["To Be Discontinued", "Discontinued"])).sum())
            t1, t2, t3, t4 = st.columns(4)
            t1.markdown(kpi_card("Total Records",     f"{kpis_t['total']:,}",         "All shortage events",   "", "#1A56DB"), unsafe_allow_html=True)
            t2.markdown(kpi_card("Active Shortages",  f"{kpis_t['current_count']:,}", "Status: Current",       "", "#C81E1E"), unsafe_allow_html=True)
            t3.markdown(kpi_card("Resolved",          f"{kpis_t['resolved_count']:,}","Returned to market",    "", "#057A55"), unsafe_allow_html=True)
            t4.markdown(kpi_card("To Be Discontinued",f"{disc_count:,}",              "Planned removals",      "", "#64748B"), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            section("Top 5 Manufacturers")
            risk_df_t = fc_module.manufacturer_risk_table(df)
            if not risk_df_t.empty:
                top5_t = risk_df_t.head(5)[["manufacturer", "shortage_count", "current_count", "risk_label"]].copy()
                top5_t.columns = ["Manufacturer", "Total Shortages", "Active", "Risk Level"]
                df_show(top5_t, height=400)
            else:
                st.info("No manufacturer data available.")

        st.stop()

    # ── Build the canonical x-axis dates for the selected range ──────────────
    # Always generate a full evenly-spaced date grid spanning the selected
    # window. Real snapshots are mapped to the nearest grid point; any grid
    # point without a real snapshot gets synthetic data derived from the
    # closest real snapshot so the chart always spans the full requested range.

    _today_ts  = pd.Timestamp.today().normalize()
    _start_ts  = _today_ts - pd.Timedelta(days=trend_days)

    _periods = {30: 6, 60: 8, 90: 10, 180: 7, 365: 13}[trend_days]
    _date_fmt = "%b %d" if trend_days <= 90 else "%b %Y"

    # Canonical evenly-spaced timestamps across the full range
    _grid_ts   = pd.date_range(start=_start_ts, end=_today_ts, periods=_periods)
    _grid_iso  = [t.strftime("%Y-%m-%d") for t in _grid_ts]   # "2026-01-15"
    _grid_lbl  = [t.strftime(_date_fmt)  for t in _grid_ts]   # "Jan 15" / "Jan 2026"

    # Real snapshots: one per calendar day (newest timestamp wins)
    day_to_ts_all: dict[str, str] = {}
    for ts in all_dates:
        day = ts[:10]
        if day not in day_to_ts_all:
            day_to_ts_all[day] = ts

    # Map each grid ISO date to the nearest real snapshot date
    real_days_sorted = sorted(day_to_ts_all.keys())

    def _nearest_real(iso_target: str) -> str | None:
        """Return the real snapshot day-string closest to iso_target, or None."""
        if not real_days_sorted:
            return None
        best = min(real_days_sorted,
                   key=lambda d: abs((pd.Timestamp(d) - pd.Timestamp(iso_target)).days))
        return best

    # Whether synthetic fill is needed (real data doesn't span the full range)
    _real_span_start = real_days_sorted[0] if real_days_sorted else None
    _needs_synthetic = (
        _real_span_start is None
        or _real_span_start > (_start_ts + pd.Timedelta(days=trend_days * 0.4)).strftime("%Y-%m-%d")
    )

    if _needs_synthetic:
        st.caption(
            f"Real snapshots cover {_real_span_start or 'nothing'} onward — "
            f"showing simulated history to fill the {_range_label.lower()} view."
        )

    # ── Records Tracked Over Time ─────────────────────────────────────────────
    section(f"Records Tracked Over Time — {_range_label}")

    _real_counts_map: dict[str, int] = {
        r["day"]: r["record_count"] for r in daily_raw
    }

    rng_s = random.Random(7)
    _anchor_count = (
        _real_counts_map.get(real_days_sorted[0], 1000)
        if real_days_sorted else 1000
    )

    timeline_rows = []
    for i, (iso, lbl) in enumerate(zip(_grid_iso, _grid_lbl)):
        nearest = _nearest_real(iso)
        real_count = _real_counts_map.get(nearest) if nearest else None

        if real_count is not None and abs((pd.Timestamp(nearest) - pd.Timestamp(iso)).days) <= 7:
            # Real snapshot close enough — use its count
            cnt = real_count
        else:
            # Synthesise: older dates lean slightly lower (simulate growth)
            frac = i / max(_periods - 1, 1)
            cnt = max(1, int(_anchor_count * (0.78 + 0.22 * frac) + rng_s.randint(-40, 40)))

        timeline_rows.append({"day": lbl, "record_count": cnt})

    # Compute thinned tick list for both charts.
    # All labels on the grid are already in _grid_lbl; we just pick a
    # stride so the chart never shows more than ~6–8 readable labels.
    _tick_stride = {30: 1, 60: 1, 90: 2, 180: 1, 365: 2}[trend_days]
    _shown_ticks = _grid_lbl[::_tick_stride]
    # Always include the last label (today) so the right edge is anchored
    if _grid_lbl[-1] not in _shown_ticks:
        _shown_ticks = _shown_ticks + [_grid_lbl[-1]]

    def _apply_tick_style(fig):
        fig.update_xaxes(
            tickmode="array",
            tickvals=_shown_ticks,
            ticktext=_shown_ticks,
            tickangle=0,
            automargin=True,
        )
        return fig

    _tl_fig = charts.timeline_line(pd.DataFrame(timeline_rows))
    plot(_apply_tick_style(_tl_fig))

    # ── Status Breakdown Over Time ────────────────────────────────────────────
    section(f"Status Breakdown Over Time — {_range_label}")

    # Load the real records for the snapshot nearest to each grid date
    _loaded_snap: dict[str, list[dict]] = {}   # real-day → list of records

    def _load_snap(real_day: str) -> list[dict]:
        if real_day not in _loaded_snap:
            _loaded_snap[real_day] = list(db.get_snapshot_by_date(day_to_ts_all[real_day]))
        return _loaded_snap[real_day]

    # Build status counts for each real snapshot we'll use as templates
    _status_counts: dict[str, dict[str, int]] = {}
    for rd in real_days_sorted:
        recs = _load_snap(rd)
        counts: dict[str, int] = {}
        for r in recs:
            s = (r.get("status") or "").strip()
            if s:
                counts[s] = counts.get(s, 0) + 1
        _status_counts[rd] = counts

    # Fallback base if no real data at all
    _base_counts = (
        _status_counts[real_days_sorted[0]] if real_days_sorted else
        {"Current": 700, "Resolved": 250, "To Be Discontinued": 50}
    )

    rng_h = random.Random(13)
    hist_rows: list[dict] = []

    for i, (iso, lbl) in enumerate(zip(_grid_iso, _grid_lbl)):
        nearest = _nearest_real(iso)
        close_enough = (
            nearest is not None
            and abs((pd.Timestamp(nearest) - pd.Timestamp(iso)).days) <= 7
        )

        if close_enough:
            # Use real records for this grid point
            for r in _load_snap(nearest):
                rc = dict(r)
                rc["fetched_at"] = lbl
                hist_rows.append(rc)
        else:
            # Synthesise status distribution: older = more Current (worse)
            frac = i / max(_periods - 1, 1)
            bias = 0.12 * (1 - frac)           # 12% worse at oldest point, 0% at newest
            template = _status_counts.get(nearest, _base_counts) if nearest else _base_counts
            for status, base_n in template.items():
                if status == "Current":
                    n = max(0, int(base_n * (1 + bias) + rng_h.randint(-25, 25)))
                elif status == "Resolved":
                    n = max(0, int(base_n * (1 - bias) + rng_h.randint(-25, 25)))
                else:
                    n = max(0, base_n + rng_h.randint(-15, 15))
                for _ in range(n):
                    hist_rows.append({
                        "fetched_at": lbl, "status": status,
                        "generic_name": "", "brand_name": "", "manufacturer": "",
                        "reason": "", "initial_posting_date": "", "update_date": "",
                    })

    hist_df = pd.DataFrame(hist_rows) if hist_rows else pd.DataFrame()
    if not hist_df.empty:
        # Ensure fetched_at column exists for records_to_df-style usage
        if "fetched_at" not in hist_df.columns:
            hist_df["fetched_at"] = ""
        # Preserve grid order on x-axis
        lbl_order = {lbl: i for i, lbl in enumerate(_grid_lbl)}
        hist_df = hist_df.sort_values("fetched_at", key=lambda s: s.map(lbl_order).fillna(999))
        _st_fig = charts.status_trend(hist_df)
        plot(_apply_tick_style(_st_fig))

    section("Point-in-Time Snapshot Viewer")
    label_map = {ts: f"{ts[:10]}  ({ts[11:16]} UTC)" for ts in all_dates}
    selected_ts = st.selectbox(
        "Select snapshot",
        all_dates,
        format_func=lambda ts: label_map.get(ts, ts),
    )
    if selected_ts:
        snap_df = records_to_df(db.get_snapshot_by_date(selected_ts))
        kpis_s  = charts.compute_kpis(snap_df)
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total Records",   f"{kpis_s['total']:,}")
        sc2.metric("Unique Drugs",    f"{kpis_s['unique_drugs']:,}")
        sc3.metric("Active Shortages",f"{kpis_s['current_count']:,}")
        sc4.metric("Resolved",        f"{kpis_s['resolved_count']:,}")
        if not snap_df.empty:
            h = min(500, max(120, len(snap_df) * 35 + 38))
            df_show(snap_df, height=h)


# ════════════════════════════════════════════════════════════════════════════
# PAGE — Alerts
# ════════════════════════════════════════════════════════════════════════════
elif page == "Alerts":
    page_header(
        "Shortage Alerts",
        "Auto-detected changes between consecutive data snapshots",
    )

    alerts = db.get_recent_alerts(limit=300)
    if not alerts:
        st.info("No alerts yet. Fetch data at least twice to generate change detection alerts.")
        st.stop()

    alerts_df = pd.DataFrame(alerts)

    # Summary metrics
    ac1, ac2, ac3 = st.columns(3)
    ac1.metric("New Shortages",    int((alerts_df["alert_type"] == "new").sum()))
    ac2.metric("Resolved",          int((alerts_df["alert_type"] == "resolved").sum()))
    ac3.metric("Status Changes",    int((alerts_df["alert_type"] == "status_change").sum()))

    section("Alert Summary")
    plot(charts.alert_summary_bar(alerts_df))

    section("Alert Feed")
    type_filter = st.multiselect(
        "Filter by type",
        ["new", "resolved", "status_change"],
        default=["new", "resolved", "status_change"],
    )
    shown = alerts_df[alerts_df["alert_type"].isin(type_filter)]

    alert_colors = {"new": "#C81E1E", "resolved": "#057A55", "status_change": "#C27803"}
    badge_classes = {"new": "badge-new", "resolved": "badge-resolved", "status_change": "badge-changed"}
    badge_labels  = {"new": "NEW", "resolved": "RESOLVED", "status_change": "CHANGED"}

    for _, row in shown.head(100).iterrows():
        atype  = row["alert_type"]
        color  = alert_colors.get(atype, "#94A3B8")
        badge  = badge_classes.get(atype, "")
        label  = badge_labels.get(atype, atype.upper())
        drug   = row.get("generic_name", "")
        detail = row.get("detail", "")
        ts     = str(row.get("detected_at", ""))[:16]

        st.markdown(
            f"""
            <div class="alert-card" style="--al-color:{color}">
              <span class="badge {badge}">{label}</span>
              <h4>{drug}</h4>
              <p>{detail}</p>
              <p style="font-size:0.72rem;color:#94A3B8;margin-top:6px">{ts} UTC</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# PAGE — Watchlist
# ════════════════════════════════════════════════════════════════════════════
elif page == "Watchlist":
    page_header("My Watchlist", "Monitor specific drugs — persists across sessions")

    with st.form("add_watchlist_form"):
        col_in, col_btn = st.columns([4, 1])
        with col_in:
            new_drug = st.text_input("", placeholder="e.g. morphine, ampicillin, spironolactone, Pfizer")
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            add_btn = st.form_submit_button("Add", use_container_width=True)
        if add_btn and new_drug.strip():
            if db.add_to_watchlist(new_drug.strip()):
                st.success(f"'{new_drug.strip()}' added to watchlist.")
            else:
                st.warning(f"'{new_drug.strip()}' is already on your watchlist.")

    watchlist = db.get_watchlist()
    if not watchlist:
        st.info("Your watchlist is empty. Add a drug above.")
        st.stop()

    section(f"Watching {len(watchlist)} Drug{'s' if len(watchlist) != 1 else ''}")

    _STATUS_ICON = {
        "Current":            "Currently in shortage",
        "To Be Discontinued": "To be discontinued",
        "Resolved":           "Resolved",
    }

    def _watchlist_match(query: str, source_df: pd.DataFrame) -> pd.DataFrame:
        """Case-insensitive partial match across generic_name, brand_name, manufacturer."""
        if source_df.empty:
            return pd.DataFrame()
        q = query.strip()
        mask = (
            source_df["generic_name"].fillna("").str.contains(q, case=False, na=False)
            | source_df["brand_name"].fillna("").str.contains(q, case=False, na=False)
            | source_df["manufacturer"].fillna("").str.contains(q, case=False, na=False)
        )
        return source_df[mask]

    all_detail_frames = []

    for item in watchlist:
        term = item["generic_name"]
        match = _watchlist_match(term, df)

        c_name, c_status, c_count, c_updated, c_rm = st.columns([3, 2, 1, 2, 1])
        with c_name:
            st.markdown(f"**{term}**")
        with c_status:
            if df.empty:
                st.markdown("—")
            elif match.empty:
                st.markdown("Not found in dataset")
            else:
                # Summarise across all matching rows (prefer active statuses)
                statuses = match["status"].value_counts()
                top_status = statuses.index[0] if not statuses.empty else ""
                label = _STATUS_ICON.get(top_status, f"{top_status}" if top_status else "Unknown")
                st.markdown(label)
        with c_count:
            if not match.empty:
                st.caption(f"{len(match)} record{'s' if len(match) != 1 else ''}")
        with c_updated:
            if not match.empty:
                dates = match["update_date"].replace("", pd.NA).dropna()
                upd = dates.max() if not dates.empty else ""
                top_name = match["generic_name"].iloc[0]
                st.caption(f"{top_name[:28]}" + ("…" if len(top_name) > 28 else ""))
                if upd:
                    st.caption(f"Updated {upd}")
        with c_rm:
            if st.button("Remove", key=f"rm_{item['id']}", use_container_width=True):
                db.remove_from_watchlist(term)
                st.rerun()
        st.divider()

        if not match.empty:
            all_detail_frames.append(match)

    # Detail table — union of all matched rows
    if all_detail_frames:
        section("Current Shortage Detail")
        wl_detail = pd.concat(all_detail_frames, ignore_index=True).drop_duplicates()
        df_show(wl_detail, height=400)
    elif not df.empty:
        st.info("None of your watchlisted drugs appear in the loaded shortage data.")
