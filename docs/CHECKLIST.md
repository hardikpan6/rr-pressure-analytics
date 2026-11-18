# Final checklist

Verified with `python -m pytest tests -q` (36 passed), `python scripts/validate.py` (13 / 13 checks passed)
and manual browser review of every page.

## Required features

| Feature | Status | How verified |
|---|---|---|
| Executive overview with all 8 KPI cards computed from data | Done | AppTest asserts every KPI label; values change with filters |
| Top-10 batter and bowler leaderboards with all requested columns | Done | AppTest + browser |
| Sorting (column headers + explicit sort control) | Done | AppTest asserts economy sort is monotonic |
| Search bar | Done | AppTest with search applied on every page |
| Season, competition type, competition, team, role filters | Done | AppTest narrow-filter run on all 10 pages |
| Reset filters button | Done | AppTest: KPIs return to defaults after reset |
| Full Members & IPL only toggle, adjustable eligibility thresholds | Done | AppTest; warning shown for non-default thresholds |
| Download filtered data as CSV | Done | Download buttons on leaderboards, analysis tables, teams/competitions, compare, profile logs, recommendations, sensitivity |
| Player detail view | Done | Leaderboard row select > Open profile (browser), recommendation cards > Profile, direct selector |
| Player comparison selector (2-6 players) | Done | AppTest (batters and bowlers mode) + browser |
| Batting analysis (SR, uplift, boundary %, consistency, sample size) | Done | Browser |
| Bowling analysis (economy, wickets/over, dot %, improvement, consistency) | Done | Browser |
| Pressure vs normal comparison charts, improvers and decliners | Done | Browser |
| Team, competition, IPL vs T20I, role distribution, season trends | Done | Browser + AppTest |
| Recommendation engine with stats-based explanations | Done | Six rule-based shortlists, no availability claims |
| Emerging / limited-sample section kept separate from main ranking | Done | Leaderboard "Limited sample" view, recommendations watch list |
| Methodology, formulas and limitations visible in the app | Done | Methodology & validation page |
| Empty-scope handling (no seasons / no eligible players) | Done | AppTest empty-scope run on all 10 pages |
| Responsive layout (desktop, tablet, mobile) | Done | Browser at ~1700 px, ~1030 px and ~515 px effective widths |

## Statistical validation

| Check | Status |
|---|---|
| Pressure tags reproduced by an independent row-by-row implementation | PASS (0 mismatches) |
| Top-10 stats and scores reproduced independently | PASS (0.0 max difference) |
| No duplicate delivery keys, no duplicate players in leaderboards | PASS |
| All joins complete (matches, players) | PASS |
| Reconstructed totals vs official results | 397 / 399 run margins, 399 / 399 wicket wins |
| Bootstrap rank stability reported | Done (leaderboard column + Methodology page) |
| Definition sensitivity analysis | Done (Methodology page) |

## Deployment readiness

| Item | Status |
|---|---|
| `requirements.txt` (runtime only) and `requirements-dev.txt` (tests) | Done |
| Relative data paths, no local-machine dependencies | Done (`src/config.py` resolves `data/` from the package) |
| No secrets required; `.streamlit/secrets.toml` git-ignored | Done |
| Streamlit Community Cloud compatible entry point `streamlit_app.py` | Done |
| Largest file 41 MB (< 100 MB git limit) | Done |
| README, METHODOLOGY, DATA_VALIDATION, DEPLOYMENT docs | Done |
| Screenshots in `docs/screenshots/` | Done |

## Known limitations (documented, not defects)

- Under the specified definition about 60% of chase deliveries are pressure deliveries.
- Top-10 order is statistically fragile (bootstrap top-10 membership roughly 12-70%).
- Roles are data-derived; no availability, fitness or auction data exists in the dataset.
- Dataframe row selection and chart interactions are verified manually in the browser (AppTest cannot simulate them).
