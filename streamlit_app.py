import streamlit as st

from src import state, ui

st.set_page_config(
    page_title="RR Pressure Analytics | IPL 2027",
    page_icon=":material/sports_cricket:",
    layout="wide",
    initial_sidebar_state="expanded",
)

ui.inject_css()
ds = state.dataset_or_stop()
state.init_state(ds)

PAGES = {
    "": [
        st.Page("app_pages/overview.py", title="Executive overview", icon=":material/space_dashboard:", default=True),
        st.Page("app_pages/leaderboards.py", title="Leaderboards", icon=":material/leaderboard:"),
        st.Page("app_pages/recommendations.py", title="Recommendations", icon=":material/recommend:"),
    ],
    "Analysis": [
        st.Page("app_pages/batting.py", title="Batting under pressure", icon=":material/sports_cricket:"),
        st.Page("app_pages/bowling.py", title="Bowling under pressure", icon=":material/sports_baseball:"),
        st.Page("app_pages/pressure_vs_normal.py", title="Pressure vs normal", icon=":material/compare_arrows:"),
        st.Page("app_pages/teams_competitions.py", title="Teams & competitions", icon=":material/groups:"),
    ],
    "Players": [
        st.Page("app_pages/player_profile.py", title="Player profile", icon=":material/person_search:"),
        st.Page("app_pages/compare.py", title="Compare players", icon=":material/balance:"),
    ],
    "About": [
        st.Page("app_pages/methodology.py", title="Methodology & validation", icon=":material/science:"),
    ],
}
page = st.navigation(PAGES, position="top")

state.render_sidebar_filters(ds)

with st.container(horizontal=True, vertical_alignment="center", gap="small"):
    st.badge("Rajasthan Royals | IPL 2027 selection analytics", icon=":material/workspace_premium:", color="primary")
    st.badge(state.scope_caption(), icon=":material/filter_list:", color="gray")
st.title(page.title)

page.run()

st.divider()
st.caption(
    "Built from the supplied ball-by-ball data pack (IPL and men's T20I, 2022-2026). "
    "Reliability scores are percentile indices within the current filter scope - not probabilities. "
    "No squad-availability or auction claims are made."
)
