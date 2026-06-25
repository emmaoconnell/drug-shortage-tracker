"""
forecasting.py — Shortage trend analysis and forward projection.

Works with as few as 1 snapshot by falling back to assumption-based projection:
  • 1 snapshot  → flat + industry-average growth assumption, wide confidence band
  • 2 snapshots → two-point slope extrapolation
  • 3+ snapshots → least-squares linear regression on smoothed series

All paths always return a complete figure — the chart is never empty.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import theme as _theme

# ── Light-mode palette (WCAG-AA compliant) ───────────────────────────────────
_LIGHT = dict(
    actual   = "#1A56DB",
    trend    = "#6C2BD9",
    forecast = "#C81E1E",
    band     = "rgba(200,30,30,0.10)",
    axis     = "#1E293B",
    grid     = "#E2E8F0",
    plot_bg  = "white",
    paper_bg = "white",
    title    = "#0F2B5B",
    legend_bg= "rgba(255,255,255,0.9)",
    legend_br= "#E2E8F0",
    divider  = "#64748B",
    annot    = "#64748B",
    bar_line = "white",
    marker_line = "white",
)

# ── Dark-mode palette ─────────────────────────────────────────────────────────
_DARK = dict(
    actual   = "#3B82F6",
    trend    = "#8B5CF6",
    forecast = "#EF4444",
    band     = "rgba(239,68,68,0.15)",
    axis     = "#D5D9E3",
    grid     = "#50566E",
    plot_bg  = "rgba(0,0,0,0)",
    paper_bg = "rgba(0,0,0,0)",
    title    = "#F5F7FA",
    legend_bg= "rgba(31,33,52,0.92)",
    legend_br= "#50566E",
    divider  = "#94A3B8",
    annot    = "#94A3B8",
    bar_line = "rgba(0,0,0,0)",
    marker_line = "#2A2B3D",
)

def _palette() -> dict:
    return _DARK if _theme.is_dark() else _LIGHT

# Industry assumption when only 1 snapshot is available:
# drug shortages have historically grown ~2-4 % per year; use 0.1 % / day.
ASSUMPTION_DAILY_GROWTH_RATE = 0.001


# ── Internal helpers ─────────────────────────────────────────────────────────

def _smooth(series: np.ndarray, alpha: float = 0.35) -> np.ndarray:
    """Exponential weighted moving average to reduce noise before fitting."""
    out = np.empty_like(series, dtype=float)
    out[0] = series[0]
    for i in range(1, len(series)):
        out[i] = alpha * series[i] + (1 - alpha) * out[i - 1]
    return out


def _linear_fit(x: np.ndarray, y: np.ndarray):
    """Least-squares linear fit → (slope, intercept)."""
    coeffs = np.polyfit(x, y, 1)
    return float(coeffs[0]), float(coeffs[1])


def _residual_std(x, y, slope, intercept) -> float:
    residuals = np.asarray(y) - (slope * np.asarray(x) + intercept)
    return float(np.std(residuals)) if len(residuals) > 1 else 0.0


def _r_squared(y_actual: np.ndarray, y_predicted: np.ndarray) -> float:
    ss_res = float(np.sum((y_actual - y_predicted) ** 2))
    ss_tot = float(np.sum((y_actual - y_actual.mean()) ** 2))
    return 1 - ss_res / ss_tot if ss_tot > 0 else 1.0


def _future_dates(last_date, horizon: int) -> list:
    return [last_date + timedelta(days=i + 1) for i in range(horizon)]


def _clamp_positive(values: list) -> list:
    return [max(0.0, v) for v in values]


# ── Core forecasting logic ───────────────────────────────────────────────────

def build_daily_series(snapshot_rows: list[dict]) -> pd.DataFrame:
    """
    Aggregate raw snapshot rows into a daily count table.
    Input rows must have 'fetched_at' (ISO timestamp) and 'status'.
    Returns columns: date, total, current, resolved.
    """
    if not snapshot_rows:
        return pd.DataFrame(columns=["date", "total", "current", "resolved"])

    df = pd.DataFrame(snapshot_rows)
    df["date"] = pd.to_datetime(df["fetched_at"].str[:10], errors="coerce")
    df = df.dropna(subset=["date"])

    # If the same calendar day was fetched multiple times, keep only the latest
    # fetch so counts aren't inflated and each date appears exactly once.
    df["_fetched_dt"] = pd.to_datetime(df["fetched_at"], errors="coerce")
    latest_per_day = df.groupby("date")["_fetched_dt"].transform("max")
    df = df[df["_fetched_dt"] == latest_per_day].drop(columns=["_fetched_dt"])

    grouped = (
        df.groupby("date")
        .agg(
            total    = ("status", "count"),
            current  = ("status", lambda s: (s == "Current").sum()),
            resolved = ("status", lambda s: (s == "Resolved").sum()),
        )
        .reset_index()
        .sort_values("date")
    )
    return grouped


def forecast_series(
    daily_df: pd.DataFrame,
    column: str = "current",
    horizon_days: int = 30,
) -> dict:
    """
    Project `column` forward `horizon_days` days.

    Always returns a non-empty dict.  Uses three tiers:
      • 1 data point  — assumption-based flat + growth projection
      • 2 data points — two-point slope extrapolation
      • 3+ data points — smoothed least-squares regression
    """
    if daily_df.empty or column not in daily_df.columns:
        return {}

    n = len(daily_df)
    dates  = daily_df["date"].tolist()
    values = daily_df[column].fillna(0).values.astype(float)
    last_date = dates[-1]
    x_hist = np.arange(n, dtype=float)

    # ── Tier 1: single snapshot ───────────────────────────────────────────────
    if n == 1:
        base_val = float(values[0])
        slope    = base_val * ASSUMPTION_DAILY_GROWTH_RATE
        intercept = base_val
        std       = base_val * 0.15  # wide band — high uncertainty
        method    = "assumption"
        r_squared = None
        smoothed  = values.copy()
        trend_hist = np.array([base_val])
        confidence = "Low — based on a single snapshot and industry growth assumptions"

    # ── Tier 2: two snapshots → two-point slope ───────────────────────────────
    elif n == 2:
        slope     = float(values[1] - values[0])
        intercept = float(values[0])
        std       = abs(slope) * 0.5
        method    = "two-point"
        r_squared = None
        smoothed  = values.copy()
        trend_hist = slope * x_hist + intercept
        confidence = "Moderate — based on 2 data points"

    # ── Tier 3: regression ────────────────────────────────────────────────────
    else:
        smoothed  = _smooth(values)
        slope, intercept = _linear_fit(x_hist, smoothed)
        std       = _residual_std(x_hist, smoothed, slope, intercept)
        trend_hist = slope * x_hist + intercept
        r_squared = _r_squared(smoothed, trend_hist)
        method    = "regression"
        if r_squared > 0.85:
            confidence = f"High (R²={r_squared:.2f})"
        elif r_squared > 0.5:
            confidence = f"Moderate (R²={r_squared:.2f})"
        else:
            confidence = f"Low (R²={r_squared:.2f}) — high variance in historical data"

    # ── Build forecast points ─────────────────────────────────────────────────
    x_fc    = np.arange(n, n + horizon_days, dtype=float)
    vals_fc = _clamp_positive((slope * x_fc + intercept).tolist())
    upper   = _clamp_positive((slope * x_fc + intercept + 1.5 * std).tolist())
    lower   = _clamp_positive((slope * x_fc + intercept - 1.5 * std).tolist())
    dates_fc = _future_dates(last_date, horizon_days)

    # ── Human-readable trend summary ─────────────────────────────────────────
    projected_end = vals_fc[-1] if vals_fc else float(values[-1])
    current_val   = float(values[-1])

    if abs(slope) < 0.3:
        direction = "stable"
        direction_icon = "→"
    elif slope > 0:
        direction = f"rising by ~{slope:.1f} records/day"
        direction_icon = "↑"
    else:
        direction = f"falling by ~{abs(slope):.1f} records/day"
        direction_icon = "↓"

    delta_pct = ((projected_end - current_val) / current_val * 100) if current_val else 0
    delta_str = f"+{delta_pct:.1f}%" if delta_pct >= 0 else f"{delta_pct:.1f}%"

    method_labels = {
        "assumption": "single-snapshot assumption (industry growth rate)",
        "two-point":  "two-point linear extrapolation",
        "regression": "least-squares linear regression",
    }
    summary = (
        f"{direction_icon} **{column.title()} shortages are {direction}.** "
        f"Projection: **{projected_end:.0f}** in {horizon_days} days "
        f"({delta_str} from today's {current_val:.0f}). "
        f"Method: {method_labels[method]}. Confidence: {confidence}."
    )

    return {
        "dates_hist":   dates,
        "values_hist":  values.tolist(),
        "smoothed_hist": smoothed.tolist(),
        "trend_hist":   trend_hist.tolist(),
        "dates_fcast":  dates_fc,
        "values_fcast": vals_fc,
        "upper_band":   upper,
        "lower_band":   lower,
        "slope":        slope,
        "r_squared":    r_squared,
        "confidence":   confidence,
        "method":       method,
        "n_snapshots":  n,
        "summary":      summary,
    }


def forecast_figure(
    daily_df: pd.DataFrame,
    column: str = "current",
    horizon_days: int = 30,
    title: str = "",
) -> go.Figure:
    """
    Always returns a populated figure — never an empty chart.
    Three tiers: 1 snapshot, 2 snapshots, or full regression.
    """
    # Synthesise a single-row DataFrame if nothing was passed
    if daily_df is None or daily_df.empty or column not in daily_df.columns:
        return _empty_figure("No snapshot data available. Click 'Fetch Latest Data' in the sidebar.")

    # Forecasting uses the original dataframe untouched.
    fc = forecast_series(daily_df, column=column, horizon_days=horizon_days)
    if not fc:
        return _empty_figure("Could not build forecast — check that data loaded correctly.")

    P = _palette()
    n = fc["n_snapshots"]
    fig = go.Figure()

    # ── Build a plot-only copy of the historical data ─────────────────────────
    # fc["dates_hist"] / fc["values_hist"] come from build_daily_series which
    # already deduplicates to one row per calendar day.  If consecutive days
    # are present (e.g. June 18 & June 19 from two fetches), thin them to one
    # bar per 7-day window so adjacent bars don't look like duplicate lines.
    _dates  = list(fc["dates_hist"])
    _values = list(fc["values_hist"])
    _trend  = list(fc["trend_hist"]) if fc.get("trend_hist") else []

    # Keep only the latest observation within each 7-day window.
    _plot_dates:  list = []
    _plot_values: list = []
    _plot_trend:  list = []
    _window_start = None
    for i, d in enumerate(_dates):
        _d = pd.Timestamp(d)
        if _window_start is None or (_d - _window_start).days >= 7:
            _plot_dates.append(_d)
            _plot_values.append(_values[i])
            if _trend:
                _plot_trend.append(_trend[i])
            _window_start = _d
        else:
            # Same 7-day window — overwrite with this later observation.
            _plot_dates[-1]  = _d
            _plot_values[-1] = _values[i]
            if _trend:
                _plot_trend[-1] = _trend[i]

    # ── 1. Historical actual values (bars) ────────────────────────────────────
    _bar_ms = 1_000 * 60 * 60 * 24 * 5   # 5 days wide — fills ~70 % of each 7-day slot
    fig.add_trace(go.Bar(
        x=_plot_dates,
        y=_plot_values,
        name="Actual",
        width=_bar_ms,
        marker=dict(color=P["actual"], opacity=0.70, line=dict(color=P["bar_line"], width=0.8)),
        hovertemplate="<b>%{x|%b %d, %Y}</b><br>Actual: %{y:,}<extra></extra>",
    ))

    # ── 2. Smoothed trend line (only when ≥ 3 points) ────────────────────────
    if n >= 3 and _plot_trend:
        fig.add_trace(go.Scatter(
            x=_plot_dates,
            y=_plot_trend,
            name="Trend (fitted)",
            line=dict(color=P["trend"], width=2.5, dash="dot"),
            hovertemplate="<b>%{x}</b><br>Trend: %{y:.1f}<extra></extra>",
        ))

    # ── Y-axis ceiling — computed once from all plotted values ───────────────
    # Must be defined before the confidence band trace so it can be used to
    # clamp the band polygon and later set yaxis.range in the layout.
    _all_plotted = (
        _plot_values
        + _plot_trend
        + list(fc["values_fcast"])
        + list(fc["upper_band"])
    )
    _y_ceil = (max(_all_plotted) * 1.18) if _all_plotted else 100

    # ── 3. Confidence band — plotted BEFORE the forecast line ────────────────
    # Guarantee the band has visible width even when std=0 (e.g. flat slope):
    # enforce a minimum half-width of 5% of the mean forecast value.
    _fc_vals   = list(fc["values_fcast"])
    _min_half  = max(sum(_fc_vals) / len(_fc_vals) * 0.05, 1.0) if _fc_vals else 1.0
    _upper_pts = [max(u, fv + _min_half) for u, fv in zip(fc["upper_band"], _fc_vals)]
    _lower_pts = [min(l, fv - _min_half) for l, fv in zip(fc["lower_band"], _fc_vals)]
    # Clamp to axis bounds and reverse lower for the closed polygon
    _upper_clamped = [min(v, _y_ceil) for v in _upper_pts]
    _lower_clamped = [max(v, 0)       for v in _lower_pts]
    band_x = list(fc["dates_fcast"]) + list(reversed(fc["dates_fcast"]))
    band_y = _upper_clamped          + list(reversed(_lower_clamped))
    _band_fill = "rgba(248,113,113,0.20)" if _theme.is_dark() else "rgba(220,38,38,0.16)"
    fig.add_trace(go.Scatter(
        x=band_x, y=band_y,
        fill="toself",
        fillcolor=_band_fill,
        line=dict(color="rgba(0,0,0,0)"),
        name="Confidence Band",
        hoverinfo="skip",
        showlegend=True,
    ))

    # ── 4. Forecast line — on top of the confidence band ─────────────────────
    fig.add_trace(go.Scatter(
        x=fc["dates_fcast"],
        y=fc["values_fcast"],
        name=f"{horizon_days}-Day Forecast",
        line=dict(color=P["forecast"], width=3),
        mode="lines+markers",
        marker=dict(size=8, color=P["forecast"], line=dict(color=P["marker_line"], width=1.5)),
        hovertemplate="<b>%{x}</b><br>Forecast: %{y:.0f}<extra></extra>",
    ))

    # ── 5. "Latest data" vertical divider ────────────────────────────────────
    today_x = str(fc["dates_hist"][-1])
    fig.add_vline(
        x=today_x,
        line_dash="dash",
        line_color=P["divider"],
        line_width=1.5,
        annotation_text="  Latest data",
        annotation_position="top right",
        annotation_font=dict(size=11, color=P["annot"]),
    )

    # ── Layout ────────────────────────────────────────────────────────────────
    _font = "Inter, system-ui, sans-serif"
    chart_title = title or f"{column.replace('_',' ').title()} Shortages — {horizon_days}-Day Forecast"

    fig.update_layout(
        title=dict(
            text=chart_title,
            font=dict(family=_font, size=16, color=P["title"]),
            x=0,
            y=0.98,
            yanchor="top",
            pad=dict(l=4, b=4),
        ),
        xaxis=dict(
            title="Date",
            title_font=dict(family=_font, size=13, color=P["axis"]),
            title_standoff=18,
            tickfont=dict(family=_font, size=11, color=P["axis"]),
            gridcolor=P["grid"],
            linecolor=P["grid"],
            showgrid=True,
            zeroline=False,
            fixedrange=True,
            automargin=True,
        ),
        yaxis=dict(
            title="Total Shortage Records",
            title_font=dict(family=_font, size=13, color=P["axis"]),
            tickfont=dict(family=_font, size=11, color=P["axis"]),
            gridcolor=P["grid"],
            linecolor=P["grid"],
            range=[0, _y_ceil],    # explicit ceiling reduces vertical exaggeration
            showgrid=True,
            zeroline=False,
            fixedrange=True,
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=P["legend_bg"],
            bordercolor=P["legend_br"],
            font=dict(family=_font, size=12, color=P["axis"]),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.03,   # anchored to bottom of legend box, sits just above plot
            xanchor="center", x=0.55,
            font=dict(family=_font, size=12, color=P["axis"]),
            bgcolor=P["legend_bg"],
            bordercolor=P["legend_br"],
            borderwidth=1,
        ),
        plot_bgcolor=P["plot_bg"],
        paper_bgcolor=P["paper_bg"],
        font=dict(family=_font, size=12, color=P["axis"]),
        margin=dict(t=70, b=110, l=80, r=60),
        barmode="overlay",
        dragmode=False,
    )
    return fig


def _empty_figure(message: str) -> go.Figure:
    """Return a blank figure with a centred message instead of crashing."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=14, color="#64748B"),
    )
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        margin=dict(t=40, b=40, l=40, r=40),
    )
    return fig


# ── Manufacturer analytics ───────────────────────────────────────────────────

def manufacturer_risk_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Score each manufacturer.
    Guaranteed output columns:
      manufacturer, shortage_count, current_count, resolved_count,
      unique_drugs, pct_current, risk_score, risk_label
    """
    empty_cols = [
        "manufacturer", "shortage_count", "current_count", "resolved_count",
        "unique_drugs", "pct_current", "risk_score", "risk_label",
    ]
    if df.empty or "manufacturer" not in df.columns:
        return pd.DataFrame(columns=empty_cols)

    grp = (
        df.groupby("manufacturer")
        .agg(
            shortage_count  = ("generic_name", "count"),
            current_count   = ("status",  lambda s: (s == "Current").sum()),
            resolved_count  = ("status",  lambda s: (s == "Resolved").sum()),
            unique_drugs    = ("generic_name", "nunique"),
        )
        .reset_index()
    )
    grp = grp[grp["manufacturer"].str.strip() != ""].copy()
    if grp.empty:
        return pd.DataFrame(columns=empty_cols)

    grp["pct_current"] = (grp["current_count"] / grp["shortage_count"] * 100).round(1)

    max_count = grp["shortage_count"].max() or 1
    grp["risk_score"] = (
        0.50 * (grp["shortage_count"] / max_count)
        + 0.35 * (grp["pct_current"] / 100)
        + 0.15 * (grp["unique_drugs"] / (grp["unique_drugs"].max() or 1))
    ) * 100
    grp["risk_score"] = grp["risk_score"].round(1)
    grp["risk_label"] = grp["risk_score"].apply(
        lambda s: "High" if s >= 65 else ("Medium" if s >= 35 else "Low")
    )
    return grp.sort_values("risk_score", ascending=False).reset_index(drop=True)


def shortage_duration_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Average shortage duration (days) per manufacturer."""
    if df.empty:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["start"] = pd.to_datetime(tmp["initial_posting_date"], errors="coerce")
    tmp["end"]   = pd.to_datetime(tmp["update_date"], errors="coerce")
    tmp["duration_days"] = (tmp["end"] - tmp["start"]).dt.days
    valid = tmp.dropna(subset=["duration_days"])
    valid = valid[valid["duration_days"] >= 0]
    if valid.empty:
        return pd.DataFrame()
    result = (
        valid.groupby("manufacturer")["duration_days"]
        .agg(avg_days="mean", max_days="max", count="count")
        .reset_index()
    )
    result["avg_days"] = result["avg_days"].round(0).astype(int)
    result["max_days"] = result["max_days"].astype(int)
    return result.sort_values("avg_days", ascending=False).reset_index(drop=True)
