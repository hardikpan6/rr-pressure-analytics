"""Reusable presentation helpers: charts, table configs, exports, light CSS."""

from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

PINK = "#EA1A85"
BLUE = "#4F8BFF"
GOLD = "#F2C94C"
GREEN = "#2ED39A"
RED = "#FF5470"
MUTED = "#8A94B3"


def inject_css() -> None:
    # Only motion/hover polish that native theming cannot provide (explicitly requested).
    st.html(
        """
        <style>
        @keyframes rrFade {from {opacity:0; transform:translateY(6px);} to {opacity:1; transform:none;}}
        [data-testid="stMainBlockContainer"] {animation: rrFade .35s ease-out;}
        [data-testid="stMetric"], [data-testid="stVerticalBlockBorderWrapper"] {
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;}
        [data-testid="stMetric"]:hover {transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(234,26,133,.18); border-color: rgba(234,26,133,.55);}
        [data-testid="stMetricValue"] {font-weight: 800; letter-spacing: -.02em;}
        [data-testid="stMetricLabel"] p {text-transform: uppercase; font-size: .72rem; letter-spacing: .06em; opacity: .8;}
        [class*="st-key-rec-grid"] [data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: rgba(234,26,133,.55); box-shadow: 0 6px 20px rgba(234,26,133,.12);}
        </style>
        """
    )


def fmt_num(v, nd=1, suffix="") -> str:
    if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
        return "n/a"
    return f"{v:,.{nd}f}{suffix}"


def download_csv(df: pd.DataFrame, filename: str, key: str, label: str = "Download CSV") -> None:
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), file_name=filename,
                       mime="text/csv", key=key, icon=":material/download:", on_click="ignore")


def empty_state(msg: str = "No data for the current filters. Widen the season or competition selection, or press Reset filters.") -> None:
    st.info(msg, icon=":material/filter_alt_off:")


# --------------------------------------------------------------------------
# Column configurations
# --------------------------------------------------------------------------
CC = st.column_config
SCORE_COL = CC.ProgressColumn("Reliability score", min_value=0, max_value=100, format="%.1f",
                              help="Percentile-based index (0-100) among eligible players. Not a probability.")

BAT_VIEW = {
    "rank": CC.NumberColumn("Rank", format="%d", width="small"),
    "display_name": CC.TextColumn("Player", width="medium"),
    "team": CC.TextColumn("Team (pressure)"),
    "role": CC.TextColumn("Role"),
    "score": SCORE_COL,
    "p_runs": CC.NumberColumn("Pressure runs", format="%d"),
    "p_balls": CC.NumberColumn("Pressure balls", format="%d"),
    "p_sr": CC.NumberColumn("Pressure SR", format="%.1f"),
    "u_sr": CC.NumberColumn("Usual SR", format="%.1f", help="Strike rate on all non-pressure balls in scope."),
    "uplift": CC.NumberColumn("SR uplift", format="%+.1f", help="Pressure SR minus usual SR (unclipped)."),
    "p_bnd_pct": CC.NumberColumn("Boundary %", format="%.1f%%"),
    "p_matches": CC.NumberColumn("Matches", format="%d", help="Matches with at least one pressure ball faced."),
    "consistency": CC.NumberColumn("Kept pace %", format="%.0f%%",
                                   help="Share of pressure innings (>=5 balls) scored at SR >= 150."),
    "p_outs": CC.NumberColumn("Outs", format="%d"),
    "p_avg": CC.NumberColumn("Pressure avg", format="%.1f"),
    "top10_share": CC.ProgressColumn("Top-10 stability", min_value=0, max_value=100, format="%.0f%%",
                                     help="Share of 200 match-bootstrap resamples in which the player ranked top 10."),
    "status": CC.TextColumn("Eligibility"),
    "latest_ipl_squad": CC.TextColumn("Latest IPL squad", help="Franchise listed for the player in the most recent IPL season of competition_team_player_mapping.csv. Not an availability claim."),
}

BOWL_VIEW = {
    "rank": CC.NumberColumn("Rank", format="%d", width="small"),
    "display_name": CC.TextColumn("Player", width="medium"),
    "team": CC.TextColumn("Team (pressure)"),
    "role": CC.TextColumn("Role"),
    "score": SCORE_COL,
    "p_wkts": CC.NumberColumn("Pressure wkts", format="%d"),
    "p_legal": CC.NumberColumn("Pressure balls", format="%d", help="Legal deliveries bowled under pressure."),
    "p_econ": CC.NumberColumn("Pressure econ", format="%.2f"),
    "u_econ": CC.NumberColumn("Usual econ", format="%.2f"),
    "econ_improvement": CC.NumberColumn("Econ gain", format="%+.2f", help="Usual economy minus pressure economy. Positive = cheaper under pressure."),
    "p_wpb": CC.NumberColumn("Wkts / over", format="%.2f", help="Wickets per six legal balls."),
    "p_dot_pct": CC.NumberColumn("Dot %", format="%.1f%%"),
    "p_matches": CC.NumberColumn("Matches", format="%d"),
    "consistency": CC.NumberColumn("Held %", format="%.0f%%", help="Share of pressure spells (>=6 balls) at economy <= 9."),
    "top10_share": BAT_VIEW["top10_share"],
    "status": CC.TextColumn("Eligibility"),
    "latest_ipl_squad": BAT_VIEW["latest_ipl_squad"],
}


def show_table(df: pd.DataFrame, config: dict, key: str | None = None, height: int | str = "auto",
               selectable: bool = False):
    cols = [c for c in config if c in df.columns]
    kwargs = dict(hide_index=True, column_order=cols, column_config=config, height=height)
    if selectable:
        return st.dataframe(df[cols + ["player_id"]] if "player_id" in df else df[cols], key=key,
                            on_select="rerun", selection_mode="single-row", **kwargs)
    return st.dataframe(df[cols], key=key, **kwargs)


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------
def scatter_vs(df: pd.DataFrame, x: str, y: str, x_title: str, y_title: str, size: str,
               tooltip: list, better: str = "above", height: int = 430) -> alt.Chart:
    """Scatter with a y = x reference: points off the line changed under pressure."""
    df = df.dropna(subset=[x, y]).copy()
    if df.empty:
        return alt.Chart(pd.DataFrame({"x": []})).mark_point()
    diff = df[y] - df[x]
    df["trend"] = np.where(diff >= 0, "Improves under pressure", "Declines under pressure") if better == "above" \
        else np.where(diff <= 0, "Improves under pressure", "Declines under pressure")
    lo = float(min(df[x].min(), df[y].min())) * 0.95
    hi = float(max(df[x].max(), df[y].max())) * 1.03
    color = alt.Color("trend:N", title=None, scale=alt.Scale(domain=["Improves under pressure", "Declines under pressure"], range=[GREEN, RED]),
                      legend=alt.Legend(orient="bottom", columns=1, labelLimit=0))
    pts = alt.Chart(df).mark_circle(opacity=0.75, stroke="#070D1F", strokeWidth=0.5).encode(
        x=alt.X(f"{x}:Q", title=x_title, scale=alt.Scale(domain=[lo, hi], zero=False)),
        y=alt.Y(f"{y}:Q", title=y_title, scale=alt.Scale(domain=[lo, hi], zero=False)),
        size=alt.Size(f"{size}:Q", title="Pressure balls", scale=alt.Scale(range=[25, 500]), legend=None),
        color=color, tooltip=tooltip)
    line = alt.Chart(pd.DataFrame({"v": [lo, hi]})).mark_line(strokeDash=[5, 4], color=MUTED).encode(x="v:Q", y="v:Q")
    return (line + pts).properties(height=height).interactive()


def diverging_bars(df: pd.DataFrame, value: str, label: str, title: str, height: int = 380) -> alt.Chart:
    df = df.copy()
    df["dir"] = np.where(df[value] >= 0, "Better under pressure", "Worse under pressure")
    return alt.Chart(df).mark_bar(cornerRadius=3).encode(
        x=alt.X(f"{value}:Q", title=title),
        y=alt.Y("display_name:N", sort=alt.SortField(value, order="descending"), title=None,
                axis=alt.Axis(labelOverlap=False, labelLimit=170)),
        color=alt.Color("dir:N", scale=alt.Scale(domain=["Better under pressure", "Worse under pressure"], range=[GREEN, RED]), legend=None),
        tooltip=["display_name", alt.Tooltip(f"{value}:Q", format="+.2f", title=label), "team"],
    ).properties(height=max(height, 24 * len(df) + 30))


def component_bars(df: pd.DataFrame, comps: dict[str, tuple[str, float]], height: int = 360) -> alt.Chart:
    """Stacked weighted contributions to the reliability score."""
    rows = []
    for _, r in df.iterrows():
        for label, (col, w) in comps.items():
            rows.append({"Player": r["display_name"], "Component": label, "Points": r[col] * w, "Percentile": r[col]})
    long = pd.DataFrame(rows)
    order = df["display_name"].tolist()
    return alt.Chart(long).mark_bar().encode(
        x=alt.X("sum(Points):Q", title="Reliability score (weighted percentile points)", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("Player:N", sort=order, title=None, axis=alt.Axis(labelOverlap=False, labelLimit=160)),
        color=alt.Color("Component:N", legend=alt.Legend(orient="bottom", title=None, columns=3, labelLimit=200)),
        order=alt.Order("Component:N"),
        tooltip=["Player", "Component", alt.Tooltip("Percentile:Q", format=".1f"), alt.Tooltip("Points:Q", format=".1f")],
    ).properties(height=max(height, 30 * len(order) + 40))


def grouped_bars(long: pd.DataFrame, cat: str, value: str, series: str, title: str, height: int = 320,
                 fmt: str = ".1f", horizontal: bool = False) -> alt.Chart:
    enc_val = alt.X(f"{value}:Q", title=title) if horizontal else alt.Y(f"{value}:Q", title=title)
    enc_cat = alt.Y(f"{cat}:N", title=None, sort=None) if horizontal else alt.X(f"{cat}:N", title=None, sort=None, axis=alt.Axis(labelAngle=-30))
    off = alt.YOffset(f"{series}:N") if horizontal else alt.XOffset(f"{series}:N")
    return alt.Chart(long).mark_bar(cornerRadius=3).encode(
        enc_val, enc_cat, off,
        color=alt.Color(f"{series}:N", legend=alt.Legend(orient="bottom", title=None, labelLimit=0, columns=3),
                        scale=alt.Scale(range=[PINK, BLUE, GOLD, GREEN, "#A78BFA", "#FF9F43"])),
        tooltip=[cat, series, alt.Tooltip(f"{value}:Q", format=fmt)],
    ).properties(height=height)


def line_trend(long: pd.DataFrame, x: str, y: str, series: str, title: str, height: int = 300) -> alt.Chart:
    return alt.Chart(long).mark_line(point=True, strokeWidth=2.5).encode(
        x=alt.X(f"{x}:O", title=None),
        y=alt.Y(f"{y}:Q", title=title, scale=alt.Scale(zero=False)),
        color=alt.Color(f"{series}:N", legend=alt.Legend(orient="bottom", title=None), scale=alt.Scale(range=[PINK, BLUE])),
        tooltip=[x, series, alt.Tooltip(f"{y}:Q", format=".2f")],
    ).properties(height=height)
