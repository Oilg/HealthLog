BASELINE_MAX_DAYS = 60
RECENT_DAYS = 5
MIN_VALID_DAYS_FOR_SIGNAL = 45
MIN_RECENT_VALID_DAYS = 3
ILLNESS_TREND_LOOKBACK_DAYS = 63
HR_POINTS_PER_DAY_MIN = 12
HRV_POINTS_PER_DAY_MIN = 3

# Wrist temperature integration (Apple Watch 8+)
TEMP_MIN_BASELINE_NIGHTS = 5
TEMP_RECENT_NIGHTS = 2
TEMP_MAX_BASELINE_NIGHTS = 14

# --- Anti-false-positive thresholds ---
# Daily "confirmed" flag thresholds. Both absolute and relative bars must be met
# for HR/RR so that a small baseline does not over-trigger (a +6 bpm shift on a
# 50 bpm athlete baseline is ~12 %, much more significant than +6 bpm on 75 bpm).
# These are deliberately conservative: the previous values (+6 bpm / -15 % HRV /
# +8 % RR) overlap with day-to-day physiological noise (poor sleep, alcohol,
# post-training overreach), driving false positives.
HR_CONFIRM_DELTA_BPM = 7
HR_CONFIRM_DELTA_REL = 0.10  # +10 % over baseline
HRV_CONFIRM_REL = 0.80  # recent HRV <= 80 % of baseline (i.e. >= -20 %)
RR_CONFIRM_REL = 1.12  # recent RR >= 112 % of baseline
RR_CONFIRM_DELTA = 2.0  # absolute +2 breaths/min over baseline

# Hard gate: how many of the last RECENT_DAYS must show >=2 simultaneous flags
# before we report anything but "none". Transient 1-2 day spikes after a hard
# workout, late dinner, alcohol or stress should not surface as illness.
MIN_CONFIRMED_DAYS_FOR_SIGNAL = 3

# Severity thresholds (post-gating). Raised so "low" is genuinely indicative
# rather than catching everyday HRV swings.
SEVERITY_LOW_MIN = 0.30
SEVERITY_MEDIUM_MIN = 0.55
SEVERITY_HIGH_MIN = 0.75

# Wrist temperature acts as an objective veto. When Watch 8+ data is present
# and the recent skin temperature is NOT elevated (delta <= 0 °C), an
# inflammatory process is physiologically unlikely; downweight the score.
TEMP_STABLE_DELTA_THRESHOLD = 0.0
TEMP_STABLE_PENALTY = 0.6
