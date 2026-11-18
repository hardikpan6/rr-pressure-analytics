import streamlit as st

from src import config as C
from src import state, ui

ds = state.get_dataset()
params = state.scope_params()
if not params[0] or not params[1]:
    ui.empty_state("Select at least one season and one competition type.")
    st.stop()
S = state.compute_scope(params)
k = S["kpis"]

st.markdown("##### Which players can be trusted when the match is under maximum pressure?")
st.caption("Every number below is recomputed from the raw ball-by-ball file for the current filter scope.")

if k["deliveries"] == 0:
    ui.empty_state()
    st.stop()

top_bat, top_bowl = k["top_bat"], k["top_bowl"]
with st.container(horizontal=True, gap="small"):
    st.metric("Players analysed", f"{k['players']:,}", border=True, help="Distinct batters, non-strikers and bowlers in scope.")
    st.metric("Matches analysed", f"{k['matches']:,}", border=True, help="Matches with ball-by-ball data in scope.")
    st.metric("Pressure deliveries", f"{k['pressure_deliveries']:,}",
              delta=f"{k['pressure_deliveries'] / k['deliveries'] * 100:.1f}% of all deliveries", delta_color="off", delta_arrow="off", border=True)
    st.metric("Competitions", f"{k['competitions']:,}", border=True)
with st.container(horizontal=True, gap="small"):
    st.metric("Eligible batters", f"{k['elig_bat']:,}", delta=f">= {params[5]} balls, >= {params[6]} matches", delta_color="off", delta_arrow="off", border=True)
    st.metric("Eligible bowlers", f"{k['elig_bowl']:,}", delta=f">= {params[5]} balls, >= {params[6]} matches", delta_color="off", delta_arrow="off", border=True)
    st.metric("Top batting score", ui.fmt_num(top_bat["score"].iat[0]) if len(top_bat) else "n/a",
              delta=top_bat["display_name"].iat[0] if len(top_bat) else None, delta_color="off", delta_arrow="off", border=True)
    st.metric("Top bowling score", ui.fmt_num(top_bowl["score"].iat[0]) if len(top_bowl) else "n/a",
              delta=top_bowl["display_name"].iat[0] if len(top_bowl) else None, delta_color="off", delta_arrow="off", border=True)

left, right = st.columns([1, 1.35], gap="medium")
with left:
    with st.container(border=True, height="stretch"):
        st.markdown("**:material/bolt: Pressure definition**")
        st.markdown(
            f"A delivery is a **pressure delivery** when it is bowled in a **second-innings chase** and, before the ball:\n"
            f"- required run rate **>= {C.PRESSURE_RRR:g}**, or\n"
            f"- **<= {C.LATE_BALLS} legal balls** remain and required run rate **>= {C.LATE_RRR:g}**.\n\n"
            "Targets and chase length use the official revised target/overs when recorded. "
            "Wides and no-balls do not consume a legal ball; super overs are excluded."
        )
        share2 = k["pressure_deliveries"] / max(1, int((state.filter_deliveries(ds, params)["any"]["innings"] == 2).sum())) * 100
        st.caption(f"In this scope {share2:.0f}% of chase deliveries meet the definition - a high bar is set by modern T20 targets "
                   "(any target of 181+ starts above RRR 9).")
with right:
    with st.container(border=True):
        st.markdown("**:material/insights: How the game changes under pressure (league-wide)**")
        ph = S["phase"]
        if not ph.empty:
            metric = st.segmented_control("Metric", ["Strike rate", "Balls per wicket", "Dot %"], default="Strike rate",
                                          key="ov_metric", label_visibility="collapsed")
            col = {"Strike rate": "strike_rate", "Balls per wicket": "balls_per_wkt", "Dot %": "dot_pct"}[metric or "Strike rate"]
            st.altair_chart(ui.grouped_bars(ph, "phase", col, "state", metric or "Strike rate", height=260))

c1, c2 = st.columns(2, gap="medium")
for col, key, title, view, cols in (
    (c1, "bat", ":material/sports_cricket: Top 5 pressure-ready batters", ui.BAT_VIEW, ["rank", "display_name", "score", "p_sr", "u_sr", "p_balls"]),
    (c2, "bowl", ":material/sports_baseball: Top 5 pressure-ready bowlers", ui.BOWL_VIEW, ["rank", "display_name", "score", "p_econ", "u_econ", "p_legal"]),
):
    with col:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            t = S[key]
            t = t[t["eligible"]].head(5)
            if t.empty:
                ui.empty_state("No eligible players in this scope.")
            else:
                ui.show_table(t, {c: view[c] for c in cols})
            if st.button("Full leaderboard", key=f"ov_go_{key}", icon=":material/arrow_forward:", type="tertiary"):
                st.switch_page("app_pages/leaderboards.py")

with st.container(border=True):
    st.markdown("**:material/calendar_month: Pressure volume and scoring by season**")
    se = S["season"]
    if not se.empty:
        vol = se.pivot_table(index="season", columns="state", values="deliveries", aggfunc="sum").fillna(0)
        vol["Pressure share %"] = vol.get("Pressure", 0) / vol.sum(axis=1) * 100
        a, b = st.columns(2)
        with a:
            st.altair_chart(ui.line_trend(se.assign(season=se["season"].astype(str)), "season", "strike_rate", "state", "Strike rate", height=240))
        with b:
            share = vol.reset_index()[["season", "Pressure share %"]].assign(season=lambda x: x["season"].astype(str))
            st.bar_chart(share, x="season", y="Pressure share %", color=ui.PINK, height=240, x_label="", y_label="Pressure share %")
