"""validate_completeness.py — S2-B: Completeness Checks.

COM_001  missing customer_id in sales        CRITICAL
COM_002  missing product_id in sales         CRITICAL
COM_003  missing sale_date in sales          MAJOR
COM_004  missing quantity / unit_price       CRITICAL
COM_005  missing optional fields (any table) MINOR

Owns NULL handling for the sales table's reporting-relevant fields
(see scope contract in validate_schema.py). Downstream checks
(REL_*, BIZ_*) skip NULLs — one empty cell is exactly one error.
"""

from __future__ import annotations

import pandas as pd

from error_record import ErrorFactory, ErrorRecord
from load_data import row_ref_for

# check_id -> (column, human label)
_MANDATORY_SALES = [
    ("COM_001", "customer_id"),
    ("COM_002", "product_id"),
    ("COM_003", "sale_date"),
    ("COM_004", "quantity"),
    ("COM_004", "unit_price"),
]


def run_checks(dataframes: dict, config: dict,
               factory: ErrorFactory) -> list[ErrorRecord]:
    errors: list[ErrorRecord] = []

    # --- COM_001..COM_004: mandatory sales fields ----------------------
    sales = dataframes["sales"]
    for check_id, col in _MANDATORY_SALES:
        for idx in sales.index[sales[col].isna()]:
            errors.append(factory.create(
                check_id=check_id, table="sales",
                row_ref=row_ref_for("sales", sales.loc[idx], idx),
                column=col, invalid_value="<empty>",
                rule=f"{col} is mandatory in sales",
                message=f"{col} missing",
            ))

    # --- COM_005: optional fields, all tables ---------------------------
    for table, optional_cols in config.get("optional_columns", {}).items():
        df = dataframes[table]
        for col in optional_cols:
            if col not in df.columns:
                continue
            for idx in df.index[df[col].isna()]:
                errors.append(factory.create(
                    check_id="COM_005", table=table,
                    row_ref=row_ref_for(table, df.loc[idx], idx),
                    column=col, invalid_value="<empty>",
                    rule=f"{col} is optional but documented when missing",
                    message=f"optional field {col} missing",
                ))

    return errors
