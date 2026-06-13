"""clean_data.py — S4: Cleaning Module (FIX / DROP / FLAG).

Reads ONLY error records + config + dataframes; returns NEW frames
(never mutates the input). Implements the decision table from
Architecture section 9 exactly:

    FIX   SCH_002 date -> ISO        (escalates to DROP if unparseable)
          BIZ_003 discount -> clip [0, max_discount]  (+ FLAG)
          BIZ_005 region -> synonym map (escalates to DROP if no match)
          BIZ_006 channel -> synonym map (escalates to DROP if no match)
    DROP  COM_001..004, UNI_*, REL_001/002, BIZ_001/002/004
    FLAG  COM_005, REL_003, BIZ_007  (+ the FIX'd BIZ_003 rows)

Two subtleties that the implementation handles explicitly:

  1. DUPLICATE INDEXING. A UNIQUENESS error's row_ref is the key
     value, which points at BOTH copies. We must keep the first and
     drop the rest — so duplicates are resolved mechanically via
     keep='first' on the index, NOT by matching row_ref. Done first,
     so afterwards every key is unique and row_ref->row resolution is
     unambiguous for all other checks.

  2. FIX -> DROP ESCALATION. SCH_002 and BIZ_005/006 are FIX by
     policy, but a value that cannot be repaired (date won't parse,
     region has no synonym) escalates to DROP at runtime. Every such
     escalation is logged as a DROP with its reason.

Invariants (Architecture section 9):
  - every dropped row is in the errors_report with a reason (the
    ErrorRecord already carries message + cleaning_action=DROP)
  - every FIX writes original_value + fixed_value to the fix log
  - FLAG rows get a quality_flag column in the clean master dataset
  - clean_master_dataset has gross_revenue and net_revenue

V1 scope note: demo errors are injected disjointly (one error per
row), so cleaning is exact on the demo data. For overlapping errors
the rule is "DROP dominates FIX/FLAG, duplicates keep-first".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from error_record import CleaningAction, ErrorRecord
from load_data import try_parse_date, try_parse_float

ISO = "%Y-%m-%d"

# Which check fixes which column, and how. Keys here MUST have
# cleaning_action FIX in the config; everything else is DROP/FLAG.
_FIX_CHECKS = {"SCH_002", "BIZ_003", "BIZ_005", "BIZ_006"}
_FLAG_CHECKS = {"COM_005", "REL_003", "BIZ_007"}


@dataclass(frozen=True)
class FixLogEntry:
    table: str
    row_ref: str
    check_id: str
    column: str
    original_value: str
    fixed_value: str
    note: str = ""


@dataclass
class CleaningResult:
    """Output of S4 — input for the second scoring pass and S5."""

    cleaned: dict[str, pd.DataFrame]          # per-table, cleaned
    master: pd.DataFrame                       # joined + revenue + flags
    fix_log: list[FixLogEntry] = field(default_factory=list)
    escalated_to_drop: list[FixLogEntry] = field(default_factory=list)
    dropped_by_check: dict[str, int] = field(default_factory=dict)
    flagged_by_check: dict[str, int] = field(default_factory=dict)
    rows_before: dict[str, int] = field(default_factory=dict)
    rows_after: dict[str, int] = field(default_factory=dict)

    @property
    def total_dropped(self) -> int:
        return sum(self.dropped_by_check.values())

    @property
    def total_fixed(self) -> int:
        return len(self.fix_log)

    @property
    def total_flagged(self) -> int:
        return sum(self.flagged_by_check.values())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_synonyms(raw: dict) -> dict[str, str]:
    """Lowercase + strip the synonym KEYS so lookups are robust
    regardless of how the config author wrote them."""
    return {str(k).strip().lower(): v for k, v in (raw or {}).items()}


def _records_by_table(errors: list[ErrorRecord]
                      ) -> dict[str, list[ErrorRecord]]:
    out: dict[str, list[ErrorRecord]] = {}
    for r in errors:
        out.setdefault(r.table, []).append(r)
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def clean(dataframes: dict[str, pd.DataFrame],
          errors: list[ErrorRecord],
          config: dict) -> CleaningResult:
    work = {t: df.copy() for t, df in dataframes.items()}
    by_table = _records_by_table(errors)

    fix_log: list[FixLogEntry] = []
    escalated: list[FixLogEntry] = []
    dropped_by_check: dict[str, int] = {}
    flagged_by_check: dict[str, int] = {}

    rows_before = {t: len(df) for t, df in work.items()}

    # --- 1. master-table de-duplication (UNI_002 / UNI_003) -------------
    work["customers"], n_c = _dedup(work["customers"], "customer_id")
    work["products"], n_p = _dedup(work["products"], "product_id")
    if n_c:
        dropped_by_check["UNI_002"] = n_c
    if n_p:
        dropped_by_check["UNI_003"] = n_p

    # --- 2. sales cleaning ---------------------------------------------
    sales = work["sales"]
    sales_records = by_table.get("sales", [])

    # 2a. duplicates first (mechanical keep-first) -> keys unique after
    dup_mask = (sales["sale_id"].notna()
                & sales.duplicated("sale_id", keep="first"))
    drop_idx: set = set(sales.index[dup_mask])
    if dup_mask.any():
        dropped_by_check["UNI_001"] = int(dup_mask.sum())

    # sale_id -> index, only for rows that survive de-dup (now unique)
    survivors = sales.loc[~sales.index.isin(drop_idx)]
    idx_of = {sid: idx for idx, sid in survivors["sale_id"].items()
              if pd.notna(sid)}

    flags: dict[int, list[str]] = {}

    def flag(idx: int, reason: str) -> None:
        flags.setdefault(idx, []).append(reason)

    # 2b. resolve every sales record to an action
    max_discount = float(config["business_rules"]["max_discount"])
    region_syn = _normalise_synonyms(
        config["allowed_values"].get("region_synonyms"))
    channel_syn = _normalise_synonyms(
        config["allowed_values"].get("channel_synonyms"))

    for rec in sales_records:
        if rec.check_id == "UNI_001":
            continue                                   # handled in 2a
        idx = idx_of.get(rec.row_ref)
        if idx is None:
            # row_ref points only at a duplicate that is already
            # being dropped -> nothing else to do
            continue

        action = rec.cleaning_action

        if action is CleaningAction.DROP:
            drop_idx.add(idx)
            dropped_by_check[rec.check_id] = \
                dropped_by_check.get(rec.check_id, 0) + 1

        elif action is CleaningAction.FLAG:
            flag(idx, rec.check_id)
            flagged_by_check[rec.check_id] = \
                flagged_by_check.get(rec.check_id, 0) + 1

        elif action is CleaningAction.FIX:
            outcome = _apply_fix(sales, idx, rec, max_discount,
                                 region_syn, channel_syn)
            if outcome is None:
                # escalation: unrepairable -> DROP
                drop_idx.add(idx)
                dropped_by_check[rec.check_id] = \
                    dropped_by_check.get(rec.check_id, 0) + 1
                escalated.append(FixLogEntry(
                    table="sales", row_ref=rec.row_ref,
                    check_id=rec.check_id, column=rec.column or "",
                    original_value=rec.invalid_value,
                    fixed_value="<dropped>",
                    note="FIX impossible (no parse / no synonym) "
                         "-> escalated to DROP"))
            else:
                fix_log.append(outcome)
                # BIZ_003 is FIX *and* FLAG (capped value stays, marked)
                if rec.check_id == "BIZ_003":
                    flag(idx, "BIZ_003")
                    flagged_by_check["BIZ_003"] = \
                        flagged_by_check.get("BIZ_003", 0) + 1

    # 2c. apply flags, then drop
    sales["quality_flag"] = sales.index.map(
        lambda i: ";".join(flags.get(i, [])))
    sales_clean = sales.drop(index=list(drop_idx)).reset_index(drop=True)
    work["sales"] = sales_clean

    rows_after = {t: len(df) for t, df in work.items()}

    # --- 3. clean master dataset (join + revenue) ----------------------
    master = _build_master(work, config)

    return CleaningResult(
        cleaned=work, master=master, fix_log=fix_log,
        escalated_to_drop=escalated,
        dropped_by_check=dropped_by_check,
        flagged_by_check=flagged_by_check,
        rows_before=rows_before, rows_after=rows_after)


# ---------------------------------------------------------------------------
# De-dup, fixes, master build
# ---------------------------------------------------------------------------

def _dedup(df: pd.DataFrame, key: str) -> tuple[pd.DataFrame, int]:
    mask = df[key].notna() & df.duplicated(key, keep="first")
    n = int(mask.sum())
    return df.loc[~mask].reset_index(drop=True), n


def _apply_fix(sales: pd.DataFrame, idx: int, rec: ErrorRecord,
               max_discount: float, region_syn: dict,
               channel_syn: dict) -> FixLogEntry | None:
    """Apply a FIX in place. Return a FixLogEntry on success, or None
    if the value cannot be repaired (caller escalates to DROP)."""
    col = rec.column
    original = sales.at[idx, col]

    if rec.check_id == "SCH_002":
        parsed = try_parse_date(original)
        if parsed is None:
            return None
        fixed = parsed.strftime(ISO)
        sales.at[idx, col] = fixed
        return FixLogEntry("sales", rec.row_ref, "SCH_002", col,
                           str(original), fixed,
                           "date normalised to ISO 8601")

    if rec.check_id == "BIZ_003":
        d = try_parse_float(original)
        capped = min(max(d, 0.0), max_discount) if d is not None else 0.0
        fixed = f"{capped:g}"
        sales.at[idx, col] = fixed           # column is all-string by design
        return FixLogEntry("sales", rec.row_ref, "BIZ_003", col,
                           str(original), fixed,
                           f"discount clipped to [0, {max_discount:g}]")

    if rec.check_id == "BIZ_005":
        mapped = region_syn.get(str(original).strip().lower())
        if mapped is None:
            return None
        sales.at[idx, col] = mapped
        return FixLogEntry("sales", rec.row_ref, "BIZ_005", col,
                           str(original), mapped, "region mapped")

    if rec.check_id == "BIZ_006":
        mapped = channel_syn.get(str(original).strip().lower())
        if mapped is None:
            return None
        sales.at[idx, col] = mapped
        return FixLogEntry("sales", rec.row_ref, "BIZ_006", col,
                           str(original), mapped, "channel mapped")

    raise ValueError(f"No fix defined for {rec.check_id} "
                     f"(config says FIX but code has no handler)")


def _build_master(work: dict[str, pd.DataFrame],
                  config: dict) -> pd.DataFrame:
    """Join cleaned sales with customers and products, add revenue.

    After cleaning every FK is valid (REL_* rows dropped), so a left
    join loses nothing. Numeric columns are coerced here — they are
    guaranteed parseable because non-numeric/negative/missing rows
    were dropped.
    """
    sales = work["sales"].copy()
    customers = work["customers"]
    products = work["products"]

    cust_cols = [c for c in ["customer_id", "customer_name",
                             "customer_segment", "country"]
                 if c in customers.columns]
    prod_cols = [c for c in ["product_id", "product_name",
                             "category", "active_status"]
                 if c in products.columns]

    master = sales.merge(customers[cust_cols], on="customer_id",
                         how="left", validate="many_to_one")
    master = master.merge(products[prod_cols], on="product_id",
                         how="left", validate="many_to_one")

    qty = pd.to_numeric(master["quantity"], errors="coerce")
    price = pd.to_numeric(master["unit_price"], errors="coerce")
    disc = pd.to_numeric(master["discount"], errors="coerce").fillna(0.0)

    master["gross_revenue"] = (qty * price).round(2)
    master["net_revenue"] = (master["gross_revenue"]
                             * (1.0 - disc)).round(2)

    ordered = ["sale_id", "sale_date", "customer_id", "customer_name",
               "customer_segment", "country", "product_id",
               "product_name", "category", "quantity", "unit_price",
               "discount", "region", "sales_channel",
               "gross_revenue", "net_revenue", "quality_flag"]
    present = [c for c in ordered if c in master.columns]
    rest = [c for c in master.columns if c not in present]
    return master[present + rest]
