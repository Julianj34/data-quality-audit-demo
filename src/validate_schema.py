"""validate_schema.py — S2-A: Schema Checks.

SCH_001  expected columns present        CRITICAL (file level -> ABORT)
SCH_002  data types correct              MAJOR    (date format, numeric)
SCH_003  required fields not empty       CRITICAL

SCOPE CONTRACT (prevents double counting — do not change casually):
    The sales table's required fields customer_id, product_id,
    sale_date, quantity and unit_price are owned by the COMPLETENESS
    layer (COM_001..COM_004). SCH_003 therefore covers:
        - sales:    sale_id only
        - all required fields of customers, products, targets
    One empty cell == exactly one error record, always.

SCH_002 date scope: only columns typed "date" in config.column_types.
    A non-ISO but parseable value (e.g. "15.03.2024") is an SCH_002
    error here and a FIX candidate in cleaning. A NULL date is NOT an
    SCH_002 error — completeness owns missing values.
"""

from __future__ import annotations

import pandas as pd

from error_record import ErrorFactory, ErrorRecord
from load_data import is_iso_date, try_parse_date, try_parse_float, \
    row_ref_for


class SchemaAbortError(Exception):
    """SCH_001 at file level: a required column is missing entirely."""


# Required sales fields owned by COM_001..COM_004 (see scope contract)
_COM_OWNED_SALES_FIELDS = {
    "customer_id", "product_id", "sale_date", "quantity", "unit_price",
}


def assert_file_level_schema(dataframes: dict, config: dict) -> None:
    """SCH_001 — abort with a clear message if any expected column is
    missing. Runs BEFORE everything else (Architecture, section 12)."""
    problems = []
    for table, required in config["required_columns"].items():
        present = set(dataframes[table].columns)
        for col in required:
            if col not in present:
                problems.append(f"{table}: column '{col}' missing")
    if problems:
        raise SchemaAbortError(
            "SCH_001 — expected column(s) missing, pipeline aborted:\n  "
            + "\n  ".join(problems)
        )


def run_checks(dataframes: dict, config: dict,
               factory: ErrorFactory) -> list[ErrorRecord]:
    errors: list[ErrorRecord] = []
    column_types = config.get("column_types", {})

    for table, df in dataframes.items():
        types = column_types.get(table, {})

        # --- SCH_002: date columns must be ISO 8601 -------------------
        for col, typ in types.items():
            if typ != "date" or col not in df.columns:
                continue
            for idx, value in df[col].items():
                if pd.isna(value):
                    continue                    # completeness owns NULLs
                if is_iso_date(value):
                    continue
                parseable = try_parse_date(value) is not None
                errors.append(factory.create(
                    check_id="SCH_002", table=table,
                    row_ref=row_ref_for(table, df.loc[idx], idx),
                    column=col, invalid_value=value,
                    rule=f"{col} matches ISO 8601 (%Y-%m-%d)",
                    message=(f"{col} '{value}' is not ISO 8601 "
                             + ("(parseable -> FIX candidate)"
                                if parseable else "(not parseable)")),
                ))

        # --- SCH_002: numeric columns must be parseable ---------------
        for col, typ in types.items():
            if typ != "numeric" or col not in df.columns:
                continue
            for idx, value in df[col].items():
                if pd.isna(value):
                    continue                    # completeness owns NULLs
                if try_parse_float(value) is None:
                    errors.append(factory.create(
                        check_id="SCH_002", table=table,
                        row_ref=row_ref_for(table, df.loc[idx], idx),
                        column=col, invalid_value=value,
                        rule=f"{col} is numeric",
                        message=f"{col} '{value}' is not numeric",
                    ))

        # --- SCH_003: required fields not empty (scope contract!) -----
        for col in config["required_columns"][table]:
            if table == "sales" and col in _COM_OWNED_SALES_FIELDS:
                continue                        # owned by COM_001..COM_004
            if col not in df.columns:
                continue                        # SCH_001 already aborted
            for idx, value in df[col].items():
                if pd.isna(value):
                    errors.append(factory.create(
                        check_id="SCH_003", table=table,
                        row_ref=row_ref_for(table, df.loc[idx], idx),
                        column=col, invalid_value="<empty>",
                        rule=f"{col} is required and must not be empty",
                        message=f"required field {col} is empty",
                    ))

    return errors
