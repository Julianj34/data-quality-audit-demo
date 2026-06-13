"""validate_uniqueness.py — S2-C: Uniqueness Checks.

UNI_001  duplicate sale_id in sales          MAJOR
UNI_002  duplicate customer_id in customers  MAJOR
UNI_003  duplicate product_id in products    MAJOR

Counting semantics: keep='first'. The FIRST occurrence of a key is
considered the legitimate row; every FURTHER occurrence produces
exactly one error record. A key appearing twice therefore yields one
error, not two — this matches the cleaning rule "keep first instance,
drop duplicates" 1:1 and keeps the manifest arithmetic exact.

NULL keys are skipped: a missing key is a completeness problem
(COM_*/SCH_003), not a duplicate.
"""

from __future__ import annotations

from error_record import ErrorFactory, ErrorRecord

_KEYS = [
    ("UNI_001", "sales", "sale_id"),
    ("UNI_002", "customers", "customer_id"),
    ("UNI_003", "products", "product_id"),
]


def run_checks(dataframes: dict, config: dict,
               factory: ErrorFactory) -> list[ErrorRecord]:
    errors: list[ErrorRecord] = []

    for check_id, table, key in _KEYS:
        df = dataframes[table]
        non_null = df[df[key].notna()]
        dup_mask = non_null.duplicated(subset=key, keep="first")
        for idx in non_null.index[dup_mask]:
            value = non_null.at[idx, key]
            errors.append(factory.create(
                check_id=check_id, table=table,
                row_ref=str(value),
                column=key, invalid_value=value,
                rule=f"{key} is unique in {table}",
                message=f"duplicate {key} {value} "
                        f"(first occurrence kept, this one flagged)",
            ))

    return errors
