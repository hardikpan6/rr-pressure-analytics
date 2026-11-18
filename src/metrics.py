"""Player aggregation, eligibility, percentile scoring and recommendations.

Pure pandas/numpy - no Streamlit imports.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src import config as C

PLAYER_COLS = ["player_id", "name", "display_name", "role", "batting_style", "bowling_style", "latest_ipl_squad"]

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def mid_percentile(ref: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Percentile of each value within ``ref`` using the mid-rank convention.

    pct = (count(ref < v) + 0.5 * count(ref == v)) / len(ref) * 100.
    Applied to the reference pool itself this equals the average-rank
    percentile, so eligible and provisional scores share one scale.
    """
    ref = np.sort(np.asarray(ref, dtype=float)[~np.isnan(ref)])
    values = np.asarray(values, dtype=float)
    out = np.full(values.shape, np.nan)
    if len(ref) == 0:
        return out
    ok = ~np.isnan(values)
    lo = np.searchsorted(ref, values[ok], side="left")
    hi = np.searchsorted(ref, values[ok], side="right")
    out[ok] = (lo + hi) / 2 / len(ref) * 100
    return out


def _safe_div(a, b, scale=1.0):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0, a / b * scale, np.nan)


def _mode_team(df: pd.DataFrame, key: str, team_col: str) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="object")
    counts = df.groupby([key, team_col]).size().reset_index(name="n")
    counts = counts.sort_values([key, "n"], ascending=[True, False])
    return counts.drop_duplicates(key).set_index(key)[team_col]


# --------------------------------------------------------------------------
# Batting
# --------------------------------------------------------------------------
def _bat_split(d: pd.DataFrame, mask: pd.Series, prefix: str) -> pd.DataFrame:
    x = d[mask]
    g = x.groupby("striker_id").agg(
        runs=("runs", "sum"),
        balls=("ball_faced", "sum"),
        fours=("bat_four", "sum"),
        sixes=("bat_six", "sum"),
        boundaries=("bat_boundary", "sum"),
        dots=("bat_dot", "sum"),
    )
    faced = x[x["ball_faced"]]
    g["matches"] = faced.groupby("striker_id")["match_id"].nunique()
    # Counts dismissals at either end (striker or non-striker run-outs).
    outs = x[x["is_wicket"] & x["dismissed_player_id"].notna()]
    outs_by = outs.groupby(outs["dismissed_player_id"].astype("int64")).size()
    g["outs"] = outs_by.reindex(g.index).fillna(0)
    g.index.name = "player_id"
    return g.add_prefix(prefix)


def batting_table(d: pd.DataFrame, players: pd.DataFrame,
                  min_balls: int = C.MIN_PRESSURE_BALLS,
                  min_matches: int = C.MIN_PRESSURE_MATCHES) -> pd.DataFrame:
    """One row per batter in scope with pressure, usual and overall stats."""
    cols = ["p_runs", "p_balls", "p_fours", "p_sixes", "p_boundaries", "p_dots", "p_matches", "p_outs"]
    if d.empty:
        return pd.DataFrame(columns=["player_id", "name", "score", "eligible"] + cols)
    p = _bat_split(d, d["pressure"], "p_")
    u = _bat_split(d, ~d["pressure"], "u_")
    t = p.join(u, how="outer").fillna(0)
    t = t[(t["p_balls"] > 0) | (t["u_balls"] > 0)]

    for pref in ("p_", "u_"):
        t[pref + "sr"] = _safe_div(t[pref + "runs"], t[pref + "balls"], 100)
        t[pref + "bnd_pct"] = _safe_div(t[pref + "boundaries"], t[pref + "balls"], 100)
        t[pref + "dot_pct"] = _safe_div(t[pref + "dots"], t[pref + "balls"], 100)
        t[pref + "avg"] = _safe_div(t[pref + "runs"], t[pref + "outs"])
        t[pref + "bpd"] = _safe_div(t[pref + "balls"], t[pref + "outs"])
    t["o_runs"] = t["p_runs"] + t["u_runs"]
    t["o_balls"] = t["p_balls"] + t["u_balls"]
    t["o_sr"] = _safe_div(t["o_runs"], t["o_balls"], 100)
    t["o_matches"] = d[d["ball_faced"]].groupby("striker_id")["match_id"].nunique().reindex(t.index).fillna(0)
    t["uplift"] = t["p_sr"] - t["u_sr"]
    t["pressure_share"] = _safe_div(t["p_balls"], t["o_balls"], 100)

    # Match-level consistency under pressure.
    pm = d[d["pressure"] & d["ball_faced"]].groupby(["striker_id", "match_id"]).agg(
        r=("runs", "sum"), b=("ball_faced", "sum"), won=("batting_won", "first"))
    pm["sr"] = pm["r"] / pm["b"] * 100
    q = pm[pm["b"] >= C.CONSISTENCY_MIN_BAT_BALLS]
    t["qual_innings"] = q.groupby(level=0).size().reindex(t.index).fillna(0)
    t["kept_pace"] = (q["sr"] >= C.CONSISTENCY_BAT_SR).groupby(level=0).sum().reindex(t.index).fillna(0)
    t["consistency"] = _safe_div(t["kept_pace"], t["qual_innings"], 100)
    t["match_sr_sd"] = q.groupby(level=0)["sr"].std().reindex(t.index)
    t["pressure_wins"] = pm.groupby(level=0)["won"].sum().reindex(t.index).fillna(0)
    t["best_pressure_innings"] = pm.groupby(level=0)["r"].max().reindex(t.index).fillna(0)

    pr = d[d["pressure"] & d["ball_faced"]]
    team = _mode_team(pr, "striker_id", "batting_team").reindex(t.index)
    t["team"] = team.fillna(_mode_team(d[d["ball_faced"]], "striker_id", "batting_team").reindex(t.index))
    t["teams_played"] = d[d["ball_faced"]].groupby("striker_id")["batting_team"].agg(lambda s: ", ".join(sorted(s.unique()))).reindex(t.index)

    t = t.reset_index().merge(players[PLAYER_COLS], on="player_id", how="left")
    t = _score_batting(t, min_balls, min_matches)
    return t


def _score_batting(t: pd.DataFrame, min_balls: int, min_matches: int) -> pd.DataFrame:
    t["eligible"] = (t["p_balls"] >= min_balls) & (t["p_matches"] >= min_matches)
    t["baseline_missing"] = t["u_sr"].isna()
    t["uplift_clipped"] = t["uplift"].clip(-C.UPLIFT_CLIP, C.UPLIFT_CLIP)
    pool = t[t["eligible"]]
    t["pct_sr"] = mid_percentile(pool["p_sr"].to_numpy(), t["p_sr"].to_numpy())
    t["pct_uplift"] = mid_percentile(pool["uplift_clipped"].to_numpy(), t["uplift_clipped"].to_numpy())
    t["pct_uplift"] = t["pct_uplift"].fillna(50.0)  # neutral when no usual baseline exists
    t["pct_boundary"] = mid_percentile(pool["p_bnd_pct"].to_numpy(), t["p_bnd_pct"].to_numpy())
    w = C.BAT_WEIGHTS
    t["score"] = w["sr"] * t["pct_sr"] + w["uplift"] * t["pct_uplift"] + w["boundary"] * t["pct_boundary"]
    t.loc[t["p_balls"] <= 0, "score"] = np.nan
    t["status"] = np.select(
        [t["eligible"], t["p_balls"] >= C.EMERGING_MIN_BALLS],
        ["Eligible", "Limited sample"], default="Insufficient sample")
    t = t.sort_values(["eligible", "score", "p_sr", "p_balls"], ascending=[False, False, False, False]).reset_index(drop=True)
    t["rank"] = np.where(t["eligible"], np.arange(1, len(t) + 1), np.nan)
    return t


# --------------------------------------------------------------------------
# Bowling
# --------------------------------------------------------------------------
def _bowl_split(d: pd.DataFrame, mask: pd.Series, prefix: str) -> pd.DataFrame:
    x = d[mask]
    g = x.groupby("bowler_id").agg(
        deliveries=("is_legal", "size"),
        legal=("is_legal", "sum"),
        runs=("bowler_runs", "sum"),
        wkts=("bowler_wicket", "sum"),
        dots=("bowler_dot", "sum"),
        wides=("is_wide", "sum"),
        noballs=("is_noball", "sum"),
        boundaries=("bat_boundary", "sum"),
        matches=("match_id", "nunique"),
    )
    g.index.name = "player_id"
    return g.add_prefix(prefix)


def bowling_table(d: pd.DataFrame, players: pd.DataFrame,
                  min_balls: int = C.MIN_PRESSURE_BALLS,
                  min_matches: int = C.MIN_PRESSURE_MATCHES) -> pd.DataFrame:
    cols = ["p_legal", "p_runs", "p_wkts", "p_dots", "p_matches"]
    if d.empty:
        return pd.DataFrame(columns=["player_id", "name", "score", "eligible"] + cols)
    p = _bowl_split(d, d["pressure"], "p_")
    u = _bowl_split(d, ~d["pressure"], "u_")
    t = p.join(u, how="outer").fillna(0)
    for pref in ("p_", "u_"):
        t[pref + "econ"] = _safe_div(t[pref + "runs"], t[pref + "legal"], 6)
        t[pref + "wpb"] = _safe_div(t[pref + "wkts"], t[pref + "legal"], 6)  # wickets per 6 legal balls
        t[pref + "dot_pct"] = _safe_div(t[pref + "dots"], t[pref + "legal"], 100)
        t[pref + "bsr"] = _safe_div(t[pref + "legal"], t[pref + "wkts"])  # balls per wicket
        t[pref + "avg"] = _safe_div(t[pref + "runs"], t[pref + "wkts"])
        t[pref + "bnd_pct"] = _safe_div(t[pref + "boundaries"], t[pref + "legal"], 100)
    t["o_legal"] = t["p_legal"] + t["u_legal"]
    t["o_runs"] = t["p_runs"] + t["u_runs"]
    t["o_wkts"] = t["p_wkts"] + t["u_wkts"]
    t["o_econ"] = _safe_div(t["o_runs"], t["o_legal"], 6)
    t["o_matches"] = d.groupby("bowler_id")["match_id"].nunique().reindex(t.index).fillna(0)
    t["econ_improvement"] = t["u_econ"] - t["p_econ"]  # positive = cheaper under pressure
    t["pressure_share"] = _safe_div(t["p_legal"], t["o_legal"], 100)

    pm = d[d["pressure"]].groupby(["bowler_id", "match_id"]).agg(
        r=("bowler_runs", "sum"), b=("is_legal", "sum"), w=("bowler_wicket", "sum"), won=("bowling_won", "first"))
    pm["econ"] = _safe_div(pm["r"], pm["b"], 6)
    q = pm[pm["b"] >= C.CONSISTENCY_MIN_BOWL_BALLS]
    t["qual_spells"] = q.groupby(level=0).size().reindex(t.index).fillna(0)
    t["held"] = (q["econ"] <= C.CONSISTENCY_BOWL_ECON).groupby(level=0).sum().reindex(t.index).fillna(0)
    t["consistency"] = _safe_div(t["held"], t["qual_spells"], 100)
    t["match_econ_sd"] = q.groupby(level=0)["econ"].std().reindex(t.index)
    t["wicket_spells"] = (pm["w"] > 0).groupby(level=0).sum().reindex(t.index).fillna(0)
    t["pressure_wins"] = pm.groupby(level=0)["won"].sum().reindex(t.index).fillna(0)

    team = _mode_team(d[d["pressure"]], "bowler_id", "bowling_team").reindex(t.index)
    t["team"] = team.fillna(_mode_team(d, "bowler_id", "bowling_team").reindex(t.index))
    t["teams_played"] = d.groupby("bowler_id")["bowling_team"].agg(lambda s: ", ".join(sorted(s.unique()))).reindex(t.index)

    t = t.reset_index().merge(players[PLAYER_COLS], on="player_id", how="left")
    t = _score_bowling(t, min_balls, min_matches)
    return t


def _score_bowling(t: pd.DataFrame, min_balls: int, min_matches: int) -> pd.DataFrame:
    t["eligible"] = (t["p_legal"] >= min_balls) & (t["p_matches"] >= min_matches)
    t["baseline_missing"] = t["u_econ"].isna()
    pool = t[t["eligible"]]
    t["pct_economy"] = mid_percentile(-pool["p_econ"].to_numpy(), -t["p_econ"].to_numpy())
    t["pct_wkts"] = mid_percentile(pool["p_wpb"].to_numpy(), t["p_wpb"].to_numpy())
    t["pct_dots"] = mid_percentile(pool["p_dot_pct"].to_numpy(), t["p_dot_pct"].to_numpy())
    w = C.BOWL_WEIGHTS
    t["score"] = w["economy"] * t["pct_economy"] + w["wkts"] * t["pct_wkts"] + w["dots"] * t["pct_dots"]
    t.loc[t["p_legal"] <= 0, "score"] = np.nan
    t["status"] = np.select(
        [t["eligible"], t["p_legal"] >= C.EMERGING_MIN_BALLS],
        ["Eligible", "Limited sample"], default="Insufficient sample")
    t = t.sort_values(["eligible", "score", "p_econ", "p_legal"], ascending=[False, False, True, False]).reset_index(drop=True)
    t["rank"] = np.where(t["eligible"], np.arange(1, len(t) + 1), np.nan)
    return t


# --------------------------------------------------------------------------
# Context tables
# --------------------------------------------------------------------------
def situation_summary(d: pd.DataFrame, by: str) -> pd.DataFrame:
    """League-level pressure vs non-pressure rates grouped by ``by``."""
    if d.empty:
        return pd.DataFrame()
    g = d.assign(state=np.where(d["pressure"], "Pressure", "Non-pressure")).groupby([by, "state"]).agg(
        bat_runs=("runs", "sum"), balls=("ball_faced", "sum"), bnd=("bat_boundary", "sum"),
        b_runs=("bowler_runs", "sum"), legal=("is_legal", "sum"), wkts=("bowler_wicket", "sum"),
        dots=("bowler_dot", "sum"), deliveries=("is_legal", "size"))
    g["strike_rate"] = _safe_div(g["bat_runs"], g["balls"], 100)
    g["economy"] = _safe_div(g["b_runs"], g["legal"], 6)
    g["boundary_pct"] = _safe_div(g["bnd"], g["balls"], 100)
    g["dot_pct"] = _safe_div(g["dots"], g["legal"], 100)
    g["balls_per_wkt"] = _safe_div(g["legal"], g["wkts"])
    g = g.reset_index()
    if by == "phase":
        order = {"Powerplay (1-6)": 0, "Middle (7-15)": 1, "Death (16-20)": 2}
        g = g.sort_values(["phase", "state"], key=lambda s: s.map(order) if s.name == "phase" else s).reset_index(drop=True)
    return g


def team_summary(d: pd.DataFrame) -> pd.DataFrame:
    """Pressure batting (as chasing side) and bowling (as defending side) by team."""
    pr = d[d["pressure"]]
    if pr.empty:
        return pd.DataFrame()
    bat = pr.groupby("batting_team").agg(bat_runs=("runs", "sum"), balls=("ball_faced", "sum"),
                                         bnd=("bat_boundary", "sum"), bat_matches=("match_id", "nunique"))
    bat["pressure_sr"] = _safe_div(bat["bat_runs"], bat["balls"], 100)
    bat["boundary_pct"] = _safe_div(bat["bnd"], bat["balls"], 100)
    bowl = pr.groupby("bowling_team").agg(b_runs=("bowler_runs", "sum"), legal=("is_legal", "sum"),
                                          wkts=("bowler_wicket", "sum"), bowl_matches=("match_id", "nunique"))
    bowl["pressure_econ"] = _safe_div(bowl["b_runs"], bowl["legal"], 6)
    bowl["wkts_per_over"] = _safe_div(bowl["wkts"], bowl["legal"], 6)
    chases = d[d["innings"] == 2].groupby(["batting_team", "match_id"]).agg(pr=("pressure", "any"), won=("batting_won", "first"))
    chases = chases[chases["pr"]].groupby(level=0)["won"].agg(["sum", "size"])
    chases["pressure_chase_win_pct"] = _safe_div(chases["sum"], chases["size"], 100)
    out = bat.join(bowl, how="outer").join(chases[["size", "pressure_chase_win_pct"]].rename(columns={"size": "pressure_chases"}))
    out.index.name = "team"
    return out.reset_index()


def player_match_log(d: pd.DataFrame, player_id: int, kind: str) -> pd.DataFrame:
    """Per-match pressure vs usual log for one player."""
    key = "striker_id" if kind == "bat" else "bowler_id"
    x = d[d[key] == player_id]
    if x.empty:
        return pd.DataFrame()
    if kind == "bat":
        agg = dict(runs=("runs", "sum"), balls=("ball_faced", "sum"), boundaries=("bat_boundary", "sum"))
    else:
        agg = dict(runs=("bowler_runs", "sum"), balls=("is_legal", "sum"), wkts=("bowler_wicket", "sum"), dots=("bowler_dot", "sum"))
    g = x.groupby(["match_id", "pressure"]).agg(**agg).unstack("pressure", fill_value=0)
    g.columns = [f"{'p' if flag else 'u'}_{c}" for c, flag in g.columns]
    meta = x.groupby("match_id").agg(date=("match_date", "first"), comp=("comp_name", "first"),
                                     team=("batting_team" if kind == "bat" else "bowling_team", "first"),
                                     opp=("bowling_team" if kind == "bat" else "batting_team", "first"),
                                     won=("batting_won" if kind == "bat" else "bowling_won", "first"))
    g = meta.join(g).reset_index().sort_values("date")
    for c in [c for c in g.columns if c.startswith(("p_", "u_"))]:
        g[c] = g[c].fillna(0)
    if kind == "bat":
        g["p_sr"] = _safe_div(g.get("p_runs", 0), g.get("p_balls", 0), 100)
        g["u_sr"] = _safe_div(g.get("u_runs", 0), g.get("u_balls", 0), 100)
    else:
        g["p_econ"] = _safe_div(g.get("p_runs", 0), g.get("p_balls", 0), 6)
        g["u_econ"] = _safe_div(g.get("u_runs", 0), g.get("u_balls", 0), 6)
    return g


# --------------------------------------------------------------------------
# Bootstrap rank stability
# --------------------------------------------------------------------------
def bootstrap_top10(d: pd.DataFrame, kind: str, reps: int = 200, seed: int = 7,
                    min_balls: int = C.MIN_PRESSURE_BALLS, min_matches: int = C.MIN_PRESSURE_MATCHES) -> pd.DataFrame:
    """Resample matches (Poisson bootstrap) and recompute the score each time.

    Returns per-player share of replicates in the top 10 and median rank.
    """
    rng = np.random.default_rng(seed)
    if kind == "bat":
        key = "striker_id"
        x = d[d["ball_faced"]]
        pm = x.groupby([key, "match_id", "pressure"]).agg(r=("runs", "sum"), b=("ball_faced", "sum"), bd=("bat_boundary", "sum")).unstack("pressure", fill_value=0)
    else:
        key = "bowler_id"
        pm = d.groupby([key, "match_id", "pressure"]).agg(r=("bowler_runs", "sum"), b=("is_legal", "sum"), w=("bowler_wicket", "sum"), dt=("bowler_dot", "sum")).unstack("pressure", fill_value=0)
    pm.columns = [f"{c}_{'p' if f else 'u'}" for c, f in pm.columns]
    pm = pm.reset_index()
    for c in pm.columns:
        if c.endswith(("_p", "_u")):
            pm[c] = pm[c].astype(float)
    if pm.empty:
        return pd.DataFrame(columns=["player_id", "top10_share", "median_rank"])
    pid, pidx = np.unique(pm[key].to_numpy(), return_inverse=True)
    mid, midx = np.unique(pm["match_id"].to_numpy(), return_inverse=True)
    n_p = len(pid)
    top_counts = np.zeros(n_p)
    ranks = np.full((reps, n_p), np.nan)
    has_p = (pm.get("b_p", 0) > 0).astype(float).to_numpy()

    def s(col, w):
        return np.bincount(pidx, weights=pm[col].to_numpy() * w, minlength=n_p) if col in pm else np.zeros(n_p)

    for r in range(reps):
        w = rng.poisson(1.0, len(mid)).astype(float)[midx]
        bp, rp = s("b_p", w), s("r_p", w)
        matches = np.bincount(pidx, weights=has_p * w, minlength=n_p)
        elig = (bp >= min_balls) & (matches >= min_matches)
        if elig.sum() < 10:
            continue
        if kind == "bat":
            bu, ru, bd = s("b_u", w), s("r_u", w), s("bd_p", w)
            sr = _safe_div(rp, bp, 100)
            up = np.clip(sr - _safe_div(ru, bu, 100), -C.UPLIFT_CLIP, C.UPLIFT_CLIP)
            bnd = _safe_div(bd, bp, 100)
            p_up = mid_percentile(up[elig], up)
            p_up = np.where(np.isnan(p_up), 50.0, p_up)
            score = (C.BAT_WEIGHTS["sr"] * mid_percentile(sr[elig], sr) + C.BAT_WEIGHTS["uplift"] * p_up
                     + C.BAT_WEIGHTS["boundary"] * mid_percentile(bnd[elig], bnd))
        else:
            wk, dt = s("w_p", w), s("dt_p", w)
            econ = _safe_div(rp, bp, 6)
            wpb = _safe_div(wk, bp, 6)
            dots = _safe_div(dt, bp, 100)
            score = (C.BOWL_WEIGHTS["economy"] * mid_percentile(-econ[elig], -econ)
                     + C.BOWL_WEIGHTS["wkts"] * mid_percentile(wpb[elig], wpb)
                     + C.BOWL_WEIGHTS["dots"] * mid_percentile(dots[elig], dots))
        score = np.where(elig, score, -np.inf)
        order = np.argsort(-score, kind="stable")
        rk = np.empty(n_p)
        rk[order] = np.arange(1, n_p + 1)
        rk[~elig] = np.nan
        ranks[r] = rk
        top_counts[order[:10]] += 1
    valid = ~np.all(np.isnan(ranks), axis=1)
    n_valid = max(int(valid.sum()), 1)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(ranks[valid], axis=0)
            elig_share = np.mean(~np.isnan(ranks[valid]), axis=0)
    return pd.DataFrame({"player_id": pid, "top10_share": top_counts / n_valid * 100,
                         "median_rank": med, "eligible_share": elig_share * 100, "replicates": n_valid})


# --------------------------------------------------------------------------
# Recommendation engine
# --------------------------------------------------------------------------
def _fmt(v, nd=1):
    return "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{nd}f}"


def explain_batter(r: pd.Series) -> str:
    parts = [f"Strike rate {_fmt(r['p_sr'])} across {int(r['p_balls'])} pressure balls in {int(r['p_matches'])} matches"]
    if not np.isnan(r["u_sr"]):
        sign = "+" if r["uplift"] >= 0 else ""
        parts.append(f"{sign}{_fmt(r['uplift'])} vs usual {_fmt(r['u_sr'])}")
    parts.append(f"{_fmt(r['p_bnd_pct'])}% boundary balls")
    if r["qual_innings"] > 0:
        parts.append(f"kept pace (SR >= 150) in {int(r['kept_pace'])}/{int(r['qual_innings'])} pressure innings")
    return "; ".join(parts) + "."


def explain_bowler(r: pd.Series) -> str:
    parts = [f"Economy {_fmt(r['p_econ'], 2)} across {int(r['p_legal'])} pressure balls in {int(r['p_matches'])} matches"]
    if not np.isnan(r["u_econ"]):
        word = "better" if r["econ_improvement"] >= 0 else "worse"
        parts.append(f"{_fmt(abs(r['econ_improvement']), 2)} runs/over {word} than usual ({_fmt(r['u_econ'], 2)})")
    parts.append(f"{int(r['p_wkts'])} wickets ({_fmt(r['p_wpb'], 2)} per over)")
    parts.append(f"{_fmt(r['p_dot_pct'])}% dots")
    if r["qual_spells"] > 0:
        parts.append(f"held <= 9 RPO in {int(r['held'])}/{int(r['qual_spells'])} pressure spells")
    return "; ".join(parts) + "."


def recommendations(bat: pd.DataFrame, bowl: pd.DataFrame, n: int = 5) -> dict[str, pd.DataFrame]:
    """Evidence-based shortlists. No availability or auction claims are made."""
    out: dict[str, pd.DataFrame] = {}
    eb, ew = bat[bat["eligible"]], bowl[bowl["eligible"]]

    def tag(df, kind, why):
        df = df.copy()
        df["discipline"] = kind
        explain = explain_batter if kind == "Batting" else explain_bowler
        df["evidence"] = [explain(r) for _, r in df.iterrows()]
        df["why"] = why
        return df

    out["Best pressure batters"] = tag(eb.nlargest(n, "score"), "Batting", "Highest Pressure Reliability Score among eligible batters")
    out["Best pressure bowlers"] = tag(ew.nlargest(n, "score"), "Bowling", "Highest Pressure Reliability Score among eligible bowlers")

    cb = eb[eb["qual_innings"] >= 6].sort_values(["consistency", "score"], ascending=False).head(n)
    cw = ew[ew["qual_spells"] >= 6].sort_values(["consistency", "score"], ascending=False).head(n)
    out["Most consistent"] = pd.concat([
        tag(cb, "Batting", "Highest share of pressure innings scored at >= 9 an over (min 6 qualifying innings)"),
        tag(cw, "Bowling", "Highest share of pressure spells held to <= 9 an over (min 6 qualifying spells)")])

    if len(eb):
        hb = eb[eb["p_sr"] >= eb["p_sr"].median()].nlargest(n, "p_runs")
    else:
        hb = eb
    if len(ew):
        hw = ew[ew["p_econ"] <= ew["p_econ"].median()].nlargest(n, "p_wkts")
    else:
        hw = ew
    out["High-impact"] = pd.concat([
        tag(hb, "Batting", "Most pressure runs while striking at or above the eligible median"),
        tag(hw, "Bowling", "Most pressure wickets while conceding at or below the eligible median economy")])

    lb = bat[(bat["status"] == "Limited sample")].nlargest(n, "score")
    lw = bowl[(bowl["status"] == "Limited sample")].nlargest(n, "score")
    out["Limited sample - watch list"] = pd.concat([
        tag(lb, "Batting", "Strong provisional score but below the 40-ball / 6-match threshold"),
        tag(lw, "Bowling", "Strong provisional score but below the 40-ball / 6-match threshold")])

    def value(df, vol_col):
        if df.empty:
            return df
        return df[(df["score"] >= df["score"].quantile(0.7)) & (df[vol_col] <= df[vol_col].median())].nlargest(n, "score")

    out["Potential value picks"] = pd.concat([
        tag(value(eb, "o_balls"), "Batting", "Top-30% pressure score with below-median overall involvement in scope (less exposure, strong pressure record)"),
        tag(value(ew, "o_legal"), "Bowling", "Top-30% pressure score with below-median overall involvement in scope (less exposure, strong pressure record)")])
    return out
