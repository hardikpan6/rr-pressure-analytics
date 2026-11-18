import altair as alt
import streamlit as st

from src import config as C
from src import state, ui

params = state.scope_params()
if not params[0] or not params[1]:
    ui.empty_state("Select at least one season and one competition type.")
    st.stop()
bat = state.compute_scope(params)["bat"]
elig = state.player_filter(bat[bat["eligible"]])
if elig.empty:
    ui.empty_state("No eligible batters in this scope.")
    st.stop()

with st.container(horizontal=True, gap="small"):
    st.metric("Eligible batters", f"{len(elig):,}", border=True)
    st.metric("Median pressure SR", ui.fmt_num(elig["p_sr"].median()), border=True)
    st.metric("Median usual SR", ui.fmt_num(elig["u_sr"].median()), border=True)
    st.metric("Share improving under pressure", ui.fmt_num((elig["uplift"] > 0).mean() * 100, 0, "%"), border=True)
    st.metric("Median boundary %", ui.fmt_num(elig["p_bnd_pct"].median(), 1, "%"), border=True)

top_n = st.slider("Players in charts", 5, 30, 10, key="bat_topn")
top = elig.head(top_n)

c1, c2 = st.columns([1.1, 1], gap="medium")
with c1:
    with st.container(border=True):
        st.markdown("**Score composition - what drives each rating**")
        st.altair_chart(ui.component_bars(top, {
            f"Pressure SR ({C.BAT_WEIGHTS['sr']:.0%})": ("pct_sr", C.BAT_WEIGHTS["sr"]),
            f"SR uplift ({C.BAT_WEIGHTS['uplift']:.0%})": ("pct_uplift", C.BAT_WEIGHTS["uplift"]),
            f"Boundary % ({C.BAT_WEIGHTS['boundary']:.0%})": ("pct_boundary", C.BAT_WEIGHTS["boundary"]),
        }, height=max(300, 30 * len(top) + 40)))
with c2:
    with st.container(border=True):
        st.markdown("**Strike rate vs sample size**")
        st.caption("Larger samples sit further right; dashed line = eligible median pressure SR.")
        base = alt.Chart(elig).mark_circle(opacity=0.7, color=ui.PINK).encode(
            x=alt.X("p_balls:Q", title="Pressure balls faced", scale=alt.Scale(type="log")),
            y=alt.Y("p_sr:Q", title="Pressure strike rate", scale=alt.Scale(zero=False)),
            size=alt.Size("p_matches:Q", legend=None, scale=alt.Scale(range=[30, 400])),
            tooltip=["display_name", "team", alt.Tooltip("p_sr:Q", format=".1f"), "p_balls", "p_matches", alt.Tooltip("score:Q", format=".1f")])
        med = alt.Chart(elig).mark_rule(strokeDash=[5, 4], color=ui.MUTED).encode(y="median(p_sr):Q")
        st.altair_chart((base + med).properties(height=max(300, 30 * len(top) + 40)).interactive())

c3, c4 = st.columns(2, gap="medium")
with c3:
    with st.container(border=True):
        st.markdown("**Boundary-ball % vs pressure SR**")
        ch = alt.Chart(elig).mark_circle(opacity=0.75).encode(
            x=alt.X("p_bnd_pct:Q", title="Boundary balls (% of balls faced)", scale=alt.Scale(zero=False)),
            y=alt.Y("p_sr:Q", title="Pressure strike rate", scale=alt.Scale(zero=False)),
            color=alt.Color("score:Q", title="Score", scale=alt.Scale(scheme="plasma")),
            tooltip=["display_name", alt.Tooltip("p_bnd_pct:Q", format=".1f"), alt.Tooltip("p_sr:Q", format=".1f"), alt.Tooltip("score:Q", format=".1f")])
        st.altair_chart(ch.properties(height=320).interactive())
with c4:
    with st.container(border=True):
        st.markdown("**Match consistency - kept pace in pressure innings**")
        st.caption(f"Share of pressure innings (>= {C.CONSISTENCY_MIN_BAT_BALLS} balls) at SR >= {C.CONSISTENCY_BAT_SR:g}.")
        cons = top.dropna(subset=["consistency"])
        st.altair_chart(alt.Chart(cons).mark_bar(cornerRadius=3, color=ui.BLUE).encode(
            x=alt.X("consistency:Q", title="Kept pace %", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("display_name:N", sort="-x", title=None),
            tooltip=["display_name", alt.Tooltip("consistency:Q", format=".0f"), "kept_pace", "qual_innings"]).properties(height=max(320, 24 * len(cons))))

with st.container(border=True):
    st.markdown("**All eligible batters - full metric table**")
    cfg = dict(ui.BAT_VIEW)
    cfg.update({
        "o_sr": ui.CC.NumberColumn("Overall SR", format="%.1f"),
        "p_fours": ui.CC.NumberColumn("4s", format="%d"),
        "p_sixes": ui.CC.NumberColumn("6s", format="%d"),
        "p_dot_pct": ui.CC.NumberColumn("Dot %", format="%.1f%%"),
        "pressure_share": ui.CC.NumberColumn("Pressure share", format="%.0f%%", help="Pressure balls / all balls faced in scope."),
        "match_sr_sd": ui.CC.NumberColumn("Match SR sd", format="%.0f", help="Std-dev of match pressure SR (lower = steadier)."),
        "best_pressure_innings": ui.CC.NumberColumn("Best (pressure runs)", format="%d"),
        "pressure_wins": ui.CC.NumberColumn("Pressure chases won", format="%d"),
    })
    order = ["rank", "display_name", "team", "role", "score", "p_runs", "p_balls", "p_sr", "u_sr", "o_sr", "uplift",
             "p_bnd_pct", "p_fours", "p_sixes", "p_dot_pct", "p_outs", "p_avg", "p_matches", "consistency", "match_sr_sd",
             "best_pressure_innings", "pressure_wins", "pressure_share", "status"]
    ui.show_table(elig, {c: cfg[c] for c in order if c in cfg}, key="bat_full", height=480)
    ui.download_csv(elig, "rr_batting_pressure_eligible.csv", key="dl_bat_full")
