"""validate_business_rules.py — S2-E: Business Rule Checks.

BIZ_001  quantity below minimum               CRITICAL
BIZ_002  unit_price not positive              CRITICAL
BIZ_003  discount outside [0, max_discount]   MAJOR
BIZ_004  sale_date outside [date_min, today]  MAJOR
BIZ_005  region not in allowed list           MAJOR
BIZ_006  sales_channel not in allowed list    MAJOR
BIZ_007  quantity outlier (median-based)      MINOR (FLAG)

Precision rules (the error arithmetic depends on these):

- NULL SKIPPING: every check here skips NaN. Missing values are owned
  by COM_001..COM_005 — a missing discount is one COM_005 error, never
  additionally a BIZ_003 error.
- UNPARSEABLE SKIPPING: values that don't parse are SCH_002's error,
  not a business rule violation on top.
- BIZ_004 evaluates every PARSEABLE date (incl. non-ISO formats) via
  the deterministic format list — a sale dated "15.03.2024" gets its
  format error from SCH_002, but its date VALUE is still judged here.
- BIZ_007 computes the median over POSITIVE quantities only, so
  injected/real negative values (BIZ_001) cannot drag the threshold
  down and create phantom outliers.
- BIZ_007 is quantity-based in V1. A price-vs-standard_price outlier
  check needs RESOLVED product references and therefore belongs after
  cleaning -> V2.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from error_record import ErrorFactory, ErrorRecord
from load_data import row_ref_for, try_parse_date, try_parse_float


def run_checks(dataframes: dict, config: dict,
               factory: ErrorFactory) -> list[ErrorRecord]:
    errors: list[ErrorRecord] = []
    sales = dataframes["sales"]
    rules = config["business_rules"]
    allowed = config["allowed_values"]

    min_quantity = float(rules["min_quantity"])
    min_unit_price = float(rules["min_unit_price"])
    max_discount = float(rules["max_discount"])
    date_min = date.fromisoformat(str(rules["date_min"]))
    today = date.today()

    # --- BIZ_007 threshold: median over positive quantities only -------
    positive_q = [q for q in (try_parse_float(v) for v in sales["quantity"])
                  if q is not None and q > 0]
    median_q = (pd.Series(positive_q).median() if positive_q else 0.0)
    outlier_threshold = median_q * float(rules["outlier_quantity_factor"])

    for idx, row in sales.iterrows():
        ref = row_ref_for("sales", row, idx)

        # --- BIZ_001: quantity >= min_quantity ------------------------
        q = try_parse_float(row["quantity"])
        if q is not None and q < min_quantity:
            errors.append(factory.create(
                check_id="BIZ_001", table="sales", row_ref=ref,
                column="quantity", invalid_value=row["quantity"],
                rule=f"quantity >= {min_quantity:g}",
                message=f"quantity {q:g} below minimum "
                        f"{min_quantity:g}",
            ))

        # --- BIZ_007: quantity outlier (only if BIZ_001 passed) -------
        elif q is not None and outlier_threshold > 0 \
                and q > outlier_threshold:
            errors.append(factory.create(
                check_id="BIZ_007", table="sales", row_ref=ref,
                column="quantity", invalid_value=row["quantity"],
                rule=f"quantity <= {rules['outlier_quantity_factor']} "
                     f"x median ({outlier_threshold:g})",
                message=f"quantity {q:g} is an outlier "
                        f"(median {median_q:g})",
            ))

        # --- BIZ_002: unit_price >= min_unit_price ---------------------
        p = try_parse_float(row["unit_price"])
        if p is not None and p < min_unit_price:
            errors.append(factory.create(
                check_id="BIZ_002", table="sales", row_ref=ref,
                column="unit_price", invalid_value=row["unit_price"],
                rule=f"unit_price >= {min_unit_price:g}",
                message=f"unit_price {p:g} is not positive",
            ))

        # --- BIZ_003: discount in [0, max_discount] --------------------
        d = try_parse_float(row["discount"])
        if d is not None and not (0.0 <= d <= max_discount):
            errors.append(factory.create(
                check_id="BIZ_003", table="sales", row_ref=ref,
                column="discount", invalid_value=row["discount"],
                rule=f"0 <= discount <= {max_discount:g}",
                message=f"discount {d:g} outside "
                        f"[0, {max_discount:g}]",
            ))

        # --- BIZ_004: sale_date within [date_min, today] ---------------
        parsed = try_parse_date(row["sale_date"])
        if parsed is not None and not (date_min <= parsed <= today):
            errors.append(factory.create(
                check_id="BIZ_004", table="sales", row_ref=ref,
                column="sale_date", invalid_value=row["sale_date"],
                rule=f"{date_min.isoformat()} <= sale_date <= today",
                message=(f"sale_date {parsed.isoformat()} is in the "
                         f"future" if parsed > today else
                         f"sale_date {parsed.isoformat()} is before "
                         f"plausibility minimum {date_min.isoformat()}"),
            ))

        # --- BIZ_005 / BIZ_006: allowed lists --------------------------
        region = row["region"]
        if pd.notna(region) and region not in allowed["regions"]:
            errors.append(factory.create(
                check_id="BIZ_005", table="sales", row_ref=ref,
                column="region", invalid_value=region,
                rule=f"region in {allowed['regions']}",
                message=f"region '{region}' not in allowed list",
            ))

        channel = row["sales_channel"]
        if pd.notna(channel) and channel not in allowed["sales_channels"]:
            errors.append(factory.create(
                check_id="BIZ_006", table="sales", row_ref=ref,
                column="sales_channel", invalid_value=channel,
                rule=f"sales_channel in {allowed['sales_channels']}",
                message=f"sales_channel '{channel}' not in allowed list",
            ))

    return errors
