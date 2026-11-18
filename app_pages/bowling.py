import altair as alt
import streamlit as st

from src import config as C
from src import state, ui

params = state.scope_params()
if not params[0] or not params[1]:
    ui.empty_state("Select at least one season and one competition type.")
    st.stop()
bowl = state.compute_scope(params)["bowl"]
elig = state.player_filter(bowl[bowl["eligible"]])
if elig.empty:
    ui.empty_state("No eligible bowlers in this scope.")
    st.stop()

with st.container(horizontal=True, gap="small"):
    st.metric("Eligible bowlers", f"{len(elig):,}", border=True)
    st.metric("Median pressure economy", ui.fmt_num(elig["p_econ"].median(), 2), border=True)
    st.metric("Median usual economy", ui.fmt_num(elig["u_econ"].median(), 2), border=True)
    st.metric("Share cheaper under pressure", ui.fmt_num((elig["econ_improvement"] > 0).mean() * 100, 0, "%"), border=True)
    st.metric("Median dot %", ui.fmt_num(elig["p_dot_pct"].median(), 1, "%"), border=True)

top_n = st.slider("Players in charts", 5, 30, 10, key="bowl_topn")
top = elig.head(top_n)

c1, c2 = st.columns([1.1, 1], gap="medium")
with c1:
    with st.container(border=True):
        st.markdown("**Score composition - what drives each rating**")
        st.altair_chart(ui.component_bars(top, {
            f"Economy, inverse ({C.BOWL_WEIGHTS['economy']:.0%})": ("pct_economy", C.BOWL_WEIGHTS["economy"]),
            f"Wickets per over ({C.BOWL_WEIGHTS['wkts']:.0%})": ("pct_wkts", C.BOWL_WEIGHTS["wkts"]),
            f"Dot-ball % ({C.BOWL_WEIGHTS['dots']:.0%})": ("pct_dots", C.BOWL_WEIGHTS["dots"]),
        }, height=max(300, 30 * len(top) + 40)))
with c2:
    with st.container(border=True):
        st.markdown("**Economy vs wicket rate under pressure**")
        st.caption("Bottom-right is best: cheap and taking wickets. Dashed lines = eligible medians.")
        pts = alt.Chart(elig).mark_circle(opacity=0.75).encode(
            x=alt.X("p_wpb:Q", title="Wickets per 6 legal balls"),
            y=alt.Y("p_econ:Q", title="Pressure economy", scale=alt.Scale(zero=False, reverse=False)),
            size=alt.Size("p_legal:Q", legend=None, scale=alt.Scale(range=[30, 450])),
            color=alt.Color("score:Q", title="Score", scale=alt.Scale(scheme="plasma")),
            tooltip=["display_name", "team", alt.Tooltip("p_econ:Q", format=".2f"), alt.Tooltip("p_wpb:Q", format=".2f"),
                     "p_wkts", "p_legal", alt.Tooltip("score:Q", format=".1f")])
        vx = alt.Chart(elig).mark_rule(strokeDash=[5, 4], color=ui.MUTED).encode(x="median(p_wpb):Q")
        hy = alt.Chart(elig).mark_rule(strokeDash=[5, 4], color=ui.MUTED).encode(y="median(p_econ):Q")
        st.altair_chart((pts + vx + hy).properties(height=max(300, 30 * len(top) + 40)).interactive())

c3, c4 = st.columns(2, gap="medium")
with c3:
    with st.container(border=True):
        st.markdown("**Dot-ball % under pressure**")
        st.altair_chart(alt.Chart(top).mark_bar(cornerRadius=3, color=ui.PINK).encode(
            x=alt.X("p_dot_pct:Q", title="Dot balls (% of legal balls)"),
            y=alt.Y("display_name:N", sort="-x", title=None),
            tooltip=["display_name", alt.Tooltip("p_dot_pct:Q", format=".1f"), "p_dots", "p_legal"]).properties(height=max(320, 24 * len(top))))
with c4:
    with st.container(border=True):
        st.markdown("**Match consistency - spells held under 9 an over**")
        st.caption(f"Share of pressure spells (>= {C.CONSISTENCY_MIN_BOWL_BALLS} legal balls) at economy <= {C.CONSISTENCY_BOWL_ECON:g}.")
        cons = top.dropna(subset=["consistency"])
        st.altair_chart(alt.Chart(cons).mark_bar(cornerRadius=3, color=ui.BLUE).encode(
            x=alt.X("consistency:Q", title="Held %", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("display_name:N", sort="-x", title=None),
            tooltip=["display_name", alt.Tooltip("consistency:Q", format=".0f"), "held", "qual_spells"]).properties(height=max(320, 24 * len(cons))))

with st.container(border=True):
    st.markdown("**All eligible bowlers - full metric table**")
    cfg = dict(ui.BOWL_VIEW)
    cfg.update({
        "o_econ": ui.CC.NumberColumn("Overall econ", format="%.2f"),
        "p_bsr": ui.CC.NumberColumn("Balls / wkt", format="%.1f"),
        "p_avg": ui.CC.NumberColumn("Pressure avg", format="%.1f"),
        "p_bnd_pct": ui.CC.NumberColumn("Boundary % conceded", format="%.1f%%"),
        "p_wides": ui.CC.NumberColumn("Wides", format="%d"),
        "p_noballs": ui.CC.NumberColumn("No-balls", format="%d"),
        "wicket_spells": ui.CC.NumberColumn("Spells with wkt", format="%d"),
        "match_econ_sd": ui.CC.NumberColumn("Match econ sd", format="%.2f"),
        "pressure_wins": ui.CC.NumberColumn("Pressure defences won", format="%d"),
    })
    order = ["rank", "display_name", "team", "role", "score", "p_wkts", "p_legal", "p_econ", "u_econ", "o_econ",
             "econ_improvement", "p_wpb", "p_bsr", "p_avg", "p_dot_pct", "p_bnd_pct", "p_wides", "p_noballs", "p_matches",
             "consistency", "wicket_spells", "match_econ_sd", "pressure_wins", "status"]
    ui.show_table(elig, {c: cfg[c] for c in order if c in cfg}, key="bowl_full", height=480)
    ui.download_csv(elig, "rr_bowling_pressure_eligible.csv", key="dl_bowl_full")
