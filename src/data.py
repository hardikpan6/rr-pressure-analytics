"""Data loading, cleaning and delivery-level pressure tagging.

This module has no Streamlit dependency so the validation script and unit
tests can import it directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src import config as C

REQUIRED_FILES = {
    "ball_by_ball": "ball_by_ball.csv",
    "matches": "matches.csv",
    "competitions": "competitions.csv",
    "teams": "teams.csv",
    "playing_eleven": "playing_eleven.csv",
    "mapping": "competition_team_player_mapping.csv",
}

BBB_COLUMNS = [
    "match_id", "innings", "overid", "over_ball_num", "innings_ball_num",
    "batting_team_id", "bowling_team_id", "striker_id", "striker_name",
    "non_striker_id", "non_striker_name", "bowler_id", "bowler_name",
    "batting_type", "bowling_type", "batting_order", "runs", "is_four",
    "is_six", "is_wicket", "dismissal_type", "dismissed_player_id",
    "extras_type", "extras1_runs", "extras_2_runs", "pace_or_spin",
]


class DataLoadError(RuntimeError):
    """Raised when the supplied CSV files are missing or malformed."""


@dataclass
class Dataset:
    deliveries: pd.DataFrame
    matches: pd.DataFrame
    players: pd.DataFrame
    teams: pd.DataFrame
    competitions: pd.DataFrame
    quality: dict


def load_raw(data_dir: Path | str = C.DATA_DIR) -> dict[str, pd.DataFrame]:
    data_dir = Path(data_dir)
    missing = [f for f in REQUIRED_FILES.values() if not (data_dir / f).exists()]
    if missing:
        raise DataLoadError(f"Missing data files in {data_dir.name}/: {', '.join(missing)}")
    raw = {}
    try:
        raw["ball_by_ball"] = pd.read_csv(data_dir / REQUIRED_FILES["ball_by_ball"], usecols=BBB_COLUMNS, low_memory=False)
        for key in ("matches", "competitions", "teams", "playing_eleven", "mapping"):
            raw[key] = pd.read_csv(data_dir / REQUIRED_FILES[key], low_memory=False)
    except ValueError as exc:  # usecols mismatch or parse failure
        raise DataLoadError(f"Could not parse the data files: {exc}") from exc
    return raw


def _comp_group(row) -> str:
    if row["match_format"] == "T20I":
        return "T20I"
    if str(row["comp_name"]).startswith("IPL"):
        return "IPL"
    return "Other T20"


def _match_context(raw: dict, bbb: pd.DataFrame) -> pd.DataFrame:
    """One row per match with competition info and the chase target/length."""
    comps = raw["competitions"].copy()
    comps["comp_group"] = comps.apply(_comp_group, axis=1)
    m = raw["matches"].merge(comps[["comp_id", "comp_name", "match_format", "comp_group"]], on="comp_id", how="left")
    m["match_date"] = pd.to_datetime(m["match_date"], errors="coerce")
    m["season"] = m["match_date"].dt.year.astype("Int64")

    inn1 = bbb[bbb["innings"] == 1].groupby("match_id").agg(
        inn1_runs=("total_runs", "sum"),
        inn1_wkts=("is_wicket", "sum"),
        inn1_legal=("is_legal", "sum"),
    )
    m = m.merge(inn1, left_on="match_id", right_index=True, how="left")

    dls_text = m["result"].astype(str).str.contains(r"D/L|DLS", case=False, regex=True)
    has_rev_target = m["revised_target"].notna()
    has_rev_overs = m["second_inn_revised_overs"].notna()
    # Revised overs are stored in balls (e.g. 114 = 19 overs) - verified.
    reduced_inferred = (~has_rev_overs) & (m["inn1_wkts"] < 10) & (m["inn1_legal"] < C.FULL_INNINGS_BALLS) & (m["inn1_legal"] > 0)

    m["target"] = np.where(has_rev_target, m["revised_target"], m["inn1_runs"] + 1)
    m["chase_balls"] = np.select(
        [has_rev_overs, reduced_inferred],
        [m["second_inn_revised_overs"], np.ceil(m["inn1_legal"] / 6) * 6],
        default=C.FULL_INNINGS_BALLS,
    )
    m["chase_context"] = np.select(
        [dls_text & ~has_rev_target, has_rev_target | has_rev_overs, reduced_inferred],
        ["DLS target unknown (excluded)", "Revised target/overs (official)", "Reduced overs (inferred)"],
        default="Standard 20 overs",
    )
    m["context_ok"] = m["chase_context"] != "DLS target unknown (excluded)"

    team_names = raw["teams"].drop_duplicates("team_id").set_index("team_id")["team_name"]
    is_top = lambda tid: team_names.get(tid, "") in C.FULL_MEMBER_TEAMS  # noqa: E731
    m["top_tier"] = (m["comp_group"] == "IPL") | (m["home_team_id"].map(is_top) & m["away_team_id"].map(is_top))
    return m


def _player_table(raw: dict, d: pd.DataFrame, team_names: pd.Series) -> pd.DataFrame:
    """Player master with data-derived role (not an official designation)."""
    names = pd.concat([
        d[["striker_id", "striker_name"]].set_axis(["player_id", "name"], axis=1),
        d[["non_striker_id", "non_striker_name"]].set_axis(["player_id", "name"], axis=1),
        d[["bowler_id", "bowler_name"]].set_axis(["player_id", "name"], axis=1),
    ]).drop_duplicates("player_id").set_index("player_id")["name"]

    xi = raw["playing_eleven"]
    played = xi[xi["is_played"] == True][["match_id", "player_id", "team_id", "is_wk"]]  # noqa: E712
    seen = pd.concat([
        d[["match_id", "striker_id", "batting_team_id"]].set_axis(["match_id", "player_id", "team_id"], axis=1),
        d[["match_id", "non_striker_id", "batting_team_id"]].set_axis(["match_id", "player_id", "team_id"], axis=1),
        d[["match_id", "bowler_id", "bowling_team_id"]].set_axis(["match_id", "player_id", "team_id"], axis=1),
    ])
    appear = pd.concat([played[["match_id", "player_id", "team_id"]], seen]).drop_duplicates(["match_id", "player_id"])
    apps = appear.groupby("player_id")["match_id"].nunique().rename("appearances")
    primary_team = appear.groupby("player_id")["team_id"].agg(lambda s: s.value_counts().index[0]).map(team_names).rename("primary_team")

    bowl = d.groupby(["bowler_id", "match_id"])["is_legal"].sum()
    bowled_matches = (bowl >= 6).groupby(level=0).sum().rename("bowled_matches")
    bat = d[d["ball_faced"]].groupby(["striker_id", "match_id"]).agg(balls=("ball_faced", "sum"), pos=("batting_order", "first"))
    bat_stats = bat.groupby(level=0).agg(bat_innings=("balls", "size"), balls_per_inn=("balls", "mean"), avg_bat_pos=("pos", "mean"))

    wk = played.dropna(subset=["is_wk"]).assign(is_wk=lambda x: x["is_wk"].astype(str).str.lower() == "true")
    wk_share = wk.groupby("player_id")["is_wk"].agg(["mean", "sum"]).rename(columns={"mean": "wk_share", "sum": "wk_matches"})

    bat_hand = d.groupby("striker_id")["batting_type"].agg(lambda s: s.mode().iat[0]).rename("batting_style")
    bowl_type = d.groupby("bowler_id")["bowling_type"].agg(lambda s: s.mode().iat[0]).rename("bowling_style")

    p = pd.DataFrame({"name": names})
    p.index.name = "player_id"
    p = p.join([apps, primary_team, bowled_matches, bat_stats, wk_share, bat_hand, bowl_type])
    for col in ("appearances", "bowled_matches", "bat_innings", "wk_matches"):
        p[col] = p[col].fillna(0).astype(int)
    p["bowl_share"] = (p["bowled_matches"] / p["appearances"].replace(0, np.nan)).fillna(0)

    def role(r) -> str:
        bats = r["bat_innings"] >= 5 and r["balls_per_inn"] >= 10 and r["avg_bat_pos"] <= 7
        if r["bowl_share"] >= 0.5:
            return "All-rounder" if bats else "Bowler"
        if r["wk_matches"] >= 3 and r["wk_share"] >= 0.5:
            return "Wicketkeeper-batter"
        if r["bowl_share"] >= 0.25 and bats:
            return "All-rounder"
        return "Batter"

    p["role"] = p.apply(role, axis=1)

    # Latest IPL squad membership as recorded in the supplied mapping file.
    mp = raw["mapping"]
    ipl = mp[mp["comp_name"].astype(str).str.match(r"^IPL \d{4}$")]
    if not ipl.empty:
        latest = ipl["comp_name"].max()
        squad = ipl[ipl["comp_name"] == latest].drop_duplicates("player_id").set_index("player_id")["team_name"]
        p["latest_ipl_squad"] = squad.reindex(p.index)
    else:
        p["latest_ipl_squad"] = pd.NA

    # Three names map to two different player IDs; disambiguate by team.
    dup = p["name"].duplicated(keep=False)
    p["display_name"] = p["name"]
    p.loc[dup, "display_name"] = p.loc[dup, "name"] + " (" + p.loc[dup, "primary_team"].fillna("?") + ")"
    dup2 = p["display_name"].duplicated(keep=False)
    p.loc[dup2, "display_name"] = p.loc[dup2, "display_name"] + " #" + p.index[dup2].astype(str)
    return p.reset_index()


def pressure_flag(d: pd.DataFrame, rrr: float = C.PRESSURE_RRR, late_balls: int = C.LATE_BALLS,
                  late_rrr: float = C.LATE_RRR, max_rrr: float = np.inf) -> pd.Series:
    """Pressure state before each delivery (live second-innings chases only).

    ``max_rrr`` is only used for sensitivity analysis (excluding lost-cause chases).
    """
    hit = (d["rrr"] >= rrr) | ((d["balls_left"] <= late_balls) & (d["rrr"] >= late_rrr))
    return d["live_chase"] & hit & (d["rrr"] <= max_rrr)


def reconcile_results(ds: "Dataset") -> dict:
    """Check reconstructed innings totals against the official result text."""
    d = ds.deliveries
    tot = d.groupby(["match_id", "innings"])["total_runs"].sum().unstack()
    tot.columns = [f"inn{c}" for c in tot.columns]
    m = ds.matches.set_index("match_id").join(tot, how="inner")
    res = m["result"].astype(str)
    margin = res.str.extract(r"(?i)by (\d+) run", expand=False).astype(float)
    clean = m["revised_target"].isna() & ~res.str.contains("super over|tied", case=False) & m["inn2"].notna()
    runs_w = clean & margin.notna()
    run_ok = (m.loc[runs_w, "inn1"] - m.loc[runs_w, "inn2"]) == margin[runs_w]
    wk_w = clean & res.str.contains(r"(?i)wicket")
    wk_ok = m.loc[wk_w, "inn2"] > m.loc[wk_w, "inn1"]
    return {
        "run_margin_results": int(runs_w.sum()), "run_margin_exact": int(run_ok.sum()),
        "run_margin_mismatches": m.loc[runs_w].loc[~run_ok, ["result", "inn1", "inn2"]].reset_index(),
        "wicket_results": int(wk_w.sum()), "wicket_chaser_ahead": int(wk_ok.sum()),
        "wicket_mismatches": m.loc[wk_w].loc[~wk_ok, ["result", "inn1", "inn2"]].reset_index(),
    }


def build_dataset(data_dir: Path | str = C.DATA_DIR) -> Dataset:
    raw = load_raw(data_dir)
    bbb = raw["ball_by_ball"]
    n_raw = len(bbb)
    super_over_rows = int((~bbb["innings"].isin([1, 2])).sum())
    d = bbb[bbb["innings"].isin([1, 2])].copy()
    d = d.sort_values(["match_id", "innings", "innings_ball_num"], kind="stable").reset_index(drop=True)

    et = d["extras_type"].fillna("")
    d["is_wide"] = et.isin(C.WIDE_TYPES)
    d["is_noball"] = et.isin(C.NOBALL_TYPES)
    d["is_legal"] = ~(d["is_wide"] | d["is_noball"])
    d["ball_faced"] = ~d["is_wide"]
    d["total_runs"] = d["runs"] + d["extras1_runs"] + d["extras_2_runs"]
    # Bowler is charged bat runs + wide runs + the no-ball penalty, never byes/leg-byes.
    d["bowler_runs"] = d["runs"] + np.where(d["is_wide"] | d["is_noball"], d["extras1_runs"], 0)
    d["bowler_wicket"] = d["is_wicket"] & d["dismissal_type"].isin(C.BOWLER_WICKET_TYPES)
    d["bat_boundary"] = d["ball_faced"] & ((d["is_four"] & (d["runs"] == 4)) | (d["is_six"] & (d["runs"] == 6)))
    d["bat_four"] = d["bat_boundary"] & (d["runs"] == 4)
    d["bat_six"] = d["bat_boundary"] & (d["runs"] == 6)
    d["bat_dot"] = d["ball_faced"] & (d["runs"] == 0)
    d["bowler_dot"] = d["is_legal"] & (d["bowler_runs"] == 0)

    grp = d.groupby(["match_id", "innings"], sort=False)
    d["runs_before"] = grp["total_runs"].cumsum() - d["total_runs"]
    d["legal_before"] = grp["is_legal"].cumsum() - d["is_legal"].astype(int)
    d["wkts_before"] = grp["is_wicket"].cumsum() - d["is_wicket"].astype(int)

    matches = _match_context(raw, d)
    ctx_cols = ["match_id", "season", "comp_id", "comp_name", "comp_group", "match_date", "target",
                "chase_balls", "chase_context", "context_ok", "top_tier", "win_team_id", "stage"]
    d = d.merge(matches[ctx_cols], on="match_id", how="left", validate="many_to_one")

    chase = d["innings"] == 2
    d["runs_needed"] = np.where(chase, d["target"] - d["runs_before"], np.nan)
    d["balls_left"] = np.where(chase, d["chase_balls"] - d["legal_before"], np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        d["rrr"] = np.where(chase & (d["balls_left"] > 0), d["runs_needed"] * 6 / d["balls_left"], np.nan)
    live = chase & d["context_ok"] & (d["runs_needed"] > 0) & (d["balls_left"] > 0)
    d["live_chase"] = live
    d["pressure"] = pressure_flag(d)
    d["phase"] = pd.cut(d["overid"], bins=[0, 6, 15, 20], labels=["Powerplay (1-6)", "Middle (7-15)", "Death (16-20)"]).astype(str)
    d["batting_won"] = d["win_team_id"] == d["batting_team_id"]
    d["bowling_won"] = d["win_team_id"] == d["bowling_team_id"]

    teams = raw["teams"].drop_duplicates("team_id")[["team_id", "team_name"]]
    team_names = teams.set_index("team_id")["team_name"]
    d["batting_team"] = d["batting_team_id"].map(team_names)
    d["bowling_team"] = d["bowling_team_id"].map(team_names)

    players = _player_table(raw, d, team_names)
    comps = raw["competitions"].copy()
    comps["comp_group"] = comps.apply(_comp_group, axis=1)

    overs = d.groupby(["match_id", "innings", "overid"])["is_legal"].sum().reset_index()
    last_over = overs.groupby(["match_id", "innings"])["overid"].transform("max")
    nonfinal = overs[overs["overid"] != last_over]

    quality = {
        "raw_rows": n_raw,
        "super_over_rows_excluded": super_over_rows,
        "analysed_rows": len(d),
        "matches_in_file": int(raw["matches"]["match_id"].nunique()),
        "matches_with_balls": int(d["match_id"].nunique()),
        "matches_without_balls": int(len(set(raw["matches"]["match_id"]) - set(d["match_id"]))),
        "chase_context_counts": matches[matches["match_id"].isin(d["match_id"])]["chase_context"].value_counts().to_dict(),
        "duplicate_name_ids": int(players["name"].duplicated(keep=False).sum()),
        "latest_ipl": str(comps.loc[comps["comp_group"] == "IPL", "comp_name"].max()),
        "nonfinal_overs": len(nonfinal),
        "nonfinal_six_legal": int((nonfinal["is_legal"] == 6).sum()),
        "orphan_matches": len(set(d["match_id"]) - set(raw["matches"]["match_id"])),
        "orphan_players": len((set(d["striker_id"]) | set(d["non_striker_id"]) | set(d["bowler_id"])) - set(raw["mapping"]["player_id"])),
    }
    keep = [c for c in d.columns if c not in ("striker_name", "non_striker_name", "bowler_name")]
    return Dataset(d[keep], matches, players, teams, comps, quality)
