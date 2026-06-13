"""error_record.py — Clean Core of the Data Quality Audit System (V1).

This module defines the single error format that ALL five validation
layers produce. Everything downstream (scoring, cleaning, reporting)
is just an aggregation over a list[ErrorRecord].

Contract (Architecture, section 6.2):
    - Every check function has the signature:
          check_xyz(dataframes: dict, config: dict) -> list[ErrorRecord]
    - No check mutates data. Validation is read-only.
    - Cleaning reads only ErrorRecords + config.

Adding a new check in V2 = adding one function with the same return
type + two config entries (severity_map, cleaning_actions). Nothing
else changes. validate_config() enforces this contract at startup.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Enums — the only allowed vocabulary
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    CRITICAL = "CRITICAL"   # row unusable for reporting
    MAJOR = "MAJOR"         # row distorts aggregations
    MINOR = "MINOR"         # row usable, but worth documenting


class CleaningAction(str, Enum):
    FIX = "FIX"     # repairable (normalize, map, cap) — original/fixed logged
    DROP = "DROP"   # not salvageable — removed, documented in errors_report
    FLAG = "FLAG"   # kept, marked via quality_flag column


class CheckLayer(str, Enum):
    SCHEMA = "SCHEMA"
    COMPLETENESS = "COMPLETENESS"
    UNIQUENESS = "UNIQUENESS"
    RELATIONSHIP = "RELATIONSHIP"
    BUSINESS_RULE = "BUSINESS_RULE"


# ---------------------------------------------------------------------------
# Check registry — every known check ID and its layer.
# A check that is not registered here cannot produce records:
# the contract is enforced, not assumed.
# ---------------------------------------------------------------------------

KNOWN_CHECKS: dict[str, CheckLayer] = {
    "SCH_001": CheckLayer.SCHEMA,
    "SCH_002": CheckLayer.SCHEMA,
    "SCH_003": CheckLayer.SCHEMA,
    "COM_001": CheckLayer.COMPLETENESS,
    "COM_002": CheckLayer.COMPLETENESS,
    "COM_003": CheckLayer.COMPLETENESS,
    "COM_004": CheckLayer.COMPLETENESS,
    "COM_005": CheckLayer.COMPLETENESS,
    "UNI_001": CheckLayer.UNIQUENESS,
    "UNI_002": CheckLayer.UNIQUENESS,
    "UNI_003": CheckLayer.UNIQUENESS,
    "REL_001": CheckLayer.RELATIONSHIP,
    "REL_002": CheckLayer.RELATIONSHIP,
    "REL_003": CheckLayer.RELATIONSHIP,
    "BIZ_001": CheckLayer.BUSINESS_RULE,
    "BIZ_002": CheckLayer.BUSINESS_RULE,
    "BIZ_003": CheckLayer.BUSINESS_RULE,
    "BIZ_004": CheckLayer.BUSINESS_RULE,
    "BIZ_005": CheckLayer.BUSINESS_RULE,
    "BIZ_006": CheckLayer.BUSINESS_RULE,
    "BIZ_007": CheckLayer.BUSINESS_RULE,
}

VALID_TABLES = {"sales", "customers", "products", "targets"}


# ---------------------------------------------------------------------------
# The Error Record itself (Architecture, section 6.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ErrorRecord:
    """One detected data quality issue. Immutable by design."""

    error_id: str               # E00001, sequential per run
    check_id: str               # e.g. REL_001
    check_layer: CheckLayer
    severity: Severity          # assigned from config (severity_map)
    table: str                  # sales | customers | products | targets
    row_ref: str                # primary key or row index of affected row
    column: Optional[str]       # affected column, None for row-level errors
    invalid_value: str          # offending value, stringified
    rule: str                   # machine-readable rule, e.g. "discount <= 0.5"
    message: str                # human-readable description
    cleaning_action: CleaningAction  # assigned from config (cleaning_actions)
    detected_at: str            # ISO timestamp of the pipeline run

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["check_layer"] = self.check_layer.value
        d["severity"] = self.severity.value
        d["cleaning_action"] = self.cleaning_action.value
        return d


# ---------------------------------------------------------------------------
# Factory — the only way checks should create records.
# Guarantees: sequential IDs, one timestamp per run, severity and
# cleaning_action always taken from config, never hardcoded in checks.
# ---------------------------------------------------------------------------

class ErrorFactory:
    """Creates ErrorRecords with run-consistent metadata.

    Usage inside a check function:

        def check_unknown_customer(dataframes, config, factory):
            errors = []
            ...
            errors.append(factory.create(
                check_id="REL_001",
                table="sales",
                row_ref=str(row.sale_id),
                column="customer_id",
                invalid_value=str(row.customer_id),
                rule="sales.customer_id in customers.customer_id",
                message=f"customer_id {row.customer_id} not found in customers",
            ))
            return errors
    """

    def __init__(self, config: dict):
        validate_config(config)
        self._config = config
        self._counter = 0
        self._run_timestamp = datetime.now().isoformat(timespec="seconds")

    @property
    def run_timestamp(self) -> str:
        return self._run_timestamp

    def create(
        self,
        check_id: str,
        table: str,
        row_ref: str,
        column: Optional[str],
        invalid_value: Any,
        rule: str,
        message: str,
    ) -> ErrorRecord:
        if check_id not in KNOWN_CHECKS:
            raise ValueError(
                f"Unknown check_id '{check_id}'. Register it in "
                f"KNOWN_CHECKS and add it to severity_map + "
                f"cleaning_actions in allowed_values.yaml."
            )
        if table not in VALID_TABLES:
            raise ValueError(f"Unknown table '{table}'. Allowed: {VALID_TABLES}")

        self._counter += 1
        return ErrorRecord(
            error_id=f"E{self._counter:05d}",
            check_id=check_id,
            check_layer=KNOWN_CHECKS[check_id],
            severity=Severity(self._config["severity_map"][check_id]),
            table=table,
            row_ref=str(row_ref),
            column=column,
            invalid_value=str(invalid_value),
            rule=rule,
            message=message,
            cleaning_action=CleaningAction(
                self._config["cleaning_actions"][check_id]
            ),
            detected_at=self._run_timestamp,
        )


# ---------------------------------------------------------------------------
# Config validation (C0) — fail fast, fail loud.
# Enforces the completeness contract of allowed_values.yaml.
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when allowed_values.yaml violates the contract."""


def validate_config(config: dict) -> None:
    """Validate that the config fulfils the Clean Core contract.

    Raises ConfigError with a precise message on the first violation.
    Called automatically by ErrorFactory and at pipeline start (step 1).
    """
    required_sections = [
        "allowed_values", "business_rules", "severity_map",
        "cleaning_actions", "scoring", "required_columns",
    ]
    for section in required_sections:
        if section not in config:
            raise ConfigError(f"Config section missing: '{section}'")

    # 1. Every known check must have a severity and a cleaning action
    for check_id in KNOWN_CHECKS:
        if check_id not in config["severity_map"]:
            raise ConfigError(f"severity_map missing entry for {check_id}")
        if check_id not in config["cleaning_actions"]:
            raise ConfigError(f"cleaning_actions missing entry for {check_id}")

    # 2. No orphan entries (config rules for checks that don't exist)
    for check_id in config["severity_map"]:
        if check_id not in KNOWN_CHECKS:
            raise ConfigError(
                f"severity_map contains unknown check_id '{check_id}' "
                f"(not in KNOWN_CHECKS)"
            )
    for check_id in config["cleaning_actions"]:
        if check_id not in KNOWN_CHECKS:
            raise ConfigError(
                f"cleaning_actions contains unknown check_id '{check_id}'"
            )

    # 3. Values must come from the allowed vocabulary
    valid_severities = {s.value for s in Severity}
    valid_actions = {a.value for a in CleaningAction}
    for check_id, sev in config["severity_map"].items():
        if sev not in valid_severities:
            raise ConfigError(
                f"severity_map[{check_id}] = '{sev}' invalid. "
                f"Allowed: {sorted(valid_severities)}"
            )
    for check_id, action in config["cleaning_actions"].items():
        if action not in valid_actions:
            raise ConfigError(
                f"cleaning_actions[{check_id}] = '{action}' invalid. "
                f"Allowed: {sorted(valid_actions)}"
            )

    # 4. Scoring must be complete and consistent
    scoring = config["scoring"]
    for key in ("weights", "normalize_per_rows", "traffic_light"):
        if key not in scoring:
            raise ConfigError(f"scoring missing key: '{key}'")
    for sev in valid_severities:
        if sev not in scoring["weights"]:
            raise ConfigError(f"scoring.weights missing severity: '{sev}'")
    tl = scoring["traffic_light"]
    if "green" not in tl or "yellow" not in tl:
        raise ConfigError("scoring.traffic_light needs 'green' and 'yellow'")
    if not tl["green"] > tl["yellow"]:
        raise ConfigError(
            f"traffic_light: green ({tl['green']}) must be > "
            f"yellow ({tl['yellow']})"
        )

    # 5. Required columns must cover all tables
    for table in VALID_TABLES:
        if table not in config["required_columns"]:
            raise ConfigError(f"required_columns missing table: '{table}'")


# ---------------------------------------------------------------------------
# Export helper — the bridge to S3 (scoring) and S5 (reports)
# ---------------------------------------------------------------------------

ERROR_REPORT_COLUMNS = [
    "error_id", "check_id", "check_layer", "severity", "table",
    "row_ref", "column", "invalid_value", "rule", "message",
    "cleaning_action", "detected_at",
]


def records_to_dataframe(records: list[ErrorRecord]) -> pd.DataFrame:
    """Convert a list of ErrorRecords into a DataFrame for scoring/export.

    Returns an empty DataFrame with the correct columns if no errors
    were found — downstream code never needs a special case for that.
    """
    if not records:
        return pd.DataFrame(columns=ERROR_REPORT_COLUMNS)
    return pd.DataFrame([r.to_dict() for r in records])[ERROR_REPORT_COLUMNS]
