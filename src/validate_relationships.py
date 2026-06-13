"""validate_relationships.py — S2-D: Relationship Checks.

REL_001  customer_id not found in customers   CRITICAL
REL_002  product_id not found in products     CRITICAL
REL_003  sale references an inactive product  MAJOR (FLAG)

Two precision rules that keep the error arithmetic exact:

1. NULL FKs are skipped — COM_001/COM_002 own missing keys. REL only
   judges keys that exist but point nowhere.
2. Lookups are built on DEDUPLICATED master tables. The masters may
   themselves contain duplicate keys (UNI_002/UNI_003) — without
   dedup, a duplicated product row would make status lookups
   ambiguous. Existence and status are taken from the first
   occurrence, consistent with the keep-first cleaning rule.

REL_003 only fires for product_ids that DO exist — an unknown id is
REL_002's error, never both.
"""

from __future__ import annotations

import pandas as pd

from error_record import ErrorFactory, ErrorRecord
from load_data import row_ref_for


def run_checks(dataframes: dict, config: dict,
               factory: ErrorFactory) -> list[ErrorRecord]:
    errors: list[ErrorRecord] = []
    sales = dataframes["sales"]

    customers = dataframes["customers"].drop_duplicates(
        subset="customer_id", keep="first")
    products = dataframes["products"].drop_duplicates(
        subset="product_id", keep="first")

    known_customers = set(customers["customer_id"].dropna())
    known_products = set(products["product_id"].dropna())
    status_of = dict(zip(products["product_id"],
                         products["active_status"]))

    for idx, row in sales.iterrows():
        ref = row_ref_for("sales", row, idx)

        # --- REL_001: unknown customer -------------------------------
        cid = row["customer_id"]
        if pd.notna(cid) and cid not in known_customers:
            errors.append(factory.create(
                check_id="REL_001", table="sales", row_ref=ref,
                column="customer_id", invalid_value=cid,
                rule="sales.customer_id in customers.customer_id",
                message=f"customer_id {cid} does not exist in customers",
            ))

        # --- REL_002 / REL_003: product reference --------------------
        pid = row["product_id"]
        if pd.isna(pid):
            continue                            # COM_002 owns this
        if pid not in known_products:
            errors.append(factory.create(
                check_id="REL_002", table="sales", row_ref=ref,
                column="product_id", invalid_value=pid,
                rule="sales.product_id in products.product_id",
                message=f"product_id {pid} does not exist in products",
            ))
        elif str(status_of.get(pid)).lower() != "active":
            errors.append(factory.create(
                check_id="REL_003", table="sales", row_ref=ref,
                column="product_id", invalid_value=pid,
                rule="referenced product has active_status = active",
                message=f"sale references inactive product {pid}",
            ))

    return errors
