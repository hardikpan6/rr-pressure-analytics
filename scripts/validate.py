"""Independent validation of the dashboard's analytics.

Re-derives pressure tags and top-10 statistics from the raw CSV files using a
row-by-row loop (no code shared with src/data.py or src/metrics.py), compares
the results with the app engine, and writes docs/DATA_VALIDATION.md plus the
official top-10 CSVs.

Run from the project root:  python scripts/validate.py
"""

from __future__ import annotations

import math
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
DOCS = ROOT / "docs"

ILLEGAL = {"wide", "Overstep", "other"}
BOWLER_WKTS = {"Bowled", "Caught", "LBW", "Stump", "Hit Wicket"}


def independent_pressure() -> pd.DataFrame:
    bbb = pd.read_csv(DATA / "ball_by_ball.csv", low_memory=False)
    matches = pd.read_csv(DATA / "matches.csv").set_index("match_id")
    bbb = bbb[bbb["innings"].isin([1, 2])].sort_values(["match_id", "innings", "innings_ball_num"])

    inn1 = defaultdict(lambda: [0, 0, 0])  # runs, wickets, legal balls
    for r in bbb[bbb["innings"] == 1].itertuples(index=False):
        s = inn1[r.match_id]
        s[0] += r.runs + r.extras1_runs + r.extras_2_runs
        s[1] += int(r.is_wicket)
        s[2] += int(r.extras_type not in ILLEGAL)

    flags = []
    state = {}
    for r in bbb.itertuples(index=False):
        if r.innings != 2:
            flags.append(False)
            continue
        if r.match_id not in state:
            m = matches.loc[r.match_id]
            runs1, wk1, legal1 = inn1[r.match_id]
            dls = bool(re.search(r"D/L|DLS", str(m["result"]), re.I))
            target = m["revised_target"] if not pd.isna(m["revised_target"]) else runs1 + 1
            if not pd.isna(m["second_inn_revised_overs"]):
                balls = m["second_inn_revised_overs"]
            elif wk1 < 10 and 0 < legal1 < 120:
                balls = math.ceil(legal1 / 6) * 6
            else:
                balls = 120
            usable = not (dls and pd.isna(m["revised_target"]))
            state[r.match_id] = {"target": target, "balls": balls, "ok": usable, "runs": 0, "legal": 0}
        s = state[r.match_id]
        need, left = s["target"] - s["runs"], s["balls"] - s["legal"]
        p = False
        if s["ok"] and need > 0 and left > 0:
            rrr = need * 6 / left
            p = rrr >= 9.0 or (left <= 30 and rrr >= 7.5)
        flags.append(p)
        s["runs"] += r.runs + r.extras1_runs + r.extras_2_runs
        s["legal"] += int(r.extras_type not in ILLEGAL)
    bbb = bbb.assign(pressure_ind=flags)
    return bbb.merge(pd.read_csv(DATA / "matches.csv")[["match_id", "comp_id", "match_date"]], on="match_id")


def independent_tables(b: pd.DataFrame, comps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    grp = comps.set_index("comp_id").apply(lambda r: "T20I" if r.match_format == "T20I" else ("IPL" if str(r.comp_name).startswith("IPL") else "Other"), axis=1)
    b = b[b["comp_id"].map(grp).isin(["IPL", "T20I"])]
    wide = b["extras_type"] == "wide"
    nob = b["extras_type"].isin(["Overstep", "other"])
    b = b.assign(faced=~wide, legal=~(wide | nob),
                 conceded=b["runs"] + np.where(wide | nob, b["extras1_runs"], 0),
                 bw=b["is_wicket"] & b["dismissal_type"].isin(BOWLER_WKTS),
                 bnd=(~wide) & ((b["is_four"] & (b["runs"] == 4)) | (b["is_six"] & (b["runs"] == 6))))
    b = b.assign(dot=b["legal"] & (b["conceded"] == 0))

    def bat(x):
        return pd.Series({"runs": x["runs"].sum(), "balls": x["faced"].sum(), "bnd": x["bnd"].sum(),
                          "matches": x.loc[x["faced"], "match_id"].nunique()})

    P, U = b[b["pressure_ind"]], b[~b["pressure_ind"]]
    bt = P.groupby("striker_id").apply(bat, include_groups=False).join(
        U.groupby("striker_id").agg(u_runs=("runs", "sum"), u_balls=("faced", "sum")), how="left")
    bt["sr"] = bt["runs"] / bt["balls"] * 100
    bt["u_sr"] = bt["u_runs"] / bt["u_balls"] * 100
    bt["bnd_pct"] = bt["bnd"] / bt["balls"] * 100
    bt = bt[(bt["balls"] >= 40) & (bt["matches"] >= 6)].copy()
    n = len(bt)
    pr = lambda s: (s.rank(method="average") - 0.5) / n * 100  # noqa: E731
    up = (bt["sr"] - bt["u_sr"]).clip(-40, 40)
    bt["score"] = 0.55 * pr(bt["sr"]) + 0.25 * pr(up).fillna(50) + 0.20 * pr(bt["bnd_pct"])

    bw = P.groupby("bowler_id").agg(legal=("legal", "sum"), runs=("conceded", "sum"), wkts=("bw", "sum"),
                                    dots=("dot", "sum"), matches=("match_id", "nunique"))
    bw = bw.join(U.groupby("bowler_id").agg(u_legal=("legal", "sum"), u_runs=("conceded", "sum")), how="left")
    bw["econ"] = bw["runs"] / bw["legal"] * 6
    bw["u_econ"] = bw["u_runs"] / bw["u_legal"] * 6
    bw["wpb"] = bw["wkts"] / bw["legal"] * 6
    bw["dot_pct"] = bw["dots"] / bw["legal"] * 100
    bw = bw[(bw["legal"] >= 40) & (bw["matches"] >= 6)].copy()
    n = len(bw)
    bw["score"] = 0.45 * pr(-bw["econ"]) + 0.35 * pr(bw["wpb"]) + 0.20 * pr(bw["dot_pct"])
    return bt.sort_values("score", ascending=False), bw.sort_values("score", ascending=False)


def md_table(df: pd.DataFrame, floatfmt: dict | None = None) -> str:
    floatfmt = floatfmt or {}
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        vals = []
        for c in cols:
            v = r[c]
            if isinstance(v, (float, np.floating)):
                vals.append("n/a" if np.isnan(v) else format(v, floatfmt.get(c, ".1f")))
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def main() -> int:
    from src import metrics as M
    from src.data import build_dataset, reconcile_results

    print("Building app dataset...")
    ds = build_dataset()
    d = ds.deliveries
    print("Recomputing pressure independently (row-by-row)...")
    ind = independent_pressure()

    key = ["match_id", "innings", "innings_ball_num"]
    cmp = d[key + ["pressure"]].merge(ind[key + ["pressure_ind"]], on=key, how="outer", indicator=True)
    join_ok = (cmp["_merge"] == "both").all()
    flag_mismatch = int((cmp["pressure"] != cmp["pressure_ind"]).sum())
    dup_keys = int(d.duplicated(key).sum())

    scope = d[d["comp_group"].isin(["IPL", "T20I"])]
    bat = M.batting_table(scope, ds.players)
    bowl = M.bowling_table(scope, ds.players)
    ib, iw = independent_tables(ind, pd.read_csv(DATA / "competitions.csv"))

    eb, ew = bat[bat["eligible"]].set_index("player_id"), bowl[bowl["eligible"]].set_index("player_id")
    same_bat_pool = set(eb.index) == set(ib.index)
    same_bowl_pool = set(ew.index) == set(iw.index)
    bat_diff = (eb.loc[ib.index, ["p_runs", "p_balls", "p_sr", "score"]].to_numpy()
                - ib[["runs", "balls", "sr", "score"]].to_numpy())
    bowl_diff = (ew.loc[iw.index, ["p_wkts", "p_legal", "p_econ", "p_dot_pct", "score"]].to_numpy()
                 - iw[["wkts", "legal", "econ", "dot_pct", "score"]].to_numpy())
    max_bat_diff = float(np.nanmax(np.abs(bat_diff)))
    max_bowl_diff = float(np.nanmax(np.abs(bowl_diff)))
    top_bat_same = list(eb.head(10).index) == list(ib.head(10).index)
    top_bowl_same = list(ew.head(10).index) == list(iw.head(10).index)

    stab_b = M.bootstrap_top10(scope, "bat", reps=200)
    stab_w = M.bootstrap_top10(scope, "bowl", reps=200)
    rec = reconcile_results(ds)
    q = ds.quality

    checks = [
        ("Every delivery row matched between engine and independent recomputation", join_ok),
        ("No duplicate (match, innings, ball) keys", dup_keys == 0),
        ("Pressure tags identical (engine vs independent loop)", flag_mismatch == 0),
        ("Batting players unique in leaderboard", not bat["player_id"].duplicated().any()),
        ("Bowling players unique in leaderboard", not bowl["player_id"].duplicated().any()),
        ("Eligible batter pool identical", same_bat_pool),
        ("Eligible bowler pool identical", same_bowl_pool),
        ("Batting stats & scores match (max abs diff < 1e-6)", max_bat_diff < 1e-6),
        ("Bowling stats & scores match (max abs diff < 1e-6)", max_bowl_diff < 1e-6),
        ("Top-10 batters identical and in the same order", top_bat_same),
        ("Top-10 bowlers identical and in the same order", top_bowl_same),
        ("All match IDs in ball_by_ball join to matches.csv", q["orphan_matches"] == 0),
        ("All player IDs join to the squad mapping", q["orphan_players"] == 0),
    ]
    all_ok = all(ok for _, ok in checks)

    top_b = bat[bat["eligible"]].head(10).merge(stab_b, on="player_id", how="left")
    top_w = bowl[bowl["eligible"]].head(10).merge(stab_w, on="player_id", how="left")
    tb = top_b[["rank", "display_name", "team", "score", "p_runs", "p_balls", "p_sr", "u_sr", "uplift", "p_bnd_pct", "p_matches", "top10_share"]].copy()
    tw = top_w[["rank", "display_name", "team", "score", "p_wkts", "p_legal", "p_econ", "u_econ", "p_wpb", "p_dot_pct", "p_matches", "top10_share"]].copy()
    tb["rank"] = tb["rank"].astype(int)
    tw["rank"] = tw["rank"].astype(int)
    for c in ("p_runs", "p_balls", "p_matches"):
        tb[c] = tb[c].astype(int)
    for c in ("p_wkts", "p_legal", "p_matches"):
        tw[c] = tw[c].astype(int)
    DOCS.mkdir(exist_ok=True)
    tb.to_csv(DOCS / "top10_batters.csv", index=False)
    tw.to_csv(DOCS / "top10_bowlers.csv", index=False)

    pr_share = scope["pressure"].sum() / max(1, (scope["innings"] == 2).sum()) * 100
    ghost = int((ind["dismissed_player_id"].notna() & ~ind["is_wicket"]).sum())
    mism = pd.concat([rec["run_margin_mismatches"], rec["wicket_mismatches"]])
    cc = pd.DataFrame(list(q["chase_context_counts"].items()), columns=["Chase context", "Matches"])

    report = f"""# Data validation summary

_Auto-generated by `scripts/validate.py` on {date.today().isoformat()}. Re-run it after any data or code change._

Overall result: **{"ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED"}**

## 1. Independent recomputation checks

The script recomputes every pressure tag with a row-by-row loop over the raw CSV and rebuilds the eligible
pools, statistics and scores with separate pandas code, then compares them with the dashboard engine
(`src/data.py`, `src/metrics.py`). Default scope: IPL + T20I, 2022-2026, 40 balls / 6 matches.

| Check | Result |
|---|---|
""" + "\n".join(f"| {name} | {'PASS' if ok else 'FAIL'} |" for name, ok in checks) + f"""

- Pressure-tag mismatches: {flag_mismatch}
- Largest absolute difference, batting stats/scores: {max_bat_diff:.2e}
- Largest absolute difference, bowling stats/scores: {max_bowl_diff:.2e}

## 2. Raw data profile

| Item | Value |
|---|---|
| Raw delivery rows | {q['raw_rows']:,} |
| Super-over rows excluded (innings 3-4) | {q['super_over_rows_excluded']} |
| Delivery rows analysed | {q['analysed_rows']:,} |
| Matches in matches.csv | {q['matches_in_file']} |
| Matches with ball-by-ball data | {q['matches_with_balls']} |
| Matches without ball data (all "Match Abandoned") | {q['matches_without_balls']} |
| Non-final overs with exactly 6 legal balls | {q['nonfinal_six_legal']:,} / {q['nonfinal_overs']:,} |
| Player IDs sharing a name with another ID | {q['duplicate_name_ids']} |
| Pressure deliveries (IPL + T20I scope) | {int(scope['pressure'].sum()):,} ({pr_share:.1f}% of chase deliveries) |
| Eligible batters / bowlers | {int(bat['eligible'].sum())} / {int(bowl['eligible'].sum())} |

### Chase context (matches with ball data)

{md_table(cc)}

## 3. Reconciliation with official results

Innings totals rebuilt from the deliveries (bat runs + all extras) were compared with the result text in matches.csv
for games with no recorded revision, tie or super over.

- "Won by N runs" results reproduced exactly: **{rec['run_margin_exact']} / {rec['run_margin_results']}**
- "Won by N wickets" results where the chaser passed the first-innings total: **{rec['wicket_chaser_ahead']} / {rec['wicket_results']}**

{"Results not reproduced (rain-affected games whose revised target is missing from matches.csv):" if len(mism) else ""}

{md_table(mism) if len(mism) else ""}

## 4. Official top-10 lists (default scope) with bootstrap stability

`top10_share` = share of 200 Poisson match-bootstrap resamples in which the player ranked in the top 10.

### Batters

{md_table(tb, {"score": ".1f", "p_sr": ".1f", "u_sr": ".1f", "uplift": "+.1f", "p_bnd_pct": ".1f", "top10_share": ".0f"})}

### Bowlers

{md_table(tw, {"score": ".1f", "p_econ": ".2f", "u_econ": ".2f", "p_wpb": ".2f", "p_dot_pct": ".1f", "top10_share": ".0f"})}

## 5. Data-handling decisions

- `extras_type = 'other'` is treated as a no-ball (always 1 penalty run, ball re-bowled).
- Revised overs in matches.csv are stored in balls (e.g. 114 = 19 overs).
- {q['chase_context_counts'].get('DLS target unknown (excluded)', 0)} DLS games with no recorded revised target are excluded from pressure tagging.
- Player identity uses `player_id`; duplicated names are disambiguated by team in the UI.
- {ghost} rows carry a `dismissed_player_id` with `is_wicket = False` (no dismissal type); they are not counted as dismissals.
"""
    (DOCS / "DATA_VALIDATION.md").write_text(report, encoding="utf-8")
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"Wrote {DOCS / 'DATA_VALIDATION.md'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
