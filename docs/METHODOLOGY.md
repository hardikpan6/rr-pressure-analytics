# Methodology - Pressure Reliability Score

This document explains how pressure is defined, how players are rated, and how far the ratings can be trusted.
The dashboard's *Methodology & validation* page shows the same content with live numbers for any filter scope.
Figures quoted below are for the default scope (IPL + T20I, 2022-2026, 40 balls / 6 matches) and are reproduced by
`python scripts/validate.py`.

## 1. Data preparation

| Step | Treatment |
|---|---|
| Joins | `ball_by_ball.match_id` -> `matches.match_id` -> `competitions.comp_id`; team names from `teams.csv`; squads from `competition_team_player_mapping.csv`; keeper flags from `playing_eleven.csv`. All joins verified complete. |
| Innings | Innings 1-2 analysed; super overs (innings 3-4, 38 rows) excluded. |
| Legal balls | Wides, `Overstep` and `other` are illegal deliveries. `other` always carries a 1-run penalty and is re-bowled, i.e. it is a no-ball. With this rule 30,622 of 30,626 non-final overs contain exactly six legal balls. |
| Batter balls faced | Every delivery except wides (no-balls count as faced). |
| Bowler runs | Bat runs + all wide runs + the no-ball penalty. Byes and leg-byes are never charged. |
| Bowler wickets | Bowled, caught, LBW, stumped, hit wicket. Run outs, retired out and obstructing the field are not credited. |
| Boundary ball | A four or six off the bat (not boundary byes or wides). |
| Competition groups | IPL (5 seasons), T20I (men's internationals), Other T20 (A-team / emerging tournaments, excluded by default). |
| Season | Calendar year of `match_date`. |
| Identity | `player_id`. Abdul Samad, Basil Hameed and Haider Ali each map to two IDs; they are shown with their team. |

## 2. Pressure definition

Before each second-innings delivery:

```
runs_needed  = target - runs scored so far (bat runs + all extras)
balls_left   = chase length (legal balls) - legal balls already bowled
RRR          = runs_needed x 6 / balls_left
pressure     = RRR >= 9.0  OR  (balls_left <= 30 AND RRR >= 7.5)
```

- **Target** = `revised_target` when recorded, otherwise first-innings total + 1.
- **Chase length** = `second_inn_revised_overs` (stored in balls, e.g. 114 = 19 overs) when recorded. If the first
  innings ended short of 120 legal balls without being bowled out and no revision is recorded, the chase length is
  inferred as the first-innings length rounded up to whole overs (23 matches).
- **4 DLS matches** with no recorded revised target are excluded from pressure tagging because the in-game target is
  unknown; their deliveries still count toward usual performance.
- First-innings deliveries are never pressure deliveries.

**Why this definition.** RRR is the most direct measure of how far a chase is behind the game. The late-chase clause
captures tight finishes where a moderate RRR still leaves no margin for error. The same match state is used for both
disciplines: batters must accelerate, bowlers must deny.

**How it separates situations.** League-wide, wickets fall much faster under pressure (IPL: one every 17.8 legal
balls vs 21.1 otherwise; T20I: 14.5 vs 19.5), while strike rates are only slightly higher. Pressure balls are riskier
balls, which is the behaviour a pressure definition should capture.

**Known breadth.** Modern targets are high, so 60.3% of chase deliveries (55,448) qualify. Any target of 181+ starts
above RRR 9, and hopeless chases (RRR > 15) are included. The sensitivity analysis below quantifies the effect.

## 3. Metrics

"Pressure" = pressure deliveries; "usual" = all non-pressure deliveries in the same filter scope (both innings).

**Batting:** pressure runs, balls, SR, boundary-ball %, dot %, dismissals, average; usual SR; uplift = pressure SR -
usual SR; *kept pace %* = share of pressure innings with >= 5 balls at SR >= 150 (9 an over); pressure chases won.

**Bowling:** pressure legal balls, runs, wickets, economy, wickets per 6 legal balls, dot %, balls per wicket, wides,
no-balls; usual economy; economy gain = usual - pressure economy; *held %* = share of pressure spells with >= 6 legal
balls at economy <= 9; pressure defences won.

## 4. Pressure Reliability Score

P(x) is the mid-rank percentile of x among **eligible players of the same discipline** in the current scope:
`(count below + 0.5 x ties) / n x 100`.

```
Batting PRS = 0.55 P(pressure SR) + 0.25 P(clip(pressure SR - usual SR, -40, +40)) + 0.20 P(pressure boundary-ball %)
Bowling PRS = 0.45 P(-pressure economy) + 0.35 P(wickets per 6 legal balls) + 0.20 P(pressure dot-ball %)
```

- The score is a **relative 0-100 index, not a probability**.
- Batting and bowling scores are on separate scales and are never compared.
- A missing usual baseline gives a neutral uplift percentile of 50 and is flagged.
- **Eligibility:** >= 40 pressure balls (faced / legal balls bowled) in >= 6 matches. Players with 15-39 balls, or fewer
  than 6 matches, are listed as *Limited sample* with a provisional score against the eligible distribution, and are never
  ranked.
- Ties are broken by pressure SR (batters) or lower pressure economy (bowlers), then sample size.

## 5. Results

The official top-10 lists, with every component statistic and bootstrap stability, are in
[DATA_VALIDATION.md](DATA_VALIDATION.md) section 4 and in `top10_batters.csv` / `top10_bowlers.csv`.

## 6. Reliability checks

1. **Independent recomputation.** `scripts/validate.py` re-tags pressure with a row-by-row loop and rebuilds every
   statistic and score with separate code. All 13 checks pass with zero differences.
2. **Result reconciliation.** Rebuilt innings totals reproduce 397 / 399 "won by N runs" results exactly and
   399 / 399 "won by N wickets" results. The two misses are DLS games whose revised target is missing.
3. **Bootstrap rank stability.** Matches are resampled 200 times (Poisson bootstrap) and all scores recomputed.
   Top-10 membership for the default lists ranges from about 12% to 70% of resamples, so the *set* of strong performers
   is informative but the *order* within the top 10 is fragile. Players close to the 40-ball threshold (e.g. the #1 batter
   with exactly 40 balls) are the least stable.
4. **Definition sensitivity.** The Methodology page recomputes the top 10 under stricter (RRR 10 / 8.5), looser
   (RRR 8 / 36 balls at 7) and close-chase-only (RRR <= 15) definitions and reports the overlap with the specified list.
5. **Cross-competition transfer.** For players eligible in both IPL and T20I, pressure numbers correlate only weakly
   between the two: r = 0.05 for batters' pressure SR (39 players) and r = 0.19 for bowlers' pressure economy
   (37 players), default scope.

## 7. Limitations

- Broad pressure band and inclusion of lost-cause chases (see section 2).
- Phase confounding: pressure balls cluster at the death, where SR is naturally higher, so uplift partly measures phase.
- Mixed opposition strength: T20Is include Associate nations. Use *Full Members & IPL only* to test robustness.
- Small samples: 40 balls is about seven overs; see bootstrap stability.
- DLS timing: a revised target is applied to the whole chase because the interruption point is not recorded.
- Roles are inferred (bowled >= 1 over in >= 50% of appearances; all-rounders also bat top-7 with >= 10 balls per
  innings; keepers flagged in >= 50% of recorded matches).
- The dataset contains no availability, fitness, retention or auction information, so no such claims are made.
