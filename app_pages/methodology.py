import pandas as pd
import streamlit as st

from src import config as C
from src import state, ui

ds = state.get_dataset()
params = state.scope_params()
q = ds.quality

st.markdown("##### How the ratings are built - and how far to trust them")

with st.container(border=True):
    st.markdown("**:material/bolt: 1. Pressure definition**")
    st.markdown(
        f"A delivery is tagged **pressure** when, *before* it is bowled, the batting side is chasing in the **second innings** and either\n"
        f"- the required run rate is **>= {C.PRESSURE_RRR:g}** runs per over, or\n"
        f"- **{C.LATE_BALLS} or fewer legal balls** remain and the required run rate is **>= {C.LATE_RRR:g}**.\n\n"
        "Required run rate = (target - runs scored) x 6 / legal balls remaining. "
        "First-innings deliveries are never pressure deliveries; super overs are excluded. "
        "The same match state is used for batters (who must accelerate) and bowlers (who must deny)."
    )
    st.markdown("**Target and chase length**")
    cc = pd.DataFrame(list(q["chase_context_counts"].items()), columns=["Chase context", "Matches"])
    st.dataframe(cc, hide_index=True, width="content")
    st.caption("Revised targets/overs come from matches.csv (overs are stored as balls, e.g. 114 = 19 overs). "
               "Where the first innings ended early without being bowled out and no revision is recorded, the chase length is inferred "
               "as the first-innings length rounded up to whole overs. DLS games with no recorded revised target are excluded from pressure tagging "
               "(their in-game target is unknown) but still count toward usual performance.")

with st.container(border=True):
    st.markdown("**:material/rule: 2. Delivery handling**")
    st.dataframe(pd.DataFrame([
        ["Wide", "Not a ball faced; not a legal ball", "All wide runs", "Yes (stumped/run out on a wide)"],
        ["No-ball ('Overstep', 'other')", "Ball faced; not a legal ball", "Bat runs + 1 penalty run", "Run out only"],
        ["Bye / leg-bye", "Ball faced; legal", "Not charged", "-"],
        ["Bowler wickets", "-", "-", "Bowled, caught, LBW, stumped, hit wicket"],
        ["Not bowler wickets", "-", "-", "Run out, retired out, obstructing the field"],
    ], columns=["Event", "Ball counting", "Runs charged to bowler", "Wicket credited to bowler"]), hide_index=True)
    st.caption(f"'other' extras behave exactly like no-balls in the file (1 penalty run, re-bowled): with that rule {q['nonfinal_six_legal']:,} of "
               f"{q['nonfinal_overs']:,} overs that are not the last over of an innings contain exactly six legal balls. "
               "Dot ball (bowler) = legal ball with no runs charged to the bowler. Boundary ball (batter) = a four or six off the bat.")

with st.container(border=True):
    st.markdown("**:material/functions: 3. Pressure Reliability Score**")
    a, b = st.columns(2, gap="medium")
    with a:
        st.markdown("**Batters**")
        st.latex(r"\text{PRS}_{bat} = 0.55\,P(\text{SR}_{p}) + 0.25\,P(\text{clip}(\text{SR}_{p}-\text{SR}_{u},\,-40,\,40)) + 0.20\,P(\text{Bnd\%}_{p})")
    with b:
        st.markdown("**Bowlers**")
        st.latex(r"\text{PRS}_{bowl} = 0.45\,P(-\text{Econ}_{p}) + 0.35\,P(\tfrac{6\,W_{p}}{\text{legal}_{p}}) + 0.20\,P(\text{Dot\%}_{p})")
    st.markdown(
        "- *P(x)* is the mid-rank percentile of x among **eligible players of the same discipline** in the current filter scope "
        "(count below + half of ties, / n x 100). Batting and bowling scores are never compared with each other.\n"
        "- Subscript *p* = pressure deliveries, *u* = usual (all non-pressure deliveries in scope).\n"
        "- The score is a **relative index from 0 to 100, not a probability**. A score of 90 means the player out-performs most "
        "of the eligible pool on the weighted components - not a 90% chance of success.\n"
        "- If a batter has no usual baseline, the uplift percentile is set to a neutral 50 and the row is flagged.\n"
        f"- Eligibility: **>= {C.MIN_PRESSURE_BALLS} pressure balls** (balls faced / legal balls bowled) in **>= {C.MIN_PRESSURE_MATCHES} matches**. "
        f"Players with {C.EMERGING_MIN_BALLS}+ balls but below that are shown as *Limited sample* with a provisional score against the eligible distribution."
    )
    st.markdown("**Consistency and context metrics (shown, not scored)**")
    st.markdown(
        f"- Batting *kept pace %*: share of pressure innings with >= {C.CONSISTENCY_MIN_BAT_BALLS} balls at SR >= {C.CONSISTENCY_BAT_SR:g} (9 an over, the pressure threshold).\n"
        f"- Bowling *held %*: share of pressure spells with >= {C.CONSISTENCY_MIN_BOWL_BALLS} legal balls at economy <= {C.CONSISTENCY_BOWL_ECON:g}.\n"
        "- Top-10 stability: share of 200 Poisson match-bootstrap resamples in which the player ranks in the top 10."
    )

with st.container(border=True):
    st.markdown("**:material/verified: 4. Data validation summary**")
    rec = state.compute_reconciliation()
    with st.container(horizontal=True, gap="small"):
        st.metric("Raw deliveries", f"{q['raw_rows']:,}", border=True)
        st.metric("Super-over rows excluded", f"{q['super_over_rows_excluded']:,}", border=True)
        st.metric("Matches with ball data", f"{q['matches_with_balls']:,} / {q['matches_in_file']:,}",
                  delta=f"{q['matches_without_balls']} abandoned, no balls", delta_color="off", delta_arrow="off", border=True)
        st.metric("Run-margin results reproduced", f"{rec['run_margin_exact']} / {rec['run_margin_results']}", border=True,
                  help="Reconstructed innings totals vs 'won by N runs' in matches.csv (non-revised games).")
        st.metric("Wicket wins: chaser passed target", f"{rec['wicket_chaser_ahead']} / {rec['wicket_results']}", border=True)
    dup_names = sorted(ds.players.loc[ds.players["name"].duplicated(keep=False), "name"].unique())
    st.markdown(
        f"- Joins: {q['orphan_matches']} match IDs in ball_by_ball.csv are missing from matches.csv; "
        f"{q['orphan_players']} player IDs are missing from the squad mapping.\n"
        f"- Player identity is keyed on `player_id`. {q['duplicate_name_ids']} IDs share a name with another ID "
        f"({', '.join(dup_names)}) and are disambiguated by team in the UI.\n"
        "- Season = calendar year of match_date (e.g. a '2022/23' series match played in Jan 2023 counts as 2023).\n"
        "- The independent script `scripts/validate.py` recomputes pressure tags and the top-10 tables from the raw CSV without using the app code."
    )
    mism = pd.concat([rec["run_margin_mismatches"], rec["wicket_mismatches"]])
    if not mism.empty:
        with st.expander(f"{len(mism)} results not reproduced exactly"):
            st.dataframe(mism, hide_index=True)
            st.caption("These are rain-affected games whose revised target is missing from matches.csv.")

with st.container(border=True):
    st.markdown("**:material/stacked_line_chart: 5. Robustness checks for the current scope**")
    if not params[0] or not params[1]:
        ui.empty_state("Select at least one season and one competition type.")
    else:
        S = state.compute_scope(params)
        tab1, tab2 = st.tabs(["Rank stability (bootstrap)", "Definition sensitivity"])
        with tab1:
            st.caption("Matches are resampled with replacement 200 times and every score is recomputed. Low stability = the rank depends on a few games.")
            c1, c2 = st.columns(2, gap="medium")
            for col, kind, label in ((c1, "bat", "Batters"), (c2, "bowl", "Bowlers")):
                with col:
                    t = S[kind][S[kind]["eligible"]].head(10)
                    stab = state.compute_stability(params, kind)
                    t = t.merge(stab, on="player_id", how="left")[["rank", "display_name", "score", "top10_share", "median_rank", "eligible_share"]]
                    st.markdown(f"**{label}**")
                    st.dataframe(t, hide_index=True, column_config={
                        "rank": ui.CC.NumberColumn("Rank", format="%d"), "display_name": "Player",
                        "score": ui.CC.NumberColumn("Score", format="%.1f"),
                        "top10_share": ui.CC.ProgressColumn("Top-10 %", min_value=0, max_value=100, format="%.0f%%"),
                        "median_rank": ui.CC.NumberColumn("Median rank", format="%.1f"),
                        "eligible_share": ui.CC.NumberColumn("Eligible in %", format="%.0f%%",
                                                             help="Share of resamples in which the player still met the eligibility threshold.")})
        with tab2:
            st.caption("Top-10 lists recomputed under alternative pressure thresholds; overlap is measured against the specified definition.")
            if st.toggle("Run sensitivity analysis", key="meth_sens"):
                sens = state.compute_sensitivity(params)
                st.dataframe(sens, hide_index=True, column_config={
                    "scenario": "Scenario", "discipline": "Discipline",
                    "pressure_deliveries": ui.CC.NumberColumn("Pressure deliveries", format="%d"),
                    "eligible": ui.CC.NumberColumn("Eligible", format="%d"),
                    "top10_overlap": ui.CC.ProgressColumn("Top-10 overlap", min_value=0, max_value=10, format="%d / 10"),
                    "top10": ui.CC.TextColumn("Top 10", width="large")})
                ui.download_csv(sens, "rr_sensitivity.csv", key="dl_sens")

with st.container(border=True):
    st.markdown("**:material/warning: 6. Limitations**")
    st.markdown(
        "- **Broad pressure band.** Modern T20 targets are high, so a large share of chase deliveries qualifies (any target of 181+ starts above RRR 9). "
        "The definition also includes lost-cause chases where the RRR is very high; the *close chases only* scenario above shows the effect of excluding them.\n"
        "- **Phase confounding.** Pressure balls cluster in the death overs where scoring is naturally faster, so batting uplift partly reflects phase, "
        "and bowlers who mostly bowl at the death have higher usual economies.\n"
        "- **Mixed competition strength.** T20Is include Associate nations; use *Full Members & IPL only* to test whether a ranking survives stronger opposition.\n"
        "- **Small samples.** 40 balls is roughly seven overs. Percentile ranks near the top are separated by small differences - see the bootstrap stability column.\n"
        "- **Weak cross-competition transfer.** For players eligible in both IPL and T20I, pressure numbers in one competition barely predict the other "
        "(see *Teams & competitions > IPL vs T20I*). Pressure performance at these sample sizes is noisy; treat ranks as evidence, not certainty.\n"
        "- **DLS timing.** When a target was revised mid-chase, the revised target is applied to the whole innings because the interruption point is not recorded.\n"
        "- **Roles are inferred** from playing patterns and may differ from official designations.\n"
        "- **No availability data.** The squad mapping shows the latest recorded IPL squad only; it says nothing about retention, auction status or fitness."
    )
