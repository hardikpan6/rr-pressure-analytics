import altair as alt
import pandas as pd
import streamlit as st

from src import state, ui

params = state.scope_params()
if not params[0] or not params[1]:
    ui.empty_state("Select at least one season and one competition type.")
    st.stop()
S = state.compute_scope(params)

with st.container(horizontal=True, vertical_alignment="bottom", gap="medium"):
    pool = st.segmented_control("Player pool", ["Eligible only", "Eligible + limited sample"], default="Eligible only", key="pvn_pool")
    n = st.slider("Players per improver/decliner chart", 5, 20, 10, key="pvn_n", width=320)
include_limited = pool == "Eligible + limited sample"


def pool_of(t):
    keep = t["eligible"] | ((t["status"] == "Limited sample") & include_limited)
    return state.player_filter(t[keep])


bat, bowl = pool_of(S["bat"]), pool_of(S["bowl"])
st.caption("Points above the dashed y = x line scored faster under pressure (batters); points below it conceded less (bowlers). "
           "Usual = all non-pressure deliveries in the same scope.")

c1, c2 = st.columns(2, gap="medium")
with c1:
    with st.container(border=True):
        st.markdown("**:material/sports_cricket: Batters - pressure SR vs usual SR**")
        if bat.empty:
            ui.empty_state()
        else:
            st.altair_chart(ui.scatter_vs(bat, "u_sr", "p_sr", "Usual strike rate", "Pressure strike rate", "p_balls",
                                          ["display_name", "team", "status", "p_balls",
                                           alt.Tooltip("u_sr:Q", format=".1f", title="Usual SR"),
                                           alt.Tooltip("p_sr:Q", format=".1f", title="Pressure SR")], better="above"))
            st.caption(f"{(bat['uplift'] > 0).sum()} of {bat['uplift'].notna().sum()} batters strike faster under pressure.")
with c2:
    with st.container(border=True):
        st.markdown("**:material/sports_baseball: Bowlers - pressure economy vs usual economy**")
        if bowl.empty:
            ui.empty_state()
        else:
            st.altair_chart(ui.scatter_vs(bowl, "u_econ", "p_econ", "Usual economy", "Pressure economy", "p_legal",
                                          ["display_name", "team", "status", "p_legal",
                                           alt.Tooltip("u_econ:Q", format=".2f", title="Usual econ"),
                                           alt.Tooltip("p_econ:Q", format=".2f", title="Pressure econ")], better="below"))
            st.caption(f"{(bowl['econ_improvement'] > 0).sum()} of {bowl['econ_improvement'].notna().sum()} bowlers are cheaper under pressure.")

c3, c4 = st.columns(2, gap="medium")
with c3:
    with st.container(border=True):
        st.markdown("**Biggest batting risers and fallers (SR uplift)**")
        b = bat.dropna(subset=["uplift"])
        if not b.empty:
            sel = pd.concat([b.nlargest(n, "uplift"), b.nsmallest(n, "uplift")]).drop_duplicates("player_id")
            st.altair_chart(ui.diverging_bars(sel, "uplift", "SR uplift", "Pressure SR minus usual SR", height=max(300, 18 * len(sel))))
with c4:
    with st.container(border=True):
        st.markdown("**Biggest bowling risers and fallers (economy gain)**")
        w = bowl.dropna(subset=["econ_improvement"])
        if not w.empty:
            sel = pd.concat([w.nlargest(n, "econ_improvement"), w.nsmallest(n, "econ_improvement")]).drop_duplicates("player_id")
            st.altair_chart(ui.diverging_bars(sel, "econ_improvement", "Economy gain", "Usual economy minus pressure economy (runs/over)",
                                              height=max(300, 18 * len(sel))))

st.info("Context: pressure balls cluster in the death overs, where strike rates are naturally higher league-wide. "
        "Uplift therefore mixes genuine pressure response with phase effects - see Methodology for the league baseline by phase.",
        icon=":material/info:")
