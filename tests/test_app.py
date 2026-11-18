"""Headless UI smoke tests: every page renders, and every global filter works."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "streamlit_app.py")
PAGES = [
    "app_pages/overview.py", "app_pages/leaderboards.py", "app_pages/recommendations.py",
    "app_pages/batting.py", "app_pages/bowling.py", "app_pages/pressure_vs_normal.py",
    "app_pages/teams_competitions.py", "app_pages/player_profile.py", "app_pages/compare.py",
    "app_pages/methodology.py",
]
TIMEOUT = 120


def fresh() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    return at


def errors(at: AppTest) -> list:
    return [e.value for e in at.exception] + [e.value for e in at.error]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    at = fresh()
    at.switch_page(page).run()
    assert not errors(at), errors(at)


def test_overview_kpis_present():
    at = fresh()
    labels = [m.label for m in at.metric]
    for needed in ("Players analysed", "Matches analysed", "Pressure deliveries", "Competitions",
                   "Eligible batters", "Eligible bowlers", "Top batting score", "Top bowling score"):
        assert needed in labels


def test_filters_change_kpis_and_reset():
    at = fresh()
    base = {m.label: m.value for m in at.metric}
    at.session_state["f_seasons"] = [2025]
    at.run()
    one = {m.label: m.value for m in at.metric}
    assert one["Matches analysed"] != base["Matches analysed"]
    at.session_state["f_groups"] = ["IPL"]
    at.run()
    ipl = {m.label: m.value for m in at.metric}
    assert ipl["Competitions"] == "1"
    at.session_state["f_teams"] = ["Rajasthan Royals"]
    at.run()
    assert not errors(at)
    reset = [b for b in at.sidebar.button if b.label == "Reset filters"][0]
    reset.click().run()
    again = {m.label: m.value for m in at.metric}
    assert again["Matches analysed"] == base["Matches analysed"]


@pytest.mark.parametrize("page", PAGES)
def test_pages_with_narrow_filters(page):
    """Single season + team + role + search must not crash any page."""
    at = fresh()
    at.session_state["f_seasons"] = [2024]
    at.session_state["f_groups"] = ["IPL"]
    at.session_state["f_teams"] = ["Rajasthan Royals"]
    at.session_state["f_roles"] = ["Bowler"]
    at.session_state["f_search"] = "a"
    at.run()
    at.switch_page(page).run()
    assert not errors(at), errors(at)


@pytest.mark.parametrize("page", PAGES)
def test_pages_with_empty_scope(page):
    at = fresh()
    at.session_state["f_seasons"] = []
    at.run()
    at.switch_page(page).run()
    assert not at.exception, at.exception


def test_leaderboard_views_and_sorting():
    at = fresh()
    at.switch_page("app_pages/leaderboards.py").run()
    for view in ("All eligible", "Limited sample", "Top 10"):
        at.segmented_control(key="lb_view_bat").set_value(view).run()
        assert not errors(at)
    at.selectbox(key="lb_sort_bowl").select("Pressure economy (low first)").run()
    assert not errors(at)
    tbl = at.dataframe[1].value
    assert tbl["p_econ"].is_monotonic_increasing


def test_top_tier_and_thresholds():
    at = fresh()
    at.session_state["f_top_tier"] = True
    at.session_state["f_min_balls"] = 60
    at.run()
    assert not errors(at)
    assert at.sidebar.warning  # non-default threshold warning


def test_compare_and_profile_interaction():
    at = fresh()
    at.switch_page("app_pages/compare.py").run()
    at.segmented_control(key="cmp_mode").set_value("Bowlers").run()
    assert not errors(at)
    at.switch_page("app_pages/player_profile.py").run()
    first = at.session_state["profile_player"]
    opts = at.selectbox(key="profile_player").options
    at.selectbox(key="profile_player").select_index(1).run()
    assert not errors(at)
    assert at.session_state["profile_player"] != first
    assert len(opts) > 100


def test_methodology_sensitivity():
    at = fresh()
    at.switch_page("app_pages/methodology.py").run()
    at.toggle(key="meth_sens").set_value(True).run()
    assert not errors(at)
