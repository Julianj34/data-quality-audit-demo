"""verify_detection.py — Proof run: detection vs. the error manifest.

Verifies the central trust claim of the project (DoD #4):

    Known injected demo errors detected: N / N
    Detection rate against intentionally injected demo errors: 100%

The verification is BIDIRECTIONAL and therefore strict:

    1. Every manifest entry must have exactly one matching detection
       (no misses).
    2. Every detection must have a matching manifest entry
       (no false positives on the otherwise-clean baseline).

Matching key: (table, row_ref, error_class/check_id).

Only if both directions hold does the claim mean what it says. A
validator that fires on everything would also reach "100% detected" —
direction 2 is what rules that out.

Usage:  python verify_detection.py [--raw-dir data/raw]
Exit code 0 only on a perfect bidirectional match.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import yaml

from error_record import ErrorFactory, records_to_dataframe
from load_data import load_raw_data
import validate_schema
import validate_completeness
import validate_uniqueness
import validate_relationships
import validate_business_rules

VALIDATORS = [
    ("SCHEMA", validate_schema),
    ("COMPLETENESS", validate_completeness),
    ("UNIQUENESS", validate_uniqueness),
    ("RELATIONSHIP", validate_relationships),
    ("BUSINESS_RULE", validate_business_rules),
]


def main(raw_dir: str = "data/raw",
         config_path: str = "data/reference/allowed_values.yaml") -> int:
    # --- run S1 + S2 exactly like the pipeline will -------------------
    with open(config_path) as f:
        config = yaml.safe_load(f)
    factory = ErrorFactory(config)              # validates config (C0)

    dataframes = load_raw_data(raw_dir)
    validate_schema.assert_file_level_schema(dataframes, config)

    detected = []
    for layer_name, module in VALIDATORS:
        found = module.run_checks(dataframes, config, factory)
        detected.extend(found)
        print(f"  {layer_name:<14} {len(found):>4} errors")
    print(f"  {'TOTAL':<14} {len(detected):>4} errors detected\n")

    # --- load ground truth ---------------------------------------------
    manifest = json.load(open(Path(raw_dir) / "injected_errors.json"))
    injected = manifest["errors"]

    # --- bidirectional comparison on (table, row_ref, check_id) --------
    injected_keys = Counter(
        (e["table"], e["row_ref"], e["error_class"]) for e in injected)
    detected_keys = Counter(
        (r.table, r.row_ref, r.check_id) for r in detected)

    missed = injected_keys - detected_keys       # in manifest, not found
    unexpected = detected_keys - injected_keys   # found, not in manifest
    matched = sum((injected_keys & detected_keys).values())

    # --- per-class table -------------------------------------------------
    classes = sorted({e["error_class"] for e in injected}
                     | {r.check_id for r in detected})
    inj_by_class = Counter(e["error_class"] for e in injected)
    det_by_class = Counter(r.check_id for r in detected)

    print(f"  {'class':<9} {'injected':>8} {'detected':>8}   status")
    print(f"  {'-' * 42}")
    for c in classes:
        i, d = inj_by_class.get(c, 0), det_by_class.get(c, 0)
        status = "OK" if i == d else "MISMATCH"
        print(f"  {c:<9} {i:>8} {d:>8}   {status}")
    print(f"  {'-' * 42}")
    print(f"  {'TOTAL':<9} {sum(inj_by_class.values()):>8} "
          f"{sum(det_by_class.values()):>8}\n")

    # --- verdict ----------------------------------------------------------
    total = manifest["total_injected_errors"]
    print(f"Known injected demo errors detected: {matched} / {total}")
    print(f"Missed injections:     {sum(missed.values())}")
    print(f"Unexpected detections: {sum(unexpected.values())}")

    for key in list(missed)[:10]:
        print(f"  MISSED:     {key}")
    for key in list(unexpected)[:10]:
        print(f"  UNEXPECTED: {key}")

    if not missed and not unexpected and matched == total:
        print("\nVERIFIED: detection rate against intentionally "
              "injected demo errors = 100% (bidirectional).")
        return 0
    print("\nFAILED: detection does not match the manifest.")
    return 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--config",
                        default="data/reference/allowed_values.yaml")
    args = parser.parse_args()
    sys.exit(main(args.raw_dir, args.config))
