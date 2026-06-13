"""run_pipeline.py — Production-style entry point (Architecture §12).

One command, idempotent, fully logged:

    python run_pipeline.py

Runs the whole chain on the data in data/raw and writes the six output
artefacts. Re-running overwrites the outputs deterministically — no
state is kept between runs.

Pipeline order:
     1. load & validate config            (C0)
     2. load raw data                      (S1)
     3-7. validate (Schema..Business)      (S2 A-E)
     8. assign severity & score (raw)      (S3)
     9. clean (FIX/DROP/FLAG)              (S4)
        + re-validate & score (clean)      (S2/S3 second pass)
    10. export reports & clean dataset     (S5)

Fail behaviour:
    - file-level schema problem (missing file / column) -> abort, exit 1
    - every other error -> collected, never aborts (audit principle:
      see everything first)

The notebook (notebooks/01_...ipynb) tells the story; this script
proves reproducibility. Both call the exact same src/ modules.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import json

import yaml

from error_record import ErrorFactory, ConfigError
from load_data import load_raw_data, DataLoadError
from calculate_quality_score import (calculate_quality_score,
                                     count_total_rows, format_score_block)
from clean_data import clean
from export_reports import PipelineReport, export_all
import validate_schema
import validate_completeness
import validate_uniqueness
import validate_relationships
import validate_business_rules

_LAYERS = [
    ("Schema", validate_schema),
    ("Completeness", validate_completeness),
    ("Uniqueness", validate_uniqueness),
    ("Relationship", validate_relationships),
    ("Business Rules", validate_business_rules),
]


class RunLogger:
    """Timestamped log to stdout and to memory (-> processing_log.txt)."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def log(self, msg: str) -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
        print(line)
        self.lines.append(line)


def _detect(dataframes, config, factory, log) -> list:
    """Run all five validation layers; collect into one record list."""
    records = []
    for name, module in _LAYERS:
        found = module.run_checks(dataframes, config, factory)
        records.extend(found)
        log.log(f"   {name:<14} {len(found):>4} issues")
    return records


def _log_detection_vs_manifest(records, manifest, log) -> None:
    """Optional: report detection against the known error manifest."""
    injected = Counter((e["table"], e["row_ref"], e["error_class"])
                       for e in manifest.get("errors", []))
    detected = Counter((r.table, r.row_ref, r.check_id) for r in records)
    matched = sum((injected & detected).values())
    total = manifest.get("total_injected_errors", sum(injected.values()))
    log.log(f"   Known injected demo errors detected: {matched} / {total}")


def run_pipeline(raw_dir: str | Path, config_path: str | Path,
                 reports_dir: str | Path,
                 processed_dir: str | Path) -> PipelineReport:
    log = RunLogger()
    log.log("=== Data Quality Audit Pipeline ===")

    # --- 1. config (C0) -------------------------------------------------
    config = yaml.safe_load(Path(config_path).read_text())
    factory = ErrorFactory(config)        # validate_config runs here
    log.log(f"1. Config loaded & validated: {config_path}")

    # --- 2. raw data (S1) ----------------------------------------------
    dataframes = load_raw_data(raw_dir)
    rows = count_total_rows(dataframes)
    log.log(f"2. Raw data loaded from {raw_dir} "
            f"({rows} rows across {len(dataframes)} tables)")

    # --- 3-7. validation (S2 A-E) --------------------------------------
    validate_schema.assert_file_level_schema(dataframes, config)
    log.log("3-7. Validation (read-only):")
    raw_errors = _detect(dataframes, config, factory, log)
    log.log(f"   TOTAL          {len(raw_errors):>4} issues found")

    # optional verification against the injected-error manifest
    manifest_path = Path(raw_dir) / "injected_errors.json"
    manifest = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        _log_detection_vs_manifest(raw_errors, manifest, log)

    # --- 8. score raw (S3) ---------------------------------------------
    raw_score = calculate_quality_score(raw_errors, rows, config)
    log.log(f"8. Raw quality score: {raw_score.score}/100 "
            f"({raw_score.traffic_light})  "
            f"[C{raw_score.n_critical}/M{raw_score.n_major}/"
            f"m{raw_score.n_minor}]")

    # --- 9. clean (S4) + second pass -----------------------------------
    cleaning = clean(dataframes, raw_errors, config)
    log.log(f"9. Cleaning: {cleaning.total_dropped} dropped, "
            f"{cleaning.total_fixed} fixed, "
            f"{cleaning.total_flagged} flagged "
            f"({len(cleaning.escalated_to_drop)} FIX->DROP escalations)")

    clean_factory = ErrorFactory(config)
    clean_errors = _detect(cleaning.cleaned, config, clean_factory,
                           RunLogger())   # re-validate quietly
    clean_rows = count_total_rows(cleaning.cleaned)
    clean_score = calculate_quality_score(clean_errors, clean_rows, config)
    log.log(f"   Clean quality score: {clean_score.score}/100 "
            f"({clean_score.traffic_light}) — "
            f"{len(clean_errors)} documented residual issues")

    # --- 10. export (S5) -----------------------------------------------
    report = PipelineReport(
        config=config, raw_dataframes=dataframes, raw_errors=raw_errors,
        raw_score=raw_score, cleaning=cleaning, clean_errors=clean_errors,
        clean_score=clean_score, log_lines=log.lines, manifest=manifest)

    paths = export_all(report, reports_dir, processed_dir)
    log.log(f"10. Exported {len(paths)} artefacts:")
    for p in paths:
        log.log(f"    {p}")
    log.log(f"Before/After: {raw_score.score}/100 {raw_score.emoji}  ->  "
            f"{clean_score.score}/100 {clean_score.emoji}")
    log.log("=== Pipeline complete ===")

    # rewrite processing_log.txt so it contains the final lines too
    (Path(reports_dir) / "processing_log.txt").write_text(
        "\n".join(log.lines) + "\n", encoding="utf-8")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Data Quality Audit pipeline end-to-end.")
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    parser.add_argument("--config",
                        default=str(ROOT / "data" / "reference"
                                    / "allowed_values.yaml"))
    parser.add_argument("--reports-dir", default=str(ROOT / "reports"))
    parser.add_argument("--processed-dir",
                        default=str(ROOT / "data" / "processed"))
    args = parser.parse_args()

    try:
        run_pipeline(args.raw_dir, args.config,
                     args.reports_dir, args.processed_dir)
        return 0
    except DataLoadError as e:
        print(f"\nABORT (S1): {e}", file=sys.stderr)
        print("Hint: generate demo data first with\n"
              "  python src/generate_demo_data.py --outdir data/raw",
              file=sys.stderr)
        return 1
    except validate_schema.SchemaAbortError as e:
        print(f"\nABORT (S2-A): {e}", file=sys.stderr)
        return 1
    except ConfigError as e:
        print(f"\nABORT (C0): config contract violated: {e}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
