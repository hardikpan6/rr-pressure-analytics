import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from src import metrics as M
from src import state, ui

ds = state.get_dataset()
params = state.scope_params()
if not params[0] or not params[1]:
    ui.empty_state("Select at least one season and one competition type.")
    st.stop()
S = state.compute_scope(params)
bat, bowl = S["bat"], S["bowl"]
if bat.empty and bowl.empty:
    ui.empty_state()
    st.stop()

# Options: players with any pressure involvement in scope, best-rated first.
opts = pd.concat([bat[bat["p_balls"] > 0][["player_id", "display_name", "score"]],
                  bowl[bowl["p_legal"] > 0][["player_id", "display_name", "score"]]])
opts = opts.sort_values("score", ascending=False).drop_duplicates("player_id")
names = dict(zip(opts["player_id"].astype(int), opts["display_name"]))
ids = list(names)
if st.session_state.get("profile_player") not in names:
    st.session_state.profile_player = ids[0]
pid = st.selectbox("Player", ids, format_func=lambda i: names.get(i, str(i)), key="profile_player",
                   help="Players with at least one pressure delivery in the current scope.")

prow = ds.players.set_index("player_id").loc[pid]
b = bat[bat["player_id"] == pid]
w = bowl[bowl["player_id"] == pid]
b = b.iloc[0] if len(b) else None
w = w.iloc[0] if len(w) else None

with st.container(horizontal=True, gap="small", vertical_alignment="center"):
    st.subheader(prow["display_name"])
    st.badge(prow["role"], icon=":material/badge:", color="primary")
    if isinstance(prow.get("batting_style"), str):
        st.badge(prow["batting_style"], color="blue")
    if isinstance(prow.get("bowling_style"), str):
        st.badge(prow["bowling_style"], color="violet")
    if isinstance(prow.get("latest_ipl_squad"), str):
        st.badge(f"{ds.quality['latest_ipl']} squad: {prow['latest_ipl_squad']}", icon=":material/groups:", color="gray")
teams_txt = (b["teams_played"] if b is not None and isinstance(b.get("teams_played"), str) else
             w["teams_played"] if w is not None and isinstance(w.get("teams_played"), str) else "n/a")
st.caption(f"Teams in scope: {teams_txt}. Role is data-derived.")


def status_txt(r):
    if r is None:
        return "No sample"
    return f"Rank #{int(r['rank'])}" if r["eligible"] else r["status"]


f = state.filter_deliveries(ds, params)
c1, c2 = st.columns(2, gap="medium")
with c1:
    with st.container(border=True):
        st.markdown("**:material/sports_cricket: Batting under pressure**")
        if b is None or b["p_balls"] == 0:
            st.caption("No pressure balls faced in scope.")
        else:
            st.badge(status_txt(b), color="green" if b["eligible"] else "orange")
            with st.container(horizontal=True, gap="small"):
                st.metric("Score" + ("" if b["eligible"] else " (provisional)"), ui.fmt_num(b["score"]), border=True)
                st.metric("Pressure SR", ui.fmt_num(b["p_sr"]), delta=None if pd.isna(b["uplift"]) else f"{b['uplift']:+.1f} vs usual", border=True)
                st.metric("Pressure runs", f"{int(b['p_runs'])}", delta=f"{int(b['p_balls'])} balls", delta_color="off", delta_arrow="off", border=True)
            with st.container(horizontal=True, gap="small"):
                st.metric("Usual SR", ui.fmt_num(b["u_sr"]), border=True)
                st.metric("Boundary %", ui.fmt_num(b["p_bnd_pct"], 1, "%"), border=True)
                st.metric("Kept pace", f"{int(b['kept_pace'])}/{int(b['qual_innings'])}", border=True)
            st.caption(M.explain_batter(b))
with c2:
    with st.container(border=True):
        st.markdown("**:material/sports_baseball: Bowling under pressure**")
        if w is None or w["p_legal"] == 0:
            st.caption("No pressure deliveries bowled in scope.")
        else:
            st.badge(status_txt(w), color="green" if w["eligible"] else "orange")
            with st.container(horizontal=True, gap="small"):
                st.metric("Score" + ("" if w["eligible"] else " (provisional)"), ui.fmt_num(w["score"]), border=True)
                st.metric("Pressure econ", ui.fmt_num(w["p_econ"], 2),
                          delta=None if pd.isna(w["econ_improvement"]) else f"{-w['econ_improvement']:+.2f} vs usual",
                          delta_color="inverse", border=True)
                st.metric("Pressure wkts", f"{int(w['p_wkts'])}", delta=f"{int(w['p_legal'])} balls", delta_color="off", delta_arrow="off", border=True)
            with st.container(horizontal=True, gap="small"):
                st.metric("Usual econ", ui.fmt_num(w["u_econ"], 2), border=True)
                st.metric("Dot %", ui.fmt_num(w["p_dot_pct"], 1, "%"), border=True)
                st.metric("Held <= 9 RPO", f"{int(w['held'])}/{int(w['qual_spells'])}", border=True)
            st.caption(M.explain_bowler(w))


def bootstrap_ci(log: pd.DataFrame, num: str, den: str, scale: float, reps: int = 2000) -> tuple[float, float]:
    x = log[log[den] > 0]
    if len(x) < 3:
        return (np.nan, np.nan)
    rng = np.random.default_rng(11)
    idx = rng.integers(0, len(x), size=(reps, len(x)))
    r, bl = x[num].to_numpy()[idx].sum(1), x[den].to_numpy()[idx].sum(1)
    vals = r / bl * scale
    return tuple(np.percentile(vals, [5, 95]))


kinds = [k for k, r in (("bat", b), ("bowl", w)) if r is not None and (r["p_balls"] if k == "bat" else r["p_legal"]) > 0]
for kind in kinds:
    log = M.player_match_log(f[kind], pid, kind)
    if log.empty:
        continue
    is_bat = kind == "bat"
    with st.container(border=True):
        st.markdown(f"**{'Batting' if is_bat else 'Bowling'} match log - pressure involvement**")
        lo, hi = bootstrap_ci(log, "p_runs", "p_balls", 100 if is_bat else 6)
        if not np.isnan(lo):
            st.caption(f"90% bootstrap interval (resampling pressure matches) for pressure {'SR' if is_bat else 'economy'}: "
                       f"{lo:.{1 if is_bat else 2}f} to {hi:.{1 if is_bat else 2}f}.")
        pl = log[log["p_balls"] > 0].copy()
        pl["date"] = pd.to_datetime(pl["date"])
        if is_bat:
            chart = alt.Chart(pl).mark_bar(color=ui.PINK, cornerRadius=2, size=7).encode(
                x=alt.X("date:T", title=None), y=alt.Y("p_runs:Q", title="Pressure runs"),
                tooltip=[alt.Tooltip("date:T"), "comp", "opp", "p_runs", "p_balls", alt.Tooltip("p_sr:Q", format=".1f"), "won"])
        else:
            chart = alt.Chart(pl).mark_circle(color=ui.BLUE).encode(
                x=alt.X("date:T", title=None), y=alt.Y("p_econ:Q", title="Pressure economy"),
                size=alt.Size("p_wkts:Q", title="Wickets", scale=alt.Scale(range=[40, 400])),
                tooltip=[alt.Tooltip("date:T"), "comp", "opp", "p_balls", "p_runs", "p_wkts", alt.Tooltip("p_econ:Q", format=".2f"), "won"])
        st.altair_chart(chart.properties(height=240).interactive())
        show = log.rename(columns={"won": "team_won"})
        log_cfg = {
            "match_id": ui.CC.NumberColumn("Match", format="%d"), "date": ui.CC.DateColumn("Date"),
            "comp": "Competition", "team": "Team", "opp": "Opponent", "team_won": ui.CC.CheckboxColumn("Team won"),
            "p_runs": ui.CC.NumberColumn("Pressure runs" if is_bat else "Pressure runs conceded", format="%d"),
            "p_balls": ui.CC.NumberColumn("Pressure balls", format="%d"),
            "u_runs": ui.CC.NumberColumn("Usual runs" if is_bat else "Usual runs conceded", format="%d"),
            "u_balls": ui.CC.NumberColumn("Usual balls", format="%d"),
            "p_boundaries": ui.CC.NumberColumn("Pressure 4s+6s", format="%d"), "u_boundaries": ui.CC.NumberColumn("Usual 4s+6s", format="%d"),
            "p_wkts": ui.CC.NumberColumn("Pressure wkts", format="%d"), "u_wkts": ui.CC.NumberColumn("Usual wkts", format="%d"),
            "p_dots": ui.CC.NumberColumn("Pressure dots", format="%d"), "u_dots": ui.CC.NumberColumn("Usual dots", format="%d"),
            "p_sr": ui.CC.NumberColumn("Pressure SR", format="%.1f"), "u_sr": ui.CC.NumberColumn("Usual SR", format="%.1f"),
            "p_econ": ui.CC.NumberColumn("Pressure econ", format="%.2f"), "u_econ": ui.CC.NumberColumn("Usual econ", format="%.2f"),
        }
        order = [c for c in ("date", "comp", "team", "opp", "team_won", "p_runs", "p_balls", "p_sr", "p_wkts", "p_econ", "p_dots",
                             "p_boundaries", "u_runs", "u_balls", "u_sr", "u_wkts", "u_econ", "match_id") if c in show.columns]
        st.dataframe(show.sort_values("date", ascending=False), hide_index=True, height=260, column_order=order, column_config=log_cfg)
        ui.download_csv(show, f"{prow['name'].replace(' ', '_')}_{kind}_match_log.csv", key=f"dl_log_{kind}")

with st.container(border=True):
    st.markdown("**Phase breakdown - pressure vs non-pressure**")
    rows = []
    if "bat" in kinds:
        x = f["bat"][f["bat"]["striker_id"] == pid]
        g = x.groupby(["phase", "pressure"]).agg(r=("runs", "sum"), bl=("ball_faced", "sum")).reset_index()
        g["value"] = np.where(g["bl"] > 0, g["r"] / g["bl"].replace(0, np.nan) * 100, np.nan)
        rows.append(g.assign(metric="Batting SR"))
    if "bowl" in kinds:
        x = f["bowl"][f["bowl"]["bowler_id"] == pid]
        g = x.groupby(["phase", "pressure"]).agg(r=("bowler_runs", "sum"), bl=("is_legal", "sum")).reset_index()
        g["value"] = np.where(g["bl"] > 0, g["r"] / g["bl"].replace(0, np.nan) * 6, np.nan)
        rows.append(g.assign(metric="Bowling economy"))
    if rows:
        ph = pd.concat(rows)
        ph["state"] = np.where(ph["pressure"], "Pressure", "Non-pressure")
        ph = ph.sort_values("phase", key=lambda s: s.map({"Powerplay (1-6)": 0, "Middle (7-15)": 1, "Death (16-20)": 2}))
        cols = st.columns(len(rows), gap="medium")
        for col, (metric, grp) in zip(cols, ph.groupby("metric")):
            with col:
                st.altair_chart(ui.grouped_bars(grp, "phase", "value", "state", metric, height=240))
                st.caption("Balls per bar: " + ", ".join(f"{p} {s.lower()}: {int(n)}" for p, s, n in grp[["phase", "state", "bl"]].itertuples(index=False)))
