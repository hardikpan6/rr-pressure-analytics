import altair as alt
import pandas as pd
import streamlit as st

from src import state, ui

params = state.scope_params()
if not params[0] or not params[1]:
    ui.empty_state("Select at least one season and one competition type.")
    st.stop()
S = state.compute_scope(params)
bat, bowl = S["bat"], S["bowl"]
if bat.empty and bowl.empty:
    ui.empty_state()
    st.stop()

mode = st.segmented_control("Compare as", ["Batters", "Bowlers"], default="Batters", key="cmp_mode") or "Batters"
t = bat if mode == "Batters" else bowl
vol = "p_balls" if mode == "Batters" else "p_legal"
t = state.player_filter(t[t[vol] > 0])
names = dict(zip(t["player_id"].astype(int), t["display_name"]))
default = [i for i in t[t["eligible"]].head(3)["player_id"].astype(int)]
key = f"cmp_players_{mode}"
if key not in st.session_state:
    st.session_state[key] = default
st.session_state[key] = [i for i in st.session_state[key] if i in names]
picked = st.multiselect("Players (2-6)", list(names), format_func=lambda i: names.get(i, str(i)), key=key, max_selections=6,
                        placeholder="Choose players to compare")
if len(picked) < 2:
    st.info("Select at least two players to compare.", icon=":material/group_add:")
    st.stop()

sel = t[t["player_id"].isin(picked)].copy()
sel["display_name"] = pd.Categorical(sel["display_name"], [names[i] for i in picked])
sel = sel.sort_values("display_name")
sel["display_name"] = sel["display_name"].astype(str)
if (~sel["eligible"]).any():
    st.warning("Players marked 'Limited sample' have provisional scores and are not equally reliable.", icon=":material/science:")

if mode == "Batters":
    metrics = [("Reliability score", "score", ".1f"), ("Pressure runs", "p_runs", "d"), ("Pressure SR", "p_sr", ".1f"),
               ("Boundary %", "p_bnd_pct", ".1f"), ("Kept pace %", "consistency", ".0f"), ("Pressure matches", "p_matches", "d")]
    pair = ("p_sr", "u_sr", "Pressure SR", "Usual SR", "Strike rate")
    pct = {"Pressure SR": "pct_sr", "SR uplift": "pct_uplift", "Boundary %": "pct_boundary"}
    cfg = ui.BAT_VIEW
else:
    metrics = [("Reliability score", "score", ".1f"), ("Pressure wickets", "p_wkts", "d"), ("Pressure economy", "p_econ", ".2f"),
               ("Dot-ball %", "p_dot_pct", ".1f"), ("Held %", "consistency", ".0f"), ("Pressure matches", "p_matches", "d")]
    pair = ("p_econ", "u_econ", "Pressure economy", "Usual economy", "Economy")
    pct = {"Economy (inverse)": "pct_economy", "Wickets per over": "pct_wkts", "Dot %": "pct_dots"}
    cfg = ui.BOWL_VIEW

ui.show_table(sel, cfg, key="cmp_tbl")
ui.download_csv(sel, f"rr_compare_{mode.lower()}.csv", key="dl_cmp")

c1, c2 = st.columns(2, gap="medium")
with c1:
    with st.container(border=True):
        st.markdown(f"**{pair[4]}: pressure vs usual**")
        long = sel.melt(id_vars="display_name", value_vars=[pair[0], pair[1]], var_name="state", value_name="v")
        long["state"] = long["state"].map({pair[0]: pair[2], pair[1]: pair[3]})
        st.altair_chart(ui.grouped_bars(long, "display_name", "v", "state", pair[4], height=300, fmt=".2f"))
with c2:
    with st.container(border=True):
        st.markdown("**Percentile profile (score components)**")
        long = sel.melt(id_vars="display_name", value_vars=list(pct.values()), var_name="component", value_name="pct")
        long["component"] = long["component"].map({v: k for k, v in pct.items()})
        st.altair_chart(ui.grouped_bars(long, "component", "pct", "display_name", "Percentile among eligible", height=300))

with st.container(border=True):
    st.markdown("**Head-to-head metrics**")
    cols = st.columns(3, gap="medium")
    for i, (label, col, fmt) in enumerate(metrics):
        with cols[i % 3]:
            m = sel[["display_name", col]].rename(columns={col: "v"})
            bars = alt.Chart(m).mark_bar(cornerRadius=3).encode(
                x=alt.X("v:Q", title=label),
                y=alt.Y("display_name:N", sort=None, title=None, axis=alt.Axis(labelLimit=130, labelOverlap=False)),
                color=alt.Color("display_name:N", legend=None, sort=None,
                                scale=alt.Scale(range=[ui.PINK, ui.BLUE, ui.GOLD, ui.GREEN, "#A78BFA", "#FF9F43"])),
                tooltip=["display_name", alt.Tooltip("v:Q", format=fmt, title=label)])
            text = bars.mark_text(align="left", dx=4, color="#EEF1F8").encode(text=alt.Text("v:Q", format=fmt))
            st.altair_chart((bars + text).properties(height=34 * len(m) + 50))

other = bowl if mode == "Batters" else bat
o = other[other["player_id"].isin(picked)]
if not o.empty:
    with st.expander(f"Their {'bowling' if mode == 'Batters' else 'batting'} under pressure (separate scale - do not compare scores across disciplines)"):
        ui.show_table(o, ui.BOWL_VIEW if mode == "Batters" else ui.BAT_VIEW, key="cmp_other")
