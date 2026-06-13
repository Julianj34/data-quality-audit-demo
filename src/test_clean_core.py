"""Smoke test for the Clean Core (error_record.py + allowed_values.yaml)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml
from error_record import (
    ErrorFactory, ConfigError, validate_config,
    records_to_dataframe, KNOWN_CHECKS,
)

CONFIG_PATH = REPO_ROOT / "data" / "reference" / "allowed_values.yaml"

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

# --- 1. Contract: config must be complete and valid -----------------------
validate_config(config)
print(f"[OK] Config valid — {len(KNOWN_CHECKS)} checks fully mapped "
      f"(severity + cleaning_action)")

# --- 2. Factory creates well-formed records -------------------------------
factory = ErrorFactory(config)

e1 = factory.create(
    check_id="REL_001", table="sales", row_ref="S-00417",
    column="customer_id", invalid_value="C-9999",
    rule="sales.customer_id in customers.customer_id",
    message="customer_id C-9999 not found in customers",
)
e2 = factory.create(
    check_id="BIZ_003", table="sales", row_ref="S-00021",
    column="discount", invalid_value="0.8",
    rule="discount <= 0.5",
    message="discount 0.8 exceeds max_discount 0.5",
)
e3 = factory.create(
    check_id="BIZ_007", table="sales", row_ref="S-01102",
    column="quantity", invalid_value="540",
    rule="quantity <= 10 * median(quantity)",
    message="quantity outlier: 540 vs median 4",
)

assert e1.error_id == "E00001" and e3.error_id == "E00003", "sequential IDs"
assert e1.severity.value == "CRITICAL" and e1.cleaning_action.value == "DROP"
assert e2.severity.value == "MAJOR" and e2.cleaning_action.value == "FIX"
assert e3.severity.value == "MINOR" and e3.cleaning_action.value == "FLAG"
assert e1.detected_at == e2.detected_at == e3.detected_at, "one timestamp/run"
print("[OK] Factory: sequential IDs, severity+action from config, "
      "single run timestamp")

# --- 3. DataFrame bridge (S3/S5 input) -------------------------------------
df = records_to_dataframe([e1, e2, e3])
assert len(df) == 3 and list(df.severity) == ["CRITICAL", "MAJOR", "MINOR"]
empty = records_to_dataframe([])
assert list(empty.columns) == list(df.columns), "empty case = same schema"
print("[OK] records_to_dataframe: 3 records + empty case share one schema")
print()
print(df[["error_id", "check_id", "severity", "cleaning_action",
          "table", "row_ref", "invalid_value"]].to_string(index=False))
print()

# --- 4. Fail fast: contract violations must raise --------------------------
broken = yaml.safe_load(open(CONFIG_PATH))
del broken["severity_map"]["BIZ_007"]
try:
    validate_config(broken)
    raise AssertionError("missing severity_map entry was NOT caught")
except ConfigError as err:
    print(f"[OK] Missing mapping caught: {err}")

broken2 = yaml.safe_load(open(CONFIG_PATH))
broken2["cleaning_actions"]["REL_001"] = "REPAIR"   # not in vocabulary
try:
    validate_config(broken2)
    raise AssertionError("invalid action was NOT caught")
except ConfigError as err:
    print(f"[OK] Invalid vocabulary caught: {err}")

try:
    factory.create(check_id="XYZ_999", table="sales", row_ref="S-1",
                   column=None, invalid_value="", rule="", message="")
    raise AssertionError("unknown check_id was NOT caught")
except ValueError as err:
    print(f"[OK] Unknown check_id caught: {err}")

print()
print("CLEAN CORE: all contract tests passed.")
