import altair as alt
import pandas as pd
import streamlit as st

from src import state, ui

params = state.scope_params()
if not params[0] or not params[1]:
    ui.empty_state("Select at least one season and one competition type.")
    st.stop()
S = state.compute_scope(params)
if S["kpis"]["deliveries"] == 0:
    ui.empty_state()
    st.stop()

view = st.segmented_control("View", ["IPL vs T20I", "By team", "By competition", "Season trends", "Role distribution"],
                            default="IPL vs T20I", key="tc_view") or "IPL vs T20I"

if view == "IPL vs T20I":
    g = S["group"]
    st.caption("League-level rates for every delivery in scope, split by pressure state. Use the Competition type filter to add 'Other T20'.")
    c1, c2, c3 = st.columns(3, gap="medium")
    for col, metric, title, fmt in ((c1, "strike_rate", "Strike rate", ".1f"), (c2, "economy", "Economy (runs/over)", ".2f"),
                                    (c3, "balls_per_wkt", "Balls per wicket", ".1f")):
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.altair_chart(ui.grouped_bars(g, "comp_group", metric, "state", title, height=280, fmt=fmt))
    tbl = g[["comp_group", "state", "deliveries", "strike_rate", "economy", "boundary_pct", "dot_pct", "balls_per_wkt"]]
    st.dataframe(tbl, hide_index=True, column_config={
        "comp_group": "Competition type", "state": "State", "deliveries": ui.CC.NumberColumn("Deliveries", format="%d"),
        "strike_rate": ui.CC.NumberColumn("SR", format="%.1f"), "economy": ui.CC.NumberColumn("Econ", format="%.2f"),
        "boundary_pct": ui.CC.NumberColumn("Boundary %", format="%.1f"), "dot_pct": ui.CC.NumberColumn("Dot %", format="%.1f"),
        "balls_per_wkt": ui.CC.NumberColumn("Balls/wkt", format="%.1f")})
    ui.download_csv(tbl, "rr_ipl_vs_t20i.csv", key="dl_grp")

    st.markdown("**Player-level: players with an eligible pressure sample in both IPL and T20I**")
    if not {"IPL", "T20I"} <= set(params[1]):
        st.caption("Select both IPL and T20I in the Competition type filter to see this comparison.")
    else:
        ipl = state.compute_scope(params[:1] + (("IPL",),) + params[2:])
        t20i = state.compute_scope(params[:1] + (("T20I",),) + params[2:])
        c1, c2 = st.columns(2, gap="medium")
        for col, kind, metric, label, fmt in ((c1, "bat", "p_sr", "pressure SR", ".1f"), (c2, "bowl", "p_econ", "pressure economy", ".2f")):
            a = ipl[kind][ipl[kind]["eligible"]][["player_id", "display_name", metric]]
            b = t20i[kind][t20i[kind]["eligible"]][["player_id", metric]]
            both = a.merge(b, on="player_id", suffixes=("_ipl", "_t20i"))
            with col:
                with st.container(border=True):
                    st.markdown(f"**{'Batters' if kind == 'bat' else 'Bowlers'} - IPL vs T20I {label}** ({len(both)} players)")
                    if both.empty:
                        ui.empty_state("No player is eligible in both competition types for this scope.")
                    else:
                        r = both[f"{metric}_ipl"].corr(both[f"{metric}_t20i"])
                        lo = float(both[[f"{metric}_ipl", f"{metric}_t20i"]].min().min()) * 0.95
                        hi = float(both[[f"{metric}_ipl", f"{metric}_t20i"]].max().max()) * 1.03
                        pts = alt.Chart(both).mark_circle(size=90, opacity=0.8, color=ui.PINK if kind == "bat" else ui.BLUE).encode(
                            x=alt.X(f"{metric}_ipl:Q", title=f"IPL {label}", scale=alt.Scale(domain=[lo, hi], zero=False)),
                            y=alt.Y(f"{metric}_t20i:Q", title=f"T20I {label}", scale=alt.Scale(domain=[lo, hi], zero=False)),
                            tooltip=["display_name", alt.Tooltip(f"{metric}_ipl:Q", format=fmt), alt.Tooltip(f"{metric}_t20i:Q", format=fmt)])
                        ref = alt.Chart(pd.DataFrame({"v": [lo, hi]})).mark_line(strokeDash=[5, 4], color=ui.MUTED).encode(x="v:Q", y="v:Q")
                        st.altair_chart((ref + pts).properties(height=300).interactive())
                        strength = "n/a" if pd.isna(r) else ("weak" if abs(r) < 0.3 else "moderate" if abs(r) < 0.6 else "strong")
                        st.caption(f"Pearson r = {r:.2f} ({strength} relationship between a player's IPL and T20I pressure numbers).")

elif view == "By team":
    t = S["teams"].copy()
    min_b = st.slider("Minimum pressure balls (batting side)", 0, 2000, 300, step=50, key="tc_minb")
    t = t[t["balls"].fillna(0) >= min_b]
    if t.empty:
        ui.empty_state("No teams pass the minimum ball filter.")
    else:
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            with st.container(border=True):
                st.markdown("**Pressure strike rate when chasing**")
                st.altair_chart(alt.Chart(t).mark_bar(cornerRadius=3, color=ui.PINK).encode(
                    x=alt.X("pressure_sr:Q", title="Pressure SR"), y=alt.Y("team:N", sort="-x", title=None),
                    tooltip=["team", alt.Tooltip("pressure_sr:Q", format=".1f"), "balls", "bat_matches"]).properties(height=max(280, 22 * len(t))))
        with c2:
            with st.container(border=True):
                st.markdown("**Pressure economy when defending**")
                st.altair_chart(alt.Chart(t.dropna(subset=["pressure_econ"])).mark_bar(cornerRadius=3, color=ui.BLUE).encode(
                    x=alt.X("pressure_econ:Q", title="Pressure economy"), y=alt.Y("team:N", sort="x", title=None),
                    tooltip=["team", alt.Tooltip("pressure_econ:Q", format=".2f"), "legal", "bowl_matches"]).properties(height=max(280, 22 * len(t))))
        st.dataframe(t, hide_index=True, column_config={
            "team": "Team", "bat_runs": ui.CC.NumberColumn("Pressure runs", format="%d"), "balls": ui.CC.NumberColumn("Pressure balls faced", format="%d"),
            "bnd": None, "bat_matches": ui.CC.NumberColumn("Chases w/ pressure", format="%d"),
            "pressure_sr": ui.CC.NumberColumn("Pressure SR", format="%.1f"), "boundary_pct": ui.CC.NumberColumn("Boundary %", format="%.1f"),
            "b_runs": None, "legal": ui.CC.NumberColumn("Pressure balls bowled", format="%d"), "wkts": ui.CC.NumberColumn("Pressure wkts", format="%d"),
            "bowl_matches": ui.CC.NumberColumn("Defences w/ pressure", format="%d"), "pressure_econ": ui.CC.NumberColumn("Pressure econ", format="%.2f"),
            "wkts_per_over": ui.CC.NumberColumn("Wkts/over", format="%.2f"), "pressure_chases": ui.CC.NumberColumn("Pressure chases", format="%d"),
            "pressure_chase_win_pct": ui.CC.NumberColumn("Pressure chase win %", format="%.0f%%")})
        ui.download_csv(t, "rr_team_pressure.csv", key="dl_team")

elif view == "By competition":
    c = S["comp"]
    piv = c.pivot_table(index="comp_name", columns="state", values=["deliveries", "strike_rate", "economy"]).reset_index()
    piv.columns = ["competition"] + [f"{a}_{b}".lower().replace("-", "_").replace(" ", "_") for a, b in piv.columns[1:]]
    piv = piv.fillna({"deliveries_pressure": 0}).sort_values("deliveries_pressure", ascending=False)
    top = piv.head(15)
    with st.container(border=True):
        st.markdown("**Largest competitions by pressure deliveries - pressure vs non-pressure SR**")
        long = top.melt(id_vars="competition", value_vars=["strike_rate_pressure", "strike_rate_non_pressure"], var_name="state", value_name="sr")
        long["state"] = long["state"].map({"strike_rate_pressure": "Pressure", "strike_rate_non_pressure": "Non-pressure"})
        st.altair_chart(ui.grouped_bars(long, "competition", "sr", "state", "Strike rate", height=max(320, 30 * len(top)), horizontal=True))
    st.dataframe(piv, hide_index=True, column_config={
        "competition": "Competition",
        "deliveries_non_pressure": ui.CC.NumberColumn("Non-pressure deliveries", format="%d"),
        "deliveries_pressure": ui.CC.NumberColumn("Pressure deliveries", format="%d"),
        "economy_non_pressure": ui.CC.NumberColumn("Econ (non-pressure)", format="%.2f"),
        "economy_pressure": ui.CC.NumberColumn("Econ (pressure)", format="%.2f"),
        "strike_rate_non_pressure": ui.CC.NumberColumn("SR (non-pressure)", format="%.1f"),
        "strike_rate_pressure": ui.CC.NumberColumn("SR (pressure)", format="%.1f")})
    ui.download_csv(piv, "rr_competition_pressure.csv", key="dl_comp")

elif view == "Season trends":
    se = S["season"].assign(season=lambda x: x["season"].astype(str))
    c1, c2, c3 = st.columns(3, gap="medium")
    for col, metric, title in ((c1, "strike_rate", "Strike rate"), (c2, "economy", "Economy"), (c3, "balls_per_wkt", "Balls per wicket")):
        with col:
            with st.container(border=True):
                st.markdown(f"**{title} by season**")
                st.altair_chart(ui.line_trend(se, "season", metric, "state", title, height=260))
    st.caption("Season = calendar year of the match date. Rising strike rates in IPL 2024-2026 push more chases into the pressure band.")
    tbl = se[["season", "state", "deliveries", "strike_rate", "economy", "boundary_pct", "dot_pct", "balls_per_wkt"]]
    st.dataframe(tbl, hide_index=True)
    ui.download_csv(tbl, "rr_season_trends.csv", key="dl_season")

else:
    bat, bowl = S["bat"], S["bowl"]
    dist = pd.concat([
        bat[bat["eligible"]].groupby("role").size().rename("players").reset_index().assign(leaderboard="Eligible batters"),
        bowl[bowl["eligible"]].groupby("role").size().rename("players").reset_index().assign(leaderboard="Eligible bowlers"),
    ])
    c1, c2 = st.columns([1.2, 1], gap="medium")
    with c1:
        with st.container(border=True):
            st.markdown("**Role distribution among eligible players**")
            st.altair_chart(ui.grouped_bars(dist, "role", "players", "leaderboard", "Players", height=300, fmt="d"))
    with c2:
        with st.container(border=True):
            st.markdown("**Average score by role**")
            avg = pd.concat([
                bat[bat["eligible"]].groupby("role")["score"].mean().rename("avg_score").reset_index().assign(leaderboard="Batting"),
                bowl[bowl["eligible"]].groupby("role")["score"].mean().rename("avg_score").reset_index().assign(leaderboard="Bowling"),
            ])
            st.altair_chart(ui.grouped_bars(avg, "role", "avg_score", "leaderboard", "Mean reliability score", height=300))
    st.caption("Roles are inferred from the data: Bowler = bowled >= 1 over in >= 50% of appearances; All-rounder also bats in the top 7 "
               "with >= 10 balls per innings; Wicketkeeper-batter = keeper in >= 50% of recorded matches.")
