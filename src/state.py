"""Streamlit-side caching and global filter state shared by every page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config as C
from src import metrics as M
from src.data import Dataset, DataLoadError, build_dataset


@st.cache_resource(show_spinner="Loading and tagging every delivery...")
def get_dataset() -> Dataset:
    # Shared read-only object: pages must never mutate these frames in place.
    return build_dataset()


def dataset_or_stop() -> Dataset:
    try:
        return get_dataset()
    except DataLoadError as exc:
        st.error(f"Data could not be loaded. {exc}", icon=":material/error:")
        st.stop()


# --------------------------------------------------------------------------
# Global filters
# --------------------------------------------------------------------------
def _defaults(ds: Dataset) -> dict:
    return {
        "f_seasons": sorted(int(s) for s in ds.deliveries["season"].dropna().unique()),
        "f_groups": list(C.DEFAULT_COMP_GROUPS),
        "f_comps": [],
        "f_teams": [],
        "f_top_tier": False,
        "f_roles": [],
        "f_search": "",
        "f_min_balls": C.MIN_PRESSURE_BALLS,
        "f_min_matches": C.MIN_PRESSURE_MATCHES,
    }


def init_state(ds: Dataset) -> None:
    for k, v in _defaults(ds).items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_filters() -> None:
    for k, v in _defaults(get_dataset()).items():
        st.session_state[k] = v


def render_sidebar_filters(ds: Dataset) -> None:
    d = ds.deliveries
    with st.sidebar:
        st.markdown("**:material/tune: Filters**")
        st.pills("Season", sorted(int(s) for s in d["season"].dropna().unique()),
                 selection_mode="multi", key="f_seasons", width="stretch")
        st.pills("Competition type", C.COMP_GROUPS, selection_mode="multi", key="f_groups", width="stretch",
                 help="IPL = Indian Premier League. T20I = men's internationals. Other T20 = A-team / emerging tournaments.")
        groups = st.session_state.f_groups or C.COMP_GROUPS
        comp_opts = (ds.competitions[ds.competitions["comp_group"].isin(groups)]
                     .sort_values("comp_name")["comp_name"].tolist())
        st.session_state.f_comps = [c for c in st.session_state.f_comps if c in comp_opts]
        st.multiselect("Competition", comp_opts, key="f_comps", placeholder="All competitions in selected types")
        st.multiselect("Team", sorted(ds.teams["team_name"].unique()), key="f_teams", placeholder="All teams",
                       help="Batting stats use deliveries where the player batted for these teams; bowling stats where they bowled for them.")
        st.multiselect("Player role", C.ROLES, key="f_roles", placeholder="All roles",
                       help="Roles are derived from the data (bowling share, batting position, keeping) - not official designations.")
        st.text_input("Search player", key="f_search", placeholder="e.g. Samson", icon=":material/search:")
        st.toggle("Full Members & IPL only", key="f_top_tier",
                  help="Keep only IPL matches and T20Is between ICC Full Members.")
        with st.expander("Eligibility thresholds"):
            st.number_input("Min pressure balls", 10, 200, step=5, key="f_min_balls")
            st.number_input("Min pressure matches", 1, 30, step=1, key="f_min_matches")
            if (st.session_state.f_min_balls, st.session_state.f_min_matches) != (C.MIN_PRESSURE_BALLS, C.MIN_PRESSURE_MATCHES):
                st.warning("Non-default thresholds. The official ranking uses 40 balls and 6 matches.", icon=":material/warning:")
        st.button("Reset filters", icon=":material/restart_alt:", on_click=reset_filters, width="stretch")
        st.caption(
            f"**Pressure** = 2nd-innings chase with RRR >= {C.PRESSURE_RRR:g}, or <= {C.LATE_BALLS} legal balls "
            f"left with RRR >= {C.LATE_RRR:g}.")


def scope_params() -> tuple:
    s = st.session_state
    return (tuple(sorted(s.f_seasons)), tuple(sorted(s.f_groups)), tuple(sorted(s.f_comps)),
            tuple(sorted(s.f_teams)), bool(s.f_top_tier), int(s.f_min_balls), int(s.f_min_matches))


def filter_deliveries(ds: Dataset, params: tuple) -> dict[str, pd.DataFrame]:
    seasons, groups, comps, teams, top_tier, _, _ = params
    d = ds.deliveries
    mask = d["season"].isin(seasons) & d["comp_group"].isin(groups)
    if comps:
        mask &= d["comp_name"].isin(comps)
    if top_tier:
        mask &= d["top_tier"]
    d = d[mask]
    if teams:
        return {"bat": d[d["batting_team"].isin(teams)], "bowl": d[d["bowling_team"].isin(teams)],
                "any": d[d["batting_team"].isin(teams) | d["bowling_team"].isin(teams)]}
    return {"bat": d, "bowl": d, "any": d}


@st.cache_data(max_entries=48, show_spinner="Recomputing pressure ratings...")
def compute_scope(params: tuple) -> dict:
    ds = get_dataset()
    f = filter_deliveries(ds, params)
    min_balls, min_matches = params[5], params[6]
    bat = M.batting_table(f["bat"], ds.players, min_balls, min_matches)
    bowl = M.bowling_table(f["bowl"], ds.players, min_balls, min_matches)
    a = f["any"]
    players = pd.unique(pd.concat([a["striker_id"], a["non_striker_id"], a["bowler_id"]]))
    kpis = {
        "players": len(players),
        "matches": int(a["match_id"].nunique()),
        "pressure_deliveries": int(a["pressure"].sum()),
        "deliveries": len(a),
        "competitions": int(a["comp_id"].nunique()),
        "elig_bat": int(bat["eligible"].sum()) if len(bat) else 0,
        "elig_bowl": int(bowl["eligible"].sum()) if len(bowl) else 0,
        "top_bat": bat.loc[bat["eligible"]].head(1),
        "top_bowl": bowl.loc[bowl["eligible"]].head(1),
        "pressure_matches": int(a.loc[a["pressure"], "match_id"].nunique()),
    }
    return {
        "bat": bat, "bowl": bowl, "kpis": kpis,
        "phase": M.situation_summary(a, "phase"),
        "season": M.situation_summary(a, "season"),
        "group": M.situation_summary(a, "comp_group"),
        "comp": M.situation_summary(a, "comp_name"),
        "teams": M.team_summary(a),
    }


@st.cache_data(max_entries=24, show_spinner="Running bootstrap stability check...")
def compute_stability(params: tuple, kind: str, reps: int = 200) -> pd.DataFrame:
    f = filter_deliveries(get_dataset(), params)
    return M.bootstrap_top10(f["bat" if kind == "bat" else "bowl"], kind, reps=reps,
                             min_balls=params[5], min_matches=params[6])


SCENARIOS = {
    "Specified: RRR >= 9, or <= 30 balls & RRR >= 7.5": dict(rrr=9.0, late_balls=30, late_rrr=7.5),
    "Stricter: RRR >= 10, or <= 30 balls & RRR >= 8.5": dict(rrr=10.0, late_balls=30, late_rrr=8.5),
    "Looser: RRR >= 8, or <= 36 balls & RRR >= 7": dict(rrr=8.0, late_balls=36, late_rrr=7.0),
    "Close chases only: specified, but RRR <= 15": dict(rrr=9.0, late_balls=30, late_rrr=7.5, max_rrr=15.0),
}


@st.cache_data(max_entries=8, show_spinner="Running sensitivity analysis...")
def compute_sensitivity(params: tuple) -> pd.DataFrame:
    """Top-10 overlap with the specified definition under alternative thresholds."""
    from src.data import pressure_flag

    ds = get_dataset()
    f = filter_deliveries(ds, params)
    first = next(iter(SCENARIOS))
    rows, base = [], {}
    for name, kw in SCENARIOS.items():
        for kind, frame, fn in (("Batting", f["bat"], M.batting_table), ("Bowling", f["bowl"], M.bowling_table)):
            flag = pressure_flag(frame, **kw)
            t = fn(frame.assign(pressure=flag), ds.players, params[5], params[6])
            top = t[t["eligible"]].head(10)
            ids = list(top["player_id"])
            if name == first:
                base[kind] = ids
            rows.append({"scenario": name, "discipline": kind, "pressure_deliveries": int(flag.sum()),
                         "eligible": int(t["eligible"].sum()), "top10_overlap": len(set(ids) & set(base[kind])),
                         "top10": ", ".join(top["display_name"])})
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def compute_reconciliation() -> dict:
    from src.data import reconcile_results

    return reconcile_results(get_dataset())


def player_filter(t: pd.DataFrame) -> pd.DataFrame:
    """Role and search filters only hide rows; scores stay relative to the full pool."""
    s = st.session_state
    if t.empty:
        return t
    if s.f_roles:
        t = t[t["role"].isin(s.f_roles)]
    q = s.f_search.strip()
    if q:
        t = t[t["display_name"].str.contains(q, case=False, regex=False, na=False)]
    return t


def scope_caption() -> str:
    s = st.session_state
    seasons = s.f_seasons
    season_txt = "no seasons" if not seasons else (f"{min(seasons)}-{max(seasons)}" if len(seasons) > 1 else str(seasons[0]))
    parts = [season_txt, " + ".join(s.f_groups) or "no competitions"]
    if s.f_comps:
        parts.append(f"{len(s.f_comps)} competition(s)")
    if s.f_teams:
        parts.append(", ".join(s.f_teams[:3]) + ("..." if len(s.f_teams) > 3 else ""))
    if s.f_top_tier:
        parts.append("Full Members & IPL")
    return " | ".join(parts)
