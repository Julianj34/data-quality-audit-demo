"""calculate_quality_score.py — S3: Severity & Scoring.

Pure aggregation over list[ErrorRecord] — no data access, no side
effects. The exact formula (Architecture, section 8.2):

    weighted_error_points      = n_critical*w_c + n_major*w_m + n_minor*w_n
    error_points_per_1000_rows = weighted_error_points / total_row_count
                                 * normalize_per_rows
    quality_score              = max(0, 100 - error_points_per_1000_rows)

    - total_row_count = sum of rows of ALL checked tables
    - weights and normalisation base come from config (scoring.*)
    - the score is rounded to an integer

Rounding decision (the architecture leaves this open, so it is fixed
here): COMMERCIAL HALF-UP rounding, not Python's built-in round().
round() uses banker's rounding (round-half-to-even), which would make
boundary behaviour surprising: round(90.5) == 90. Half-up guarantees
90.5 -> 91, deterministically, which matters exactly at the traffic
light thresholds.

The score is calculated twice by the pipeline — once on raw data,
once after cleaning — which yields the before/after comparison for
the summary. This module doesn't know or care which run it is.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from error_record import ErrorRecord, Severity

# severity -> recommended action in the decision-ready output (§8.3)
_ACTION_OF = {
    Severity.CRITICAL: "ACT",
    Severity.MAJOR: "CHECK",
    Severity.MINOR: "OBSERVE",
}

_EMOJI = {"green": "\U0001F7E2", "yellow": "\U0001F7E1",
          "red": "\U0001F534"}


def round_half_up(x: float) -> int:
    """Commercial rounding for non-negative values: 0.5 always up."""
    return int(math.floor(x + 0.5))


def count_total_rows(dataframes: dict[str, pd.DataFrame]) -> int:
    """total_row_count = sum of rows of all checked tables."""
    return sum(len(df) for df in dataframes.values())


@dataclass(frozen=True)
class ScoreResult:
    """Everything S5 needs to render data_quality_score.md."""

    score: int                        # 0..100, half-up rounded
    traffic_light: str                # "green" | "yellow" | "red"
    n_critical: int
    n_major: int
    n_minor: int
    total_errors: int
    weighted_error_points: float
    error_points_per_1000_rows: float
    total_row_count: int
    errors_by_check: dict[str, int] = field(default_factory=dict)
    errors_by_table: dict[str, int] = field(default_factory=dict)

    @property
    def emoji(self) -> str:
        return _EMOJI[self.traffic_light]

    def top_error_classes(self, n: int = 5) -> list[tuple[str, int]]:
        return Counter(self.errors_by_check).most_common(n)


def calculate_quality_score(records: list[ErrorRecord],
                            total_row_count: int,
                            config: dict) -> ScoreResult:
    """Apply the exact §8.2 formula to a list of error records.

    Raises ValueError for total_row_count <= 0 — an empty dataset is a
    loading problem (DataLoadError territory), not a scorable state.
    """
    if total_row_count <= 0:
        raise ValueError(
            "total_row_count must be positive — scoring an empty "
            "dataset is undefined (check data loading)")

    scoring = config["scoring"]
    weights = scoring["weights"]
    normalize = float(scoring["normalize_per_rows"])

    by_severity = Counter(r.severity for r in records)
    n_critical = by_severity.get(Severity.CRITICAL, 0)
    n_major = by_severity.get(Severity.MAJOR, 0)
    n_minor = by_severity.get(Severity.MINOR, 0)

    weighted = (n_critical * float(weights["CRITICAL"])
                + n_major * float(weights["MAJOR"])
                + n_minor * float(weights["MINOR"]))
    per_norm = weighted / total_row_count * normalize
    score = round_half_up(max(0.0, 100.0 - per_norm))

    tl = scoring["traffic_light"]
    if score >= tl["green"]:
        light = "green"
    elif score >= tl["yellow"]:
        light = "yellow"
    else:
        light = "red"

    return ScoreResult(
        score=score,
        traffic_light=light,
        n_critical=n_critical,
        n_major=n_major,
        n_minor=n_minor,
        total_errors=len(records),
        weighted_error_points=weighted,
        error_points_per_1000_rows=per_norm,
        total_row_count=total_row_count,
        errors_by_check=dict(Counter(r.check_id for r in records)),
        errors_by_table=dict(Counter(r.table for r in records)),
    )


def format_score_block(result: ScoreResult, config: dict,
                       label: str = "") -> str:
    """Render the decision-ready block (Architecture, section 8.3).

    Plain text — used in the processing log and the notebook. The
    data_quality_score.md file itself is rendered by S5.
    """
    tl = config["scoring"]["traffic_light"]
    title = f"Overall Quality Score{f' ({label})' if label else ''}:"
    lines = [
        f"{title} {result.score}/100        {result.emoji}",
        "",
        f"Critical Issues: {result.n_critical:<6} "
        f"-> {_ACTION_OF[Severity.CRITICAL]}",
        f"Major Issues:    {result.n_major:<6} "
        f"-> {_ACTION_OF[Severity.MAJOR]}",
        f"Minor Issues:    {result.n_minor:<6} "
        f"-> {_ACTION_OF[Severity.MINOR]}",
        "",
        f"Weighted error points: {result.weighted_error_points:g} "
        f"({result.error_points_per_1000_rows:.1f} per "
        f"{config['scoring']['normalize_per_rows']:g} rows, "
        f"{result.total_row_count} rows checked)",
        "",
        f"Traffic light thresholds (config): "
        f"{_EMOJI['green']} >= {tl['green']}   "
        f"{_EMOJI['yellow']} {tl['yellow']}-{tl['green'] - 1}   "
        f"{_EMOJI['red']} < {tl['yellow']}",
    ]
    return "\n".join(lines)
