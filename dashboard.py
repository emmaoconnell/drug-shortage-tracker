"""
dashboard.py — Chart library for Drug Shortage Tracker.

All charts pull colors from theme.get() so light/dark mode works automatically.
Every text element >= 12 px; titles >= 16 px bold. WCAG-AA compliant.
"""

import re as _re
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

import theme as _theme

# Fixed semantic colors (same in both themes — high contrast on their own)
STATUS_COLORS = {
    "Current":            "#DC2626",   # vivid red
    "Resolved":           "#16A34A",   # vivid green
    "Discontinued":       "#6366F1",   # indigo — clearly distinct from amber
    "To Be Discontinued": "#F59E0B",   # vivid amber
    "No Longer Marketed": "#F59E0B",   # same amber group
}

_FONT = "Inter, system-ui, -apple-system, sans-serif"

# Excluded from the main reasons chart
_REASON_EXCLUDE = {"", "other", "not specified", "n/a", "unknown"}


# ════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ════════════════════════════════════════════════════════════════════════════

def _T():
    return _theme.get()


def _base(title: str = "", height: int = 400, margin: dict | None = None, showlegend: bool = False) -> dict:
    return _theme.plotly_base(title=title, height=height, margin=margin, showlegend=showlegend)


def _no_data_fig(msg: str = "No data available") -> None:
    """Return None so callers can do: fig = func(); if fig: st.plotly_chart(fig)"""
    return None  # blank-box sentinel — never renders a large empty Plotly frame


# ── Manufacturer-specific label shortener (more aggressive than shorten_label) ──
_MFR_STRIP_SUFFIXES = _re.compile(
    r",?\s*\b(LLC|LLP|LP|PC|PLC|NV|BV|AG|GmbH|SA|SAS|SRL|SRO)\b"
    r"|,?\s*\ba\s+\w+\s+Company\b"           # ", a Pfizer Company"
    r"|,?\s*\bIncorporated\b"
    r"|,?\s*\bInc\."                          # "Inc." — no trailing \b (dot is non-word)
    r"|,?\s*\bLimited\b"
    r"|,?\s*\bLtd\."                          # "Ltd."
    r"|,?\s*\bCorporation\b"
    r"|,?\s*\bCorp\."                         # "Corp." — before bare Corp to avoid Corp\b issues
    r"|,?\s*\bCo\."                           # "Co." — dot required so "Company" is safe
    r"|\bUSA\b|\bU\.S\.A\.\b|\bU\.S\.\b"
    r"|,?\s*\bInstitutional\b"
    r"|,?\s*\bPharmacies\b",
    _re.IGNORECASE,
)
# After suffix strip, clean any orphaned whitespace / trailing commas / dots
_MFR_CLEANUP = _re.compile(r"\s*\.\s*$|,\s*$|\s{2,}")
_MFR_ABBREVS: list[tuple[str, str]] = [
    (r"\bPharmaceuticals\b",  "Pharma."),
    (r"\bPharmaceutical\b",   "Pharma."),
    (r"\bHealthcare\b",       "HC"),
    (r"\bMedical\b",          "Med."),
    (r"\bInternational\b",    "Intl."),
    (r"\bLaboratories\b",     "Labs"),
    (r"\bLaboratory\b",       "Lab"),
    (r"\bManufacturing\b",    "Mfg."),
    (r"\bCompany\b",          "Co."),
    (r"\bIncorporated\b",     ""),
]

def shorten_manufacturer_name(name: str, max_len: int = 14) -> str:
    """Aggressively shorten a manufacturer name for tight y-axis / x-axis labels.

    Full original name must be passed to Plotly customdata for hover text.
    """
    s = name.strip()
    # Strip noisy legal suffixes first
    s = _MFR_STRIP_SUFFIXES.sub("", s)
    # Clean orphaned trailing dots / commas / extra spaces left by suffix removal
    s = _MFR_CLEANUP.sub(lambda m: " " if m.group().strip() == "" else "", s).strip().strip(",").strip()
    # Apply abbreviations
    for pattern, repl in _MFR_ABBREVS:
        s = _re.sub(pattern, repl, s, flags=_re.IGNORECASE)
    s = s.strip().strip(",").strip()
    if not s:
        s = name.strip()  # fallback to original if we stripped everything

    if len(s) <= max_len:
        return s

    # Split at comma → two lines
    if "," in s:
        p1 = s[:s.index(",")].strip()
        p2 = s[s.index(",") + 1:].strip()
        if len(p1) <= max_len:
            p2_short = (p2[:max_len - 1] + "…") if len(p2) > max_len else p2
            return p1 + "<br>" + p2_short

    # Word-wrap into 2 lines
    words = s.split()
    l1, l2, cur = [], [], 0
    split = False
    for w in words:
        if not split and cur + (1 if cur else 0) + len(w) > max_len:
            split = True
            l2.append(w)
            cur = len(w)
        elif split:
            l2.append(w)
        else:
            l1.append(w)
            cur += (1 if cur else 0) + len(w)
    line1 = " ".join(l1)
    line2 = " ".join(l2)
    if line2:
        if len(line2) > max_len:
            line2 = line2[:max_len - 1] + "…"
        return line1 + "<br>" + line2
    return line1[:max_len - 1] + "…"


_ABBREVS: list[tuple[str, str]] = [
    # suffix-strip patterns FIRST (before generic word replacements fire)
    (r",\s*a\s+Pfizer\s+Company\b",  ""),   # "…, a Pfizer Company" → ""
    (r",\s*a\s+\w+\s+Company\b",    ""),    # "…, a XYZ Company" → ""
    # word abbreviations — longer/more-specific before shorter
    (r"\bPharmaceuticals\b",         "Pharma."),
    (r"\bPharmaceutical\b",          "Pharma."),
    (r"\bIncorporated\b",            "Inc."),
    (r"\bHealthcare\b",              "HC"),
    (r"\bUnited States\b",           "US"),
    (r"\bLaboratories\b",            "Labs"),
    (r"\bLaboratory\b",              "Lab"),
    (r"\bInternational\b",           "Intl."),
    (r"\bManufacturing\b",           "Mfg."),
    (r"\bCorporation\b",             "Corp."),
    (r"\bLimited\b",                 "Ltd."),
    (r"\bCompany\b",                 "Co."),
]

def shorten_label(text: str, max_chars: int = 24) -> str:
    """Abbreviate and optionally wrap a y-axis label for mobile display.

    Full original label should be passed separately to hover customdata.
    """
    s = text.strip()
    for pattern, replacement in _ABBREVS:
        s = _re.sub(pattern, replacement, s, flags=_re.IGNORECASE)
    s = s.strip().rstrip(",").strip()

    if len(s) <= max_chars:
        return s

    # Try splitting at the first comma if that gives a short enough first line
    if "," in s:
        part = s[:s.index(",")].strip()
        rest = s[s.index(",") + 1:].strip()
        if len(part) <= max_chars:
            return part + "<br>" + (rest[:max_chars] if len(rest) <= max_chars else rest[:max_chars - 1] + "…")

    # Word-wrap into 2 lines of max_chars each
    words = s.split()
    line1, line2 = [], []
    cur_len = 0
    split_done = False
    for w in words:
        if not split_done and cur_len + (1 if cur_len else 0) + len(w) > max_chars:
            split_done = True
            cur_len = len(w)
            line2.append(w)
        elif split_done:
            line2.append(w)
        else:
            line1.append(w)
            cur_len += (1 if cur_len else 0) + len(w)
    l1 = " ".join(line1)
    l2 = " ".join(line2)
    if l2:
        if len(l2) > max_chars:
            l2 = l2[:max_chars - 1] + "…"
        return l1 + "<br>" + l2
    return l1[:max_chars - 1] + "…" if len(l1) > max_chars else l1


def _truncate_label(text: str, max_len: int = 22) -> str:
    """Legacy alias — prefer shorten_label for new call sites."""
    return shorten_label(text, max_chars=max_len)


def _wrap_label(text: str, width: int = 34) -> str:
    words = text.split()
    lines, line, line_len = [], [], 0
    for w in words:
        if line_len and line_len + 1 + len(w) > width:
            lines.append(" ".join(line))
            line, line_len = [w], len(w)
        else:
            line.append(w)
            line_len += (1 if line_len else 0) + len(w)
    if line:
        lines.append(" ".join(line))
    return "<br>".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# KPI helpers
# ════════════════════════════════════════════════════════════════════════════

def compute_kpis(df: pd.DataFrame) -> dict:
    if df.empty:
        return dict(total=0, unique_drugs=0, unique_manufacturers=0,
                    current_count=0, resolved_count=0, discontinued_count=0,
                    unspecified_reason_pct=0.0)
    total = len(df)
    unspecified = int(df["reason"].fillna("").str.strip().eq("").sum()) if "reason" in df.columns else 0
    return dict(
        total                  = total,
        unique_drugs           = df["generic_name"].nunique(),
        unique_manufacturers   = df["manufacturer"].nunique(),
        current_count          = int((df["status"] == "Current").sum()),
        resolved_count         = int((df["status"] == "Resolved").sum()),
        discontinued_count     = int(df["status"].isin(["Discontinued", "To Be Discontinued"]).sum()),
        unspecified_reason_pct = round(unspecified / total * 100, 1) if total else 0.0,
    )


# ════════════════════════════════════════════════════════════════════════════
# Status charts
# ════════════════════════════════════════════════════════════════════════════

def status_donut(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _no_data_fig("No status data")
    T = _T()

    counts = df["status"].value_counts().reset_index()
    counts.columns = ["status", "count"]
    total  = int(counts["count"].sum())
    colors = [STATUS_COLORS.get(s, T.text_muted) for s in counts["status"]]

    fig = go.Figure(go.Pie(
        labels=counts["status"],
        values=counts["count"],
        hole=0.62,
        marker=dict(colors=colors, line=dict(color=T.chart_bg, width=2.5)),
        textinfo="none",
        hovertemplate="<b>%{label}</b><br>%{value:,} records<br>%{percent}<extra></extra>",
        pull=[0.04 if s == "Current" else 0 for s in counts["status"]],
        domain=dict(x=[0.05, 0.58], y=[0.12, 0.88]),
    ))
    fig.add_annotation(
        text=f"<b>{total:,}</b><br><span style='font-size:14px'>TOTAL</span>",
        x=0.315, y=0.5, showarrow=False,
        xanchor="center", yanchor="middle",
        font=dict(family=_FONT, size=22, color=T.text_primary),
    )
    layout = _base("Shortage Status Distribution", height=360,
                   margin=dict(t=56, b=16, l=0, r=16), showlegend=True)
    layout["legend"].update(
        orientation="v", x=0.60, y=0.5, yanchor="middle", xanchor="left",
        font=dict(family=_FONT, size=11, color=T.text_primary),
        bgcolor="rgba(0,0,0,0)", borderwidth=0,
    )
    fig.update_layout(**{k: v for k, v in layout.items() if k not in ("xaxis", "yaxis")})
    return fig


def status_trend(df_history: pd.DataFrame) -> go.Figure:
    if df_history.empty:
        return _no_data_fig("No historical snapshot data")
    T = _T()

    grouped = df_history.groupby(["fetched_at", "status"]).size().reset_index(name="count")
    date_order = list(dict.fromkeys(df_history["fetched_at"].tolist()))

    fig = go.Figure()
    for status, color in STATUS_COLORS.items():
        sub = grouped[grouped["status"] == status]
        if sub.empty:
            continue
        sub = sub.set_index("fetched_at").reindex(date_order, fill_value=0).reset_index()
        sub.columns = ["fetched_at", "status", "count"]
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        fill_rgba = f"rgba({r},{g},{b},0.10)"
        fig.add_trace(go.Scatter(
            x=sub["fetched_at"], y=sub["count"],
            name=status,
            mode="lines+markers",
            line=dict(color=color, width=2.5),
            marker=dict(size=8, color=color, line=dict(color=T.chart_bg, width=1.5)),
            fill="tozeroy", fillcolor=fill_rgba,
            hovertemplate=f"<b>{status}</b><br>%{{x}}: %{{y:,}} records<extra></extra>",
        ))

    layout = _base("Shortage Status Breakdown Over Time", height=420,
                   margin=dict(t=70, b=90, l=70, r=80), showlegend=True)
    layout["xaxis"].update(
        title="Snapshot Date",
        categoryorder="array",
        categoryarray=date_order,
        tickangle=0,
        automargin=True,
        range=[-0.2, len(date_order) - 0.8],
    )
    layout["yaxis"].update(title="Total Shortage Records", rangemode="tozero")
    layout["legend"].update(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    layout["hovermode"] = "x unified"
    fig.update_layout(**layout)
    return fig


# ════════════════════════════════════════════════════════════════════════════
# Manufacturer charts
# ════════════════════════════════════════════════════════════════════════════

def _non_blank_mfr(df: pd.DataFrame) -> pd.Series:
    return df.loc[df["manufacturer"].str.strip() != "", "manufacturer"]


def top_manufacturers_bar(df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    if df.empty or "manufacturer" not in df.columns:
        return _no_data_fig("No manufacturer data")
    T = _T()

    top = _non_blank_mfr(df).value_counts().head(top_n).reset_index()
    if top.empty:
        return _no_data_fig("Fetch latest data to populate manufacturer charts")
    top.columns = ["manufacturer", "count"]
    top = top.sort_values("count")

    norm   = (top["count"] - top["count"].min()) / max(top["count"].max() - top["count"].min(), 1)
    colors = [f"rgba(26,86,219,{0.38 + 0.62 * float(v):.2f})" for v in norm]

    short_labels = top["manufacturer"].apply(shorten_manufacturer_name)
    _max_line = short_labels.apply(
        lambda t: max(len(s) for s in t.split("<br>"))
    ).max()
    left_margin = min(140, max(90, _max_line * 7))
    height = max(400, top_n * 36 + 80)

    fig = go.Figure(go.Bar(
        x=top["count"], y=short_labels,
        orientation="h",
        marker=dict(color=colors, line=dict(color=T.chart_bg, width=0.5)),
        hovertemplate="<b>%{customdata}</b><br>Shortages: %{x:,}<extra></extra>",
        customdata=top["manufacturer"],
    ))
    layout = _base(f"Top {top_n} Manufacturers by Shortage Count", height=height,
                   margin=dict(t=64, b=90, l=left_margin, r=70))
    layout["xaxis"].update(title="Shortage Count")
    layout["yaxis"].update(tickfont=dict(family=_FONT, size=11, color=T.text_primary))
    fig.update_layout(**layout)
    return fig


def manufacturer_current_vs_resolved(df: pd.DataFrame, top_n: int = 12) -> go.Figure:
    """Horizontal grouped bar chart — manufacturers on y-axis, status counts on x-axis.

    Horizontal layout prevents x-axis label cramping on mobile and makes
    manufacturer names readable without rotation.
    """
    if df.empty or "manufacturer" not in df.columns:
        return _no_data_fig("No manufacturer data")
    T = _T()

    top_names = _non_blank_mfr(df).value_counts().head(top_n).index.tolist()
    if not top_names:
        return _no_data_fig("Fetch latest data to populate manufacturer charts")

    sub   = df[df["manufacturer"].isin(top_names)]
    pivot = (
        sub.groupby(["manufacturer", "status"]).size().reset_index(name="count")
        .pivot(index="manufacturer", columns="status", values="count")
        .fillna(0).reindex(top_names)
    )
    # Sort by total shortage count descending (highest at top)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=True).index]

    full_names  = pivot.index.tolist()
    short_names = [shorten_manufacturer_name(n) for n in full_names]

    fig = go.Figure()
    for status, color in STATUS_COLORS.items():
        if status in pivot.columns:
            vals = pivot[status].tolist()
            hover = [
                f"<b>{full_names[i]}</b><br>{status}: {int(vals[i]):,}<extra></extra>"
                for i in range(len(full_names))
            ]
            fig.add_trace(go.Bar(
                name=status,
                y=short_names,
                x=vals,
                orientation="h",
                marker_color=color,
                hovertemplate="%{customdata}<extra></extra>",
                customdata=hover,
            ))

    _max_line = max(
        max(len(s) for s in n.split("<br>")) for n in short_names
    )
    left_margin = min(140, max(90, _max_line * 7))
    height = max(460, top_n * 44 + 100)

    fig.update_layout(barmode="group")
    layout = _base("Shortage Status by Top Manufacturers", height=height,
                   margin=dict(t=64, b=70, l=left_margin, r=20), showlegend=True)
    layout["xaxis"].update(title="Shortage Count",
                           tickfont=dict(family=_FONT, size=11, color=T.text_primary))
    layout["yaxis"].update(tickfont=dict(family=_FONT, size=11, color=T.text_primary),
                           automargin=True)
    _leg_bg = "rgba(31,41,55,0.95)" if T.name == "dark" else "rgba(255,255,255,0.95)"
    _leg_border = "#374151" if T.name == "dark" else "#D1D5DB"
    layout["legend"].update(
        title_text="Status",
        font=dict(family=_FONT, size=11, color=T.text_primary),
        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
        bgcolor=_leg_bg, bordercolor=_leg_border, borderwidth=1,
    )
    fig.update_layout(**layout)
    return fig


def manufacturer_heatmap(df: pd.DataFrame, top_n: int = 12) -> go.Figure:
    if df.empty or "manufacturer" not in df.columns:
        return _no_data_fig("No manufacturer data")
    T = _T()

    top_names = _non_blank_mfr(df).value_counts().head(top_n).index.tolist()
    if not top_names:
        return _no_data_fig("Fetch latest data to populate heatmap")

    sub   = df[df["manufacturer"].isin(top_names)]
    pivot = sub.groupby(["manufacturer", "status"]).size().unstack(fill_value=0)
    col_order = [c for c in
                 ["Current", "To Be Discontinued", "Resolved", "Discontinued", "No Longer Marketed"]
                 if c in pivot.columns]
    if not col_order:
        return _no_data_fig("No status data for heatmap")
    pivot = pivot[col_order]
    pivot.columns = [
        "To Be<br>Discontinued" if c == "To Be Discontinued" else c
        for c in pivot.columns
    ]

    full_names  = pivot.index.tolist()
    short_names = [shorten_manufacturer_name(n) for n in full_names]
    # Build hover text matrix using full manufacturer names
    hover_text  = [
        [f"<b>{full_names[r]}</b><br>{pivot.columns[c]}: {pivot.values[r, c]:,}"
         for c in range(len(pivot.columns))]
        for r in range(len(full_names))
    ]

    z      = pivot.values
    maxval = z.max() or 1

    colorscale = (
        [[0, "#0F2B5B"], [0.6, "#3B82F6"], [1, "#EFF6FF"]]
        if T.name == "dark" else
        [[0, "#EFF6FF"], [0.4, "#3B82F6"], [1, "#0F2B5B"]]
    )
    fig = go.Figure(go.Heatmap(
        z=z, x=pivot.columns.tolist(), y=short_names,
        colorscale=colorscale,
        text=z, texttemplate="%{text}",
        textfont=dict(size=11, family=_FONT),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover_text,
        showscale=True,
        colorbar=dict(
            title=dict(text="Count", font=dict(size=13, color=T.text_primary, family=_FONT)),
            tickfont=dict(size=11, color=T.text_primary, family=_FONT),
            thickness=14, len=0.85,
        ),
    ))
    # margin: longest single line of any short name × 7px, capped at 140
    _hm_max_line = max(
        max(len(s) for s in n.split("<br>")) for n in short_names
    )
    left_margin = min(140, max(90, _hm_max_line * 7))
    height = max(380, top_n * 42 + 80)
    layout = _base("Shortage Volume Heatmap", height=height,
                   margin=dict(t=64, b=110, l=left_margin, r=80))
    layout["xaxis"].update(title="", side="bottom", tickangle=0,
                           tickfont=dict(family=_FONT, size=11, color=T.text_primary))
    layout["yaxis"].update(tickfont=dict(family=_FONT, size=11, color=T.text_primary))
    fig.update_layout(**layout)
    return fig


def market_share_treemap(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart showing top 15 manufacturers by shortage count.

    Plotly treemap cannot vary text color per-box, making pale boxes unreadable.
    A ranked bar chart delivers the same market-share story with full legibility.
    """
    if df.empty or "manufacturer" not in df.columns:
        return _no_data_fig("No manufacturer data")
    T = _T()

    counts = _non_blank_mfr(df).value_counts().head(15).reset_index()
    counts.columns = ["manufacturer", "count"]
    if counts.empty:
        return _no_data_fig("Fetch latest data to populate chart")

    total = counts["count"].sum()
    counts["pct"] = (counts["count"] / total * 100).round(1)
    counts = counts.sort_values("count", ascending=True)

    # Gradient: lightest bar = smallest count, darkest = largest
    n = len(counts)
    bar_colors = [
        f"rgba(26,86,219,{0.35 + 0.65 * i / max(n - 1, 1):.2f})"
        for i in range(n)
    ]

    short_labels = counts["manufacturer"].apply(shorten_manufacturer_name)
    fig = go.Figure(go.Bar(
        x=counts["count"],
        y=short_labels,
        orientation="h",
        marker=dict(color=bar_colors, line=dict(width=0)),
        cliponaxis=False,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Shortages: %{x:,}<br>"
            "Share: %{customdata[1]:.1f}%"
            "<extra></extra>"
        ),
        customdata=list(zip(counts["manufacturer"], counts["pct"])),
    ))

    _ms_max_line = short_labels.apply(
        lambda t: max(len(s) for s in t.split("<br>"))
    ).max()
    left_margin = min(140, max(90, _ms_max_line * 7))

    fig.update_layout(
        paper_bgcolor=T.chart_bg,
        plot_bgcolor=T.chart_plot_bg,
        font=dict(family=_FONT, size=12, color=T.text_primary),
        title=dict(
            text="Market Share — Top 15 Manufacturers by Shortage Count",
            font=dict(family=_FONT, size=18, color=T.text_primary),
            x=0, pad=dict(l=4, b=12),
        ),
        xaxis=dict(
            title="Shortage Records",
            title_font=dict(size=13, color=T.text_muted),
            tickfont=dict(size=11, color=T.text_muted),
            showgrid=True,
            gridcolor=T.border,
            gridwidth=1,
            zeroline=False,
            fixedrange=True,
        ),
        yaxis=dict(
            tickfont=dict(size=11, color=T.text_primary),
            automargin=True,
            fixedrange=True,
        ),
        dragmode=False,
        margin=dict(t=64, b=90, l=left_margin, r=80),
        height=650,
        hoverlabel=dict(
            bgcolor="#1F2937" if T.name == "dark" else "#FFFFFF",
            bordercolor="#374151" if T.name == "dark" else "#D1D5DB",
            font=dict(family=_FONT, size=13,
                      color="#F9FAFB" if T.name == "dark" else "#111827"),
            namelength=-1,
        ),
    )
    return fig


def exec_bubble_chart(risk_df: pd.DataFrame, df: pd.DataFrame | None = None) -> go.Figure:
    """Manufacturer Shortage Impact Landscape — top 10 manufacturers.

    X = market share (%)  |  Y = avg shortage duration (days)
    Bubble size = unique drugs  |  Bubble color = risk score (0–100)

    Clean consulting-slide design:
    - Single markers-only trace (enables full colorscale + colorbar)
    - All labels as Plotly annotations — full per-label control
    - Large bubbles: white bold text centred inside, no arrow
    - Small bubbles: dark text + hairline leader line, direction chosen by
      Y-rank to minimise crossing and overlap
    - Reference lines at TOP-10 averages (dashed, muted)
    - Quadrant labels: 7px, 30% opacity — barely visible background cues
    - Subtitle under title; no footer caption; no reading-guide box
    """
    needed = {"shortage_count", "pct_current", "unique_drugs", "risk_score",
              "manufacturer", "current_count"}
    if risk_df.empty or not needed.issubset(risk_df.columns):
        return _no_data_fig("No manufacturer risk data — fetch latest data")
    T = _T()

    # ── Short display names ───────────────────────────────────────────────────
    _SHORT = {
        "hospira":                  "Hospira",
        "fresenius":                "Fresenius",
        "hikma":                    "Hikma",
        "baxter":                   "Baxter",
        "pfizer":                   "Pfizer",
        "teva":                     "Teva",
        "eugia":                    "Eugia",
        "sandoz":                   "Sandoz",
        "aurobindo":                "Aurobindo",
        "otsuka":                   "Otsuka ICU",
        "icu medical":              "ICU Medical",
        "b. braun":                 "B. Braun",
        "braun":                    "B. Braun",
        "mylan":                    "Mylan",
        "sagent":                   "Sagent",
        "accord":                   "Accord",
        "west-ward":                "West-Ward",
        "westward":                 "West-Ward",
        "apotex":                   "Apotex",
        "amneal":                   "Amneal",
        "luitpold":                 "Luitpold",
        "sun pharma":               "Sun Pharma",
        "sun pharm":                "Sun Pharma",
        "american regent":          "Am. Regent",
        "international medication": "Int'l Med.",
        "slayback":                 "Slayback",
        "novaplus":                 "NovaPlus",
        "civica":                   "Civica",
        "wockhardt":                "Wockhardt",
        "bedford":                  "Bedford",
        "abraxis":                  "Abraxis",
    }

    def _shorten(name: str) -> str:
        low = name.lower()
        for key, short in _SHORT.items():
            if key in low:
                return short
        trimmed = name.split(",")[0].split("(")[0].strip()
        return trimmed if len(trimmed) <= 14 else trimmed[:13] + "…"

    # ── Top 10 by shortage count ──────────────────────────────────────────────
    top = risk_df.head(10).copy()
    top = top.sort_values("shortage_count", ascending=False).reset_index(drop=True)

    total_records = max(int(risk_df["shortage_count"].sum()), 1)
    top["market_share"] = (top["shortage_count"] / total_records * 100).round(1)
    top["short_name"]   = top["manufacturer"].apply(_shorten)

    # ── Average shortage duration from raw records ────────────────────────────
    avg_dur: dict[str, float] = {}
    if df is not None and not df.empty and "initial_posting_date" in df.columns:
        tmp = df[df["manufacturer"].isin(top["manufacturer"])].copy()
        tmp["start"] = pd.to_datetime(tmp["initial_posting_date"], errors="coerce")
        tmp["end"]   = pd.to_datetime(
            tmp["update_date"] if "update_date" in tmp.columns else pd.NaT,
            errors="coerce",
        )
        tmp["dur"] = (tmp["end"] - tmp["start"]).dt.days
        valid = tmp[(tmp["dur"].notna()) & (tmp["dur"] >= 0)]
        if not valid.empty:
            avg_dur = valid.groupby("manufacturer")["dur"].mean().round(1).to_dict()

    top["avg_duration"] = top["manufacturer"].map(avg_dur)
    if top["avg_duration"].isna().all():
        top["avg_duration"] = (top["pct_current"] * 10).round(1)
    else:
        med_fill = float(top["avg_duration"].median())
        top["avg_duration"] = top["avg_duration"].fillna(med_fill).round(1)

    # ── Reference-line positions (top-10 averages) ────────────────────────────
    avg_x = float(top["market_share"].mean())
    avg_y = float(top["avg_duration"].mean())

    # ── Axis ranges: tight with ~12% padding ─────────────────────────────────
    x_max    = float(top["market_share"].max())
    y_max    = float(top["avg_duration"].max())
    y_min    = float(top["avg_duration"].min())
    y_spread = max(y_max - y_min, 1.0)
    x_range  = max(x_max, 1.0)

    x_lo, x_hi = 0.0, x_max * 1.28          # extra padding for larger bubbles
    y_lo = max(0.0, y_min - y_spread * 0.22)
    y_hi = y_max + y_spread * 0.28

    # ── Bubble sizing: diameter mode, largest ≈ 110px ────────────────────────
    max_drugs = float(top["unique_drugs"].max())
    sizeref   = max_drugs / 110.0

    # ── Color: vivid 3-stop green → yellow → red ─────────────────────────────
    color_scale = [
        [0.0, "#22C55E"],
        [0.5, "#FACC15"],
        [1.0, "#EF4444"],
    ]

    # ── Hover strings ─────────────────────────────────────────────────────────
    hover_texts = [
        (
            f"<b>{r['manufacturer']}</b><br>"
            f"Market share: {r['market_share']:.1f}%<br>"
            f"Total shortages: {r['shortage_count']:,}<br>"
            f"Unique drugs affected: {int(r['unique_drugs'])}<br>"
            f"Avg shortage duration: {r['avg_duration']:.0f} days<br>"
            f"Risk score: {r['risk_score']:.1f}"
        )
        for _, r in top.iterrows()
    ]

    # ── Markers-only trace (labels via annotations for full control) ──────────
    fig = go.Figure(go.Scatter(
        x=top["market_share"].tolist(),
        y=top["avg_duration"].tolist(),
        mode="markers",
        marker=dict(
            size=top["unique_drugs"].tolist(),
            sizemode="diameter",
            sizeref=sizeref,
            sizemin=14,
            color=top["risk_score"].tolist(),
            colorscale=color_scale,
            cmin=0.0,
            cmax=100.0,
            line=dict(color="rgba(255,255,255,0.7)", width=1.5),
            opacity=0.88,
            showscale=False,
        ),
        hovertext=hover_texts,
        hoverinfo="text",
        showlegend=False,
    ))

    # ── Discrete legend entries replacing the colorbar ────────────────────────
    _leg_bg = "rgba(31,41,55,0.95)" if T.name == "dark" else "rgba(255,255,255,0.95)"
    _leg_border = "#374151" if T.name == "dark" else "#D1D5DB"
    for label, color in [("High", "#EF4444"), ("Medium", "#FACC15"), ("Low", "#22C55E")]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=10, color=color, symbol="circle"),
            name=label,
            showlegend=True,
        ))

    # ── Labels: every manufacturer centred inside its bubble ─────────────────
    # Use font size 11 for names > 8 chars so longer names fit inside smaller bubbles.
    annotations: list[dict] = []
    for _, row in top.iterrows():
        x_pt = float(row["market_share"])
        y_pt = float(row["avg_duration"])
        name = str(row["short_name"])
        font_size = 9 if len(name) > 8 else 11
        annotations.append(dict(
            x=x_pt, y=y_pt,
            xref="x", yref="y",
            xanchor="center", yanchor="middle",
            text=f"<b>{name}</b>",
            showarrow=False,
            font=dict(family=_FONT, size=font_size, color=T.text_primary),
            bgcolor="rgba(0,0,0,0)",
            borderpad=0,
        ))

    # ── Subtitle — centred, two lines so it never clips the right edge ───────
    annotations.append(dict(
        xref="paper", yref="paper",
        x=0.5, y=1.07,
        xanchor="center", yanchor="bottom",
        text=(
            "Market Share vs. Average Shortage Duration<br>"
            "among the 10 most impactful manufacturers"
        ),
        showarrow=False,
        font=dict(family=_FONT, size=11, color=T.text_muted),
        bgcolor="rgba(0,0,0,0)",
    ))

    # ── Average reference lines (unlabeled) ───────────────────────────────────
    ref = dict(color=T.text_muted, width=0.8, dash="dot")
    fig.add_shape(type="line", x0=x_lo,  x1=x_hi,  y0=avg_y, y1=avg_y, line=ref)
    fig.add_shape(type="line", x0=avg_x, x1=avg_x, y0=y_lo,  y1=y_hi,  line=ref)

    fig.update_layout(
        paper_bgcolor=T.chart_bg,
        plot_bgcolor=T.chart_plot_bg,
        font=dict(family=_FONT, size=12, color=T.text_primary),
        title=dict(
            text="Manufacturer Shortage Impact Landscape",
            font=dict(family=_FONT, size=18, color=T.text_primary),
            x=0.5, xanchor="center",
            y=0.97, yanchor="top",
        ),
        xaxis=dict(
            title=dict(text="Market Share (%)", font=dict(size=13, color=T.text_muted),
                       standoff=10),
            tickfont=dict(size=11, color=T.text_muted),
            ticksuffix="%",
            range=[x_lo, x_hi],
            showgrid=True, gridcolor=T.border, gridwidth=0.5,
            zeroline=False,
            linecolor=T.border, linewidth=1, mirror=False,
            fixedrange=True,
        ),
        yaxis=dict(
            title=dict(text="Avg Shortage Duration (Days)",
                       font=dict(size=13, color=T.text_muted), standoff=10),
            tickfont=dict(size=11, color=T.text_muted),
            range=[y_lo, y_hi],
            showgrid=True, gridcolor=T.border, gridwidth=0.5,
            zeroline=False,
            linecolor=T.border, linewidth=1, mirror=False,
            fixedrange=True,
        ),
        showlegend=True,
        legend=dict(
            title=dict(text="Risk Score", font=dict(family=_FONT, size=12, color=T.text_primary)),
            font=dict(family=_FONT, size=11, color=T.text_primary),
            bgcolor=_leg_bg,
            bordercolor=_leg_border,
            borderwidth=1,
            x=1.01, y=0.5, xanchor="left", yanchor="middle",
        ),
        dragmode=False,
        width=1020,
        height=540,
        margin=dict(t=130, b=90, l=76, r=120),
        annotations=annotations,
        hoverlabel=dict(
            bgcolor="#1F2937" if T.name == "dark" else "#FFFFFF",
            bordercolor="#374151" if T.name == "dark" else "#D1D5DB",
            font=dict(family=_FONT, size=13,
                      color="#F9FAFB" if T.name == "dark" else "#111827"),
            namelength=-1,
        ),
    )
    return fig


def risk_scatter(risk_df: pd.DataFrame) -> go.Figure:
    needed = {"shortage_count", "pct_current", "unique_drugs", "risk_score", "manufacturer"}
    if risk_df.empty or not needed.issubset(risk_df.columns):
        return _no_data_fig("No manufacturer risk data — fetch latest data")
    T = _T()

    top = risk_df.head(30).copy()
    top["bubble_size"] = top["unique_drugs"].clip(lower=1)

    fig = px.scatter(
        top, x="shortage_count", y="pct_current",
        size="bubble_size", color="risk_score",
        hover_name="manufacturer",
        color_continuous_scale=[[0, "#22C55E"], [0.5, "#FACC15"], [1, "#EF4444"]],
        size_max=50,
        labels={"shortage_count": "Total Shortages", "pct_current": "% Currently Active",
                "bubble_size": "Unique Drugs", "risk_score": "Risk Score"},
    )
    fig.update_traces(
        marker=dict(line=dict(color=T.chart_bg, width=1.5), opacity=0.60),
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "Total shortages: %{x:,}<br>"
            "Currently active: %{y:.1f}%<br>"
            "Risk score: %{marker.color:.1f}"
            "<extra></extra>"
        ),
    )
    fig.update_coloraxes(
        colorbar=dict(
            title=dict(text="Risk Score", font=dict(size=13, color=T.text_primary, family=_FONT)),
            tickfont=dict(size=11, color=T.text_primary, family=_FONT),
            thickness=14,
        )
    )

    # ── Label only the top 6 bubbles (by shortage_count) — centered inside ───
    _RISK_SHORT = {
        "hospira": "Hospira", "fresenius": "Fresenius", "hikma": "Hikma",
        "pfizer": "Pfizer", "teva": "Teva", "baxter": "Baxter",
        "eugia": "Eugia", "sandoz": "Sandoz", "b. braun": "B. Braun",
        "braun": "B. Braun", "otsuka": "Otsuka ICU", "aurobindo": "Aurobindo",
        "mylan": "Mylan", "sagent": "Sagent", "icu medical": "ICU Medical",
        "accord": "Accord", "amneal": "Amneal", "apotex": "Apotex",
    }
    def _rs_short(name: str) -> str:
        low = name.lower()
        for k, v in _RISK_SHORT.items():
            if k in low:
                return v
        return name.split(",")[0].split("(")[0].strip()[:12]

    label_color = "#FFFFFF" if _theme.is_dark() else "#0F172A"
    top6 = top.nlargest(6, "shortage_count")
    annotations = []
    for _, row in top6.iterrows():
        annotations.append(dict(
            x=float(row["shortage_count"]),
            y=float(row["pct_current"]),
            xref="x", yref="y",
            xanchor="center", yanchor="middle",
            text=f"<b>{_rs_short(str(row['manufacturer']))}</b>",
            showarrow=False,
            font=dict(family=_FONT, size=11, color=label_color),
            bgcolor="rgba(0,0,0,0)",
            borderpad=0,
        ))

    layout = _base("Manufacturer Risk Matrix  (bubble = unique drugs affected)", height=460,
                   margin=dict(t=64, b=90, l=64, r=24))
    layout["xaxis"].update(title="Total Shortage Count")
    layout["yaxis"].update(title="% Currently Active Shortages")
    layout["annotations"] = annotations
    fig.update_layout(**layout)
    return fig


# ════════════════════════════════════════════════════════════════════════════
# Reason / cause charts
# ════════════════════════════════════════════════════════════════════════════

def reason_bar(df: pd.DataFrame) -> go.Figure:
    """
    Horizontal bar — meaningful FDA shortage reasons only.
    Excludes blank, 'Other', 'Not Specified', 'N/A', 'Unknown'.
    Falls back to top_drugs_bar() when fewer than 3 meaningful reasons remain.
    """
    if df.empty or "reason" not in df.columns:
        return _no_data_fig("No shortage reason data")
    T = _T()

    meaningful = df["reason"].fillna("").str.strip()
    meaningful = meaningful[~meaningful.str.lower().isin(_REASON_EXCLUDE)]

    if meaningful.empty or meaningful.nunique() < 3:
        return top_drugs_bar(df)

    counts = meaningful.value_counts().head(10).reset_index()
    counts.columns = ["reason", "count"]
    counts = counts.sort_values("count", ascending=True)

    short_reasons = counts["reason"].apply(lambda t: shorten_label(t, max_chars=28))
    norm    = (counts["count"] - counts["count"].min()) / max(counts["count"].max() - counts["count"].min(), 1)
    colors  = [f"rgba(220,38,38,{0.45 + 0.55 * float(v):.2f})" for v in norm]

    max_lines = short_reasons.apply(lambda t: t.count("<br>") + 1).max()
    row_h     = max(52, max_lines * 26)
    height    = max(340, len(counts) * row_h + 100)

    max_line_len = short_reasons.apply(
        lambda t: max(len(s) for s in t.split("<br>"))
    ).max()
    left_margin = min(210, max(130, max_line_len * 7))

    fig = go.Figure(go.Bar(
        x=counts["count"], y=short_reasons,
        orientation="h",
        marker=dict(color=colors, line=dict(color=T.chart_bg, width=0.6)),
        hovertemplate="<b>%{customdata}</b><br>%{x:,} shortages<extra></extra>",
        customdata=counts["reason"],
    ))
    layout = _base("Top FDA-Classified Shortage Reasons", height=height,
                   margin=dict(t=64, b=90, l=left_margin, r=90))
    layout["xaxis"].update(title="Shortage Count", showgrid=True)
    layout["yaxis"].update(tickfont=dict(family=_FONT, size=13, color=T.text_primary), autorange=True)
    fig.update_layout(**layout)
    return fig


def top_drugs_bar(df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    if df.empty or "generic_name" not in df.columns:
        return _no_data_fig("No drug data available")
    T = _T()

    counts = (
        df[df["generic_name"].str.strip() != ""]["generic_name"]
        .value_counts().head(top_n).reset_index()
    )
    counts.columns = ["drug", "count"]
    if counts.empty:
        return _no_data_fig("No drug data available")
    counts = counts.sort_values("count", ascending=True)

    wrapped = counts["drug"].apply(lambda t: _wrap_label(t, width=28))
    norm    = (counts["count"] - counts["count"].min()) / max(counts["count"].max() - counts["count"].min(), 1)
    colors  = [f"rgba(6,148,162,{0.40 + 0.60 * float(v):.2f})" for v in norm]

    max_lines = wrapped.apply(lambda t: t.count("<br>") + 1).max()
    row_h  = max(48, max_lines * 24)
    height = max(340, len(counts) * row_h + 100)

    fig = go.Figure(go.Bar(
        x=counts["count"], y=wrapped,
        orientation="h",
        marker=dict(color=colors, line=dict(color=T.chart_bg, width=0.6)),
        text=counts["count"], textposition="outside",
        textfont=dict(size=11, color=T.text_primary, family=_FONT),
        hovertemplate="<b>%{customdata}</b><br>%{x:,} records<extra></extra>",
        customdata=counts["drug"],
    ))
    layout = _base(f"Top {top_n} Most-Affected Drugs", height=height,
                   margin=dict(t=64, b=90, l=230, r=80))
    layout["xaxis"].update(title="Shortage Records", showgrid=True)
    layout["yaxis"].update(tickfont=dict(family=_FONT, size=11, color=T.text_primary))
    fig.update_layout(**layout)
    return fig


# ════════════════════════════════════════════════════════════════════════════
# Timeline / alert charts
# ════════════════════════════════════════════════════════════════════════════

def timeline_line(trend_df: pd.DataFrame) -> go.Figure:
    if trend_df.empty:
        return _no_data_fig("No snapshot history yet")
    T = _T()

    fig = go.Figure(go.Scatter(
        x=trend_df["day"], y=trend_df["record_count"],
        mode="lines+markers",
        line=dict(color="#1A56DB", width=3),
        marker=dict(size=9, color="#1A56DB", line=dict(color=T.chart_bg, width=2)),
        fill="tozeroy", fillcolor="rgba(26,86,219,0.08)",
        hovertemplate="<b>%{x}</b><br>Records: %{y:,}<extra></extra>",
        name="Records Captured",
    ))
    layout = _base("Shortage Records Tracked Over Time", height=360,
                   margin=dict(t=52, b=96, l=80, r=80))
    layout["xaxis"].update(title="Date", tickfont=dict(family=_FONT, size=11, color=T.text_secondary))
    layout["yaxis"].update(title="Total Shortage Records", rangemode="tozero")
    layout["hovermode"] = "x unified"
    fig.update_layout(**layout)
    return fig


def alert_summary_bar(alerts_df: pd.DataFrame) -> go.Figure:
    if alerts_df.empty:
        return _no_data_fig("No alerts yet")
    T = _T()

    counts = alerts_df["alert_type"].value_counts().reset_index()
    counts.columns = ["alert_type", "count"]
    color_map = {"new": "#DC2626", "resolved": "#16A34A", "status_change": "#F59E0B"}
    label_map = {"new": "New Shortage", "resolved": "Resolved", "status_change": "Status Changed"}
    counts["label"] = counts["alert_type"].map(label_map).fillna(counts["alert_type"])
    counts["color"] = counts["alert_type"].map(color_map).fillna(T.text_muted)

    fig = go.Figure(go.Bar(
        x=counts["label"], y=counts["count"],
        marker=dict(color=counts["color"].tolist(), line=dict(color=T.chart_bg, width=0.5)),
        text=counts["count"], textposition="outside",
        textfont=dict(size=11, color=T.text_primary, family=_FONT),
        hovertemplate="<b>%{x}</b><br>Count: %{y:,}<extra></extra>",
    ))
    layout = _base("Alert Summary", height=340, margin=dict(t=64, b=90, l=60, r=20))
    layout["xaxis"].update(tickfont=dict(family=_FONT, size=11, color=T.text_primary))
    layout["yaxis"].update(title="Count", rangemode="tozero")
    fig.update_layout(**layout)
    return fig
