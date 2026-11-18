"""Central constants for the pressure analytics model.

Every analytical threshold lives here so the methodology page, the README and
the code can never drift apart.
"""

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# --- Pressure definition (second-innings chases only) -----------------------
PRESSURE_RRR = 9.0  # required run rate that alone qualifies as pressure
LATE_BALLS = 30  # "late chase" window, in legal balls remaining
LATE_RRR = 7.5  # required run rate that qualifies inside the late window
FULL_INNINGS_BALLS = 120

# --- Delivery classification (verified against the raw data) ---------------
# 'Overstep' is a front-foot no-ball; 'other' behaves identically (1-run
# penalty, ball re-bowled) so both are treated as no-balls.
WIDE_TYPES = {"wide"}
NOBALL_TYPES = {"Overstep", "other"}
BYE_TYPES = {"byes", "legbyes"}
BOWLER_WICKET_TYPES = {"Bowled", "Caught", "LBW", "Stump", "Hit Wicket"}

# --- Eligibility for the main leaderboard -----------------------------------
MIN_PRESSURE_BALLS = 40
MIN_PRESSURE_MATCHES = 6
# Players below eligibility but above this floor appear as "emerging".
EMERGING_MIN_BALLS = 15

# --- Scoring weights (percentiles are computed within each discipline) ------
BAT_WEIGHTS = {"sr": 0.55, "uplift": 0.25, "boundary": 0.20}
BOWL_WEIGHTS = {"economy": 0.45, "wkts": 0.35, "dots": 0.20}
UPLIFT_CLIP = 40.0

# --- Consistency definitions ------------------------------------------------
# A batter "kept pace" in a pressure innings when scoring at >= 9 an over
# (strike rate 150) across at least this many pressure balls in that match.
CONSISTENCY_MIN_BAT_BALLS = 5
CONSISTENCY_BAT_SR = 150.0
# A bowler "held" a pressure spell when conceding <= 9 an over across at least
# this many pressure legal balls in that match.
CONSISTENCY_MIN_BOWL_BALLS = 6
CONSISTENCY_BOWL_ECON = 9.0

# --- Competition grouping ---------------------------------------------------
COMP_GROUPS = ["IPL", "T20I", "Other T20"]
DEFAULT_COMP_GROUPS = ["IPL", "T20I"]

# ICC Full Members (used only by the optional "Full Members & IPL" filter).
FULL_MEMBER_TEAMS = {
    "Afghanistan", "Australia", "Bangladesh", "England", "India", "Ireland",
    "New Zealand", "Pakistan", "South Africa", "Sri Lanka", "West Indies",
    "Zimbabwe",
}

ROLES = ["Batter", "Wicketkeeper-batter", "All-rounder", "Bowler"]
