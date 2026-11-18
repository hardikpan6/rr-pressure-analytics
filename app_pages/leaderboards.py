import streamlit as st

from src import state, ui

params = state.scope_params()
if not params[0] or not params[1]:
    ui.empty_state("Select at least one season and one competition type.")
    st.stop()
S = state.compute_scope(params)

st.caption(
    "Ranks are computed among **eligible** players only (>= {} pressure balls in >= {} matches). "
    "Limited-sample players receive a *provisional* score against the eligible distribution and are never ranked. "
    "Click a column header to sort, or pick a row to open the player profile.".format(params[5], params[6])
)

SORTS_BAT = {"Reliability score": "score", "Pressure SR": "p_sr", "Pressure runs": "p_runs", "SR uplift": "uplift",
             "Boundary %": "p_bnd_pct", "Pressure balls": "p_balls", "Kept pace %": "consistency"}
SORTS_BOWL = {"Reliability score": "score", "Pressure economy (low first)": "p_econ", "Pressure wickets": "p_wkts",
              "Wickets per over": "p_wpb", "Dot %": "p_dot_pct", "Economy gain": "econ_improvement", "Pressure balls": "p_legal"}


def board(kind: str) -> None:
    t = S[kind]
    if t.empty:
        ui.empty_state()
        return
    stab = state.compute_stability(params, kind)
    t = t.merge(stab[["player_id", "top10_share"]], on="player_id", how="left")
    t.loc[~t["eligible"], "top10_share"] = None
    sorts = SORTS_BAT if kind == "bat" else SORTS_BOWL

    with st.container(horizontal=True, vertical_alignment="bottom", gap="medium"):
        view = st.segmented_control("Show", ["Top 10", "All eligible", "Limited sample"], default="Top 10", key=f"lb_view_{kind}")
        sort_label = st.selectbox("Sort by", list(sorts), key=f"lb_sort_{kind}", width=240)
    view = view or "Top 10"
    col = sorts[sort_label]
    asc = col == "p_econ"

    if view == "Limited sample":
        rows = t[t["status"] == "Limited sample"]
        st.warning("Provisional scores - fewer than the eligibility threshold. Not equally reliable as the main ranking.", icon=":material/science:")
    else:
        rows = t[t["eligible"]]
        if view == "Top 10":
            rows = rows.head(10)
    rows = state.player_filter(rows).sort_values(col, ascending=asc, na_position="last")
    if rows.empty:
        ui.empty_state("No players match the current role/search filters.")
        return

    cfg = ui.BAT_VIEW if kind == "bat" else ui.BOWL_VIEW
    ev = ui.show_table(rows, cfg, key=f"lb_tbl_{kind}_{view}", selectable=True,
                       height=min(38 + 35 * len(rows), 620))
    picked = ev.selection.rows if ev is not None else []
    with st.container(horizontal=True, gap="small"):
        ui.download_csv(rows, f"rr_pressure_{'batters' if kind == 'bat' else 'bowlers'}_{view.lower().replace(' ', '_')}.csv", key=f"dl_{kind}")
        if picked:
            pid = int(rows.iloc[picked[0]]["player_id"])
            name = rows.iloc[picked[0]]["display_name"]
            if st.button(f"Open profile: {name}", key=f"open_{kind}", icon=":material/person_search:", type="primary"):
                st.session_state.profile_player = pid
                st.switch_page("app_pages/player_profile.py")
        else:
            st.caption("Select a row to open the player profile.")


bat_tab, bowl_tab = st.tabs([":material/sports_cricket: Pressure-ready batters", ":material/sports_baseball: Pressure-ready bowlers"])
with bat_tab:
    st.caption("Score = 55% pressure SR percentile + 25% SR-uplift percentile (uplift clipped to +/-40) + 20% boundary-ball % percentile.")
    board("bat")
with bowl_tab:
    st.caption("Score = 45% inverse pressure-economy percentile + 35% wickets-per-6-balls percentile + 20% dot-ball % percentile.")
    board("bowl")
