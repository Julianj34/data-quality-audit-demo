"""load_data.py — S1: Data Loader.

Loading principle: RAW STAYS RAW.
    Every column is loaded as string (object dtype). The loader does
    NOT strip whitespace, NOT coerce types, NOT fix formats — values
    like "NORTH " or "15.03.2024" must reach the validators exactly
    as they appear in the file. The only normalisation is empty
    string -> NaN, so "missing" has one representation.

Fail behaviour (Architecture, section 12):
    A missing input file is a file-level CRITICAL -> raise immediately
    with a clear message. Everything else is the validators' job.

This module also hosts the deterministic parsing helpers used by the
validators (S1 = data access layer). No dateutil guessing — only an
explicit, ordered format list, so results never depend on locale or
library heuristics.
"""

from __future__ import annotations

from datetime import date, datetime
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

RAW_FILES = {
    "sales": "sales_raw.csv",
    "customers": "customers_raw.xlsx",
    "products": "products_raw.xlsx",
    "targets": "monthly_targets.xlsx",
}

# Ordered, explicit. First match wins. ISO first by design.
DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d-%m-%Y"]
ISO_FORMAT = "%Y-%m-%d"
_ISO_SHAPE = re.compile(r"\d{4}-\d{2}-\d{2}")


class DataLoadError(Exception):
    """Raised when an input file is missing or unreadable (abort)."""


def load_raw_data(raw_dir: str | Path) -> dict[str, pd.DataFrame]:
    """Load all four raw files as all-string DataFrames.

    Returns {"sales": df, "customers": df, "products": df, "targets": df}.
    Raises DataLoadError if any file is missing (file-level CRITICAL).
    """
    raw = Path(raw_dir)
    missing = [name for name, fn in RAW_FILES.items()
               if not (raw / fn).exists()]
    if missing:
        raise DataLoadError(
            f"Missing input file(s) in {raw}: "
            + ", ".join(RAW_FILES[m] for m in missing)
        )

    dataframes: dict[str, pd.DataFrame] = {}

    # CSV: keep_default_na=False so we control what counts as missing
    df = pd.read_csv(raw / RAW_FILES["sales"], dtype=str,
                     keep_default_na=False)
    dataframes["sales"] = df.replace("", np.nan)

    for name in ("customers", "products", "targets"):
        df = pd.read_excel(raw / RAW_FILES[name], dtype=str)
        dataframes[name] = df.replace("", np.nan)

    return dataframes


# ---------------------------------------------------------------------------
# Deterministic parsing helpers (used by validators and cleaning)
# ---------------------------------------------------------------------------

def try_parse_date(value, formats: list[str] = DATE_FORMATS
                   ) -> Optional[date]:
    """Parse a date string against the explicit format list.

    Returns None for NaN/unparseable values — callers decide what
    that means (skip, COM error, DROP, ...).
    """
    if pd.isna(value):
        return None
    s = str(value).strip()
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def is_iso_date(value) -> bool:
    """True if the value is STRICTLY ISO 8601 (YYYY-MM-DD, zero-padded).

    strptime alone is too lenient — it accepts "2024-1-5" for
    "%Y-%m-%d". The regex enforces the exact shape first, strptime
    then validates the calendar (rejects e.g. "2024-02-30").
    """
    if pd.isna(value):
        return False
    s = str(value)
    if not _ISO_SHAPE.fullmatch(s):
        return False
    try:
        datetime.strptime(s, ISO_FORMAT)
        return True
    except ValueError:
        return False


def try_parse_float(value) -> Optional[float]:
    """Parse a numeric string. None for NaN/unparseable values."""
    if pd.isna(value):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def row_ref_for(table: str, row: pd.Series, index) -> str:
    """Primary key of the affected row, or the row index as fallback."""
    pk_column = {
        "sales": "sale_id",
        "customers": "customer_id",
        "products": "product_id",
        "targets": None,           # composite (month, region)
    }[table]
    if pk_column and pd.notna(row.get(pk_column)):
        return str(row[pk_column])
    if table == "targets":
        return f"{row.get('month')}/{row.get('region')}"
    return f"row:{index}"
