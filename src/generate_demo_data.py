"""generate_demo_data.py — S0: Seeded demo data with controlled error injection.

Design principle (Architecture, section 11):
    1. Generate a CLEAN baseline first. Every row is guaranteed valid:
       only existing FKs, only active products, valid regions/channels,
       discounts in range, dates in the past, no duplicates.
    2. Inject errors deliberately onto DISJOINT rows — one error per row.
       No error can mask or duplicate another, so the manifest count
       is exact by construction.
    3. Log every injected error to data/raw/injected_errors.json.
       This manifest is the ground truth the validators are verified
       against ("known injected demo errors detected: N / N").

Reproducibility: random.seed(42) → byte-identical data on every run.

Note for validator design (kept here so the contract is in one place):
    - NULL values in optional fields raise COM_005 only. Business rule
      checks (BIZ_*) must SKIP nulls, otherwise one injected error
      would be counted twice.
    - BIZ_007 (outlier) must compute the median over positive
      quantities only, so injected BIZ_001 negatives cannot shift it.
"""

from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Generation parameters
# ---------------------------------------------------------------------------

SEED = 42
N_CUSTOMERS = 200
N_PRODUCTS = 50          # thereof N_INACTIVE inactive
N_INACTIVE = 5
N_SALES = 2_000
SALES_YEAR = 2024        # clean sale_dates live entirely in this year

REGIONS = ["North", "South", "East", "West", "Central"]
CHANNELS = ["online", "retail", "partner"]
SEGMENTS = ["B2B", "B2C", "Enterprise"]
COUNTRIES = ["Germany", "Austria", "Switzerland", "Netherlands", "France"]
CATEGORIES = ["Electronics", "Office", "Furniture", "Accessories", "Software"]

CLEAN_DISCOUNTS = [0.0, 0.0, 0.0, 0.0, 0.05, 0.10, 0.15, 0.20, 0.25]

# ---------------------------------------------------------------------------
# Error injection plan — exactly one entry per manifest line.
# Total = 142 (matches the verification claim in ARCHITECTURE.md §11).
# One error per row, rows are disjoint by construction.
# ---------------------------------------------------------------------------

ERROR_PLAN: dict[str, int] = {
    "SCH_002": 9,    # wrong date format (parseable -> FIX candidates)
    "COM_001": 8,    # missing customer_id
    "COM_002": 8,    # missing product_id
    "COM_003": 6,    # missing sale_date
    "COM_004": 8,    # missing quantity / unit_price (split 4/4)
    "COM_005": 13,   # missing optional field (discount/region/channel)
    "UNI_001": 6,    # duplicate sale_id (otherwise-clean rows copied)
    "UNI_002": 4,    # duplicate customer_id in customers
    "UNI_003": 3,    # duplicate product_id in products
    "REL_001": 11,   # unknown customer_id
    "REL_002": 8,    # unknown product_id
    "REL_003": 7,    # sale of an inactive product
    "BIZ_001": 8,    # quantity <= 0
    "BIZ_002": 7,    # unit_price <= 0
    "BIZ_003": 10,   # discount outside [0, max_discount]
    "BIZ_004": 6,    # sale_date in the future
    "BIZ_005": 8,    # invalid region (5 mappable via synonyms, 3 not)
    "BIZ_006": 7,    # invalid sales_channel (5 mappable, 2 not)
    "BIZ_007": 5,    # revenue outlier (extreme quantity)
}
EXPECTED_TOTAL = 142
assert sum(ERROR_PLAN.values()) == EXPECTED_TOTAL, "ERROR_PLAN must sum to 142"

SALES_COLUMNS = [
    "sale_id", "sale_date", "customer_id", "product_id",
    "quantity", "unit_price", "discount", "region", "sales_channel",
]

FIRST_NAMES = ["Anna", "Ben", "Clara", "David", "Elena", "Felix", "Greta",
               "Henrik", "Ida", "Jonas", "Katrin", "Lukas", "Mara", "Niklas",
               "Olivia", "Paul", "Quinn", "Rosa", "Stefan", "Tina"]
LAST_NAMES = ["Albrecht", "Bauer", "Conrad", "Dietrich", "Eberhard", "Fischer",
              "Graf", "Hoffmann", "Iversen", "Jung", "Keller", "Lang",
              "Maier", "Neumann", "Oswald", "Peters", "Quandt", "Richter",
              "Schmidt", "Thalberg"]
PRODUCT_NOUNS = ["Desk", "Monitor", "Keyboard", "Chair", "Lamp", "Cable",
                 "Dock", "Headset", "Webcam", "Stand", "Adapter", "Printer",
                 "Router", "Tablet", "Speaker"]
PRODUCT_ADJ = ["Pro", "Basic", "Ultra", "Compact", "Ergo", "Smart",
               "Classic", "Max", "Lite", "Prime"]


# ---------------------------------------------------------------------------
# Clean baseline generation
# ---------------------------------------------------------------------------

def random_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))


def generate_customers() -> pd.DataFrame:
    rows = []
    for i in range(1, N_CUSTOMERS + 1):
        rows.append({
            "customer_id": f"C-{i:04d}",
            "customer_name": f"{random.choice(FIRST_NAMES)} "
                             f"{random.choice(LAST_NAMES)}",
            "customer_segment": random.choice(SEGMENTS),
            "country": random.choice(COUNTRIES),
            "signup_date": random_date(date(2020, 1, 1),
                                       date(2023, 12, 31)).isoformat(),
        })
    return pd.DataFrame(rows)


def generate_products() -> pd.DataFrame:
    rows = []
    for i in range(1, N_PRODUCTS + 1):
        rows.append({
            "product_id": f"P-{i:03d}",
            "product_name": f"{random.choice(PRODUCT_ADJ)} "
                            f"{random.choice(PRODUCT_NOUNS)} {i:03d}",
            "category": random.choice(CATEGORIES),
            "standard_price": round(random.uniform(5, 500), 2),
            # the LAST N_INACTIVE products are inactive — clean sales
            # never reference them, only injected REL_003 rows do
            "active_status": "inactive" if i > N_PRODUCTS - N_INACTIVE
                             else "active",
        })
    return pd.DataFrame(rows)


def generate_clean_sales(customers: pd.DataFrame,
                         products: pd.DataFrame) -> list[dict]:
    """Every generated row is valid against every V1 check."""
    customer_ids = customers["customer_id"].tolist()
    active = products[products["active_status"] == "active"]
    active_ids = active["product_id"].tolist()
    price_of = dict(zip(active["product_id"], active["standard_price"]))

    rows = []
    for i in range(1, N_SALES + 1):
        product_id = random.choice(active_ids)
        rows.append({
            "sale_id": f"S-{i:05d}",
            "sale_date": random_date(date(SALES_YEAR, 1, 1),
                                     date(SALES_YEAR, 12, 31)).isoformat(),
            "customer_id": random.choice(customer_ids),
            "product_id": product_id,
            "quantity": random.randint(1, 10),          # median ~5
            "unit_price": round(price_of[product_id]
                                * random.uniform(0.9, 1.1), 2),
            "discount": random.choice(CLEAN_DISCOUNTS),
            "region": random.choice(REGIONS),
            "sales_channel": random.choice(CHANNELS),
        })
    return rows


def generate_targets() -> pd.DataFrame:
    rows = []
    for month in range(1, 13):
        for region in REGIONS:
            rows.append({
                "month": f"{SALES_YEAR}-{month:02d}",
                "region": region,
                "target_revenue": round(random.uniform(40_000, 120_000), -2),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Error injection — one error per row, disjoint rows, full manifest
# ---------------------------------------------------------------------------

class Injector:
    """Hands out disjoint sales-row indices and writes the manifest."""

    def __init__(self, n_rows: int):
        self._pool = list(range(n_rows))
        random.shuffle(self._pool)
        self.manifest: list[dict] = []

    def take(self, n: int) -> list[int]:
        if n > len(self._pool):
            raise RuntimeError("Not enough clean rows left for injection")
        return [self._pool.pop() for _ in range(n)]

    def log(self, table: str, row_ref: str, error_class: str,
            column: str | None, detail: str) -> None:
        self.manifest.append({
            "table": table,
            "row_ref": row_ref,
            "error_class": error_class,
            "column": column,
            "detail": detail,
        })


def inject_sales_errors(sales: list[dict], inj: Injector) -> list[dict]:
    """Mutates sales rows in place according to ERROR_PLAN; returns the
    final row list (incl. inserted duplicates)."""

    def ref(idx: int) -> str:
        return sales[idx]["sale_id"]

    # SCH_002 — wrong but unambiguously parseable date formats (FIX)
    formats = ["%d.%m.%Y", "%Y/%m/%d", "%d-%m-%Y"]
    for k, idx in enumerate(inj.take(ERROR_PLAN["SCH_002"])):
        iso = sales[idx]["sale_date"]
        wrong = date.fromisoformat(iso).strftime(formats[k % len(formats)])
        sales[idx]["sale_date"] = wrong
        inj.log("sales", ref(idx), "SCH_002", "sale_date",
                f"non-ISO date format '{wrong}' (was {iso})")

    # COM_001 / COM_002 — missing mandatory FKs
    for idx in inj.take(ERROR_PLAN["COM_001"]):
        sales[idx]["customer_id"] = ""
        inj.log("sales", ref(idx), "COM_001", "customer_id",
                "customer_id missing")
    for idx in inj.take(ERROR_PLAN["COM_002"]):
        sales[idx]["product_id"] = ""
        inj.log("sales", ref(idx), "COM_002", "product_id",
                "product_id missing")

    # COM_003 — missing sale_date
    for idx in inj.take(ERROR_PLAN["COM_003"]):
        sales[idx]["sale_date"] = ""
        inj.log("sales", ref(idx), "COM_003", "sale_date",
                "sale_date missing")

    # COM_004 — missing quantity / unit_price (split half/half)
    com4 = inj.take(ERROR_PLAN["COM_004"])
    for k, idx in enumerate(com4):
        col = "quantity" if k % 2 == 0 else "unit_price"
        sales[idx][col] = ""
        inj.log("sales", ref(idx), "COM_004", col, f"{col} missing")

    # COM_005 — missing optional fields (round-robin)
    optional = ["discount", "region", "sales_channel"]
    for k, idx in enumerate(inj.take(ERROR_PLAN["COM_005"])):
        col = optional[k % len(optional)]
        sales[idx][col] = ""
        inj.log("sales", ref(idx), "COM_005", col,
                f"optional field {col} missing")

    # REL_001 / REL_002 — FKs that do not exist in the master tables
    for k, idx in enumerate(inj.take(ERROR_PLAN["REL_001"])):
        bad = f"C-{9900 + k}"
        sales[idx]["customer_id"] = bad
        inj.log("sales", ref(idx), "REL_001", "customer_id",
                f"customer_id {bad} does not exist in customers")
    for k, idx in enumerate(inj.take(ERROR_PLAN["REL_002"])):
        bad = f"P-{900 + k}"
        sales[idx]["product_id"] = bad
        inj.log("sales", ref(idx), "REL_002", "product_id",
                f"product_id {bad} does not exist in products")

    # REL_003 — sale references an inactive product
    inactive_ids = [f"P-{i:03d}"
                    for i in range(N_PRODUCTS - N_INACTIVE + 1,
                                   N_PRODUCTS + 1)]
    for k, idx in enumerate(inj.take(ERROR_PLAN["REL_003"])):
        pid = inactive_ids[k % len(inactive_ids)]
        sales[idx]["product_id"] = pid
        inj.log("sales", ref(idx), "REL_003", "product_id",
                f"sale references inactive product {pid}")

    # BIZ_001 / BIZ_002 — non-positive amounts
    for idx in inj.take(ERROR_PLAN["BIZ_001"]):
        bad = random.choice([-5, -3, -1, 0])
        sales[idx]["quantity"] = bad
        inj.log("sales", ref(idx), "BIZ_001", "quantity",
                f"quantity {bad} <= 0")
    for idx in inj.take(ERROR_PLAN["BIZ_002"]):
        bad = round(random.uniform(-80, -1), 2)
        sales[idx]["unit_price"] = bad
        inj.log("sales", ref(idx), "BIZ_002", "unit_price",
                f"unit_price {bad} <= 0")

    # BIZ_003 — discount outside [0, max_discount=0.5]
    for k, idx in enumerate(inj.take(ERROR_PLAN["BIZ_003"])):
        bad = -0.1 if k < 2 else round(random.uniform(0.55, 0.95), 2)
        sales[idx]["discount"] = bad
        inj.log("sales", ref(idx), "BIZ_003", "discount",
                f"discount {bad} outside [0, 0.5]")

    # BIZ_004 — sale_date in the future (far future: robust against
    # whenever the pipeline is actually run)
    for idx in inj.take(ERROR_PLAN["BIZ_004"]):
        future = random_date(date(2030, 1, 1), date(2030, 12, 31)).isoformat()
        sales[idx]["sale_date"] = future
        inj.log("sales", ref(idx), "BIZ_004", "sale_date",
                f"sale_date {future} is in the future")

    # BIZ_005 — invalid region (first 5 mappable via synonyms -> FIX,
    # last 3 unmappable -> DROP fallback)
    bad_regions = ["NORTH ", "Sued", "ZENTRAL", "west ", "EAST",
                   "Atlantis", "Mordor", "Springfield"]
    for k, idx in enumerate(inj.take(ERROR_PLAN["BIZ_005"])):
        sales[idx]["region"] = bad_regions[k]
        inj.log("sales", ref(idx), "BIZ_005", "region",
                f"region '{bad_regions[k]}' not in allowed list")

    # BIZ_006 — invalid channel (5 mappable, 2 unmappable)
    bad_channels = ["Webshop", "STORE ", "Reseller", "WEB", "Online ",
                    "fax", "carrier-pigeon"]
    for k, idx in enumerate(inj.take(ERROR_PLAN["BIZ_006"])):
        sales[idx]["sales_channel"] = bad_channels[k]
        inj.log("sales", ref(idx), "BIZ_006", "sales_channel",
                f"sales_channel '{bad_channels[k]}' not in allowed list")

    # BIZ_007 — extreme quantity outliers (clean median ~5, factor 10
    # -> threshold ~50; injected values are far beyond)
    for idx in inj.take(ERROR_PLAN["BIZ_007"]):
        bad = random.randint(350, 700)
        sales[idx]["quantity"] = bad
        inj.log("sales", ref(idx), "BIZ_007", "quantity",
                f"quantity {bad} is an extreme outlier (median ~5)")

    # UNI_001 — duplicate sale_id: copy otherwise-CLEAN rows (taken from
    # the pool so they carry no other injected error) and insert the
    # copies at random positions
    for idx in inj.take(ERROR_PLAN["UNI_001"]):
        dup = dict(sales[idx])
        sales.insert(random.randint(0, len(sales)), dup)
        inj.log("sales", dup["sale_id"], "UNI_001", "sale_id",
                f"duplicate sale_id {dup['sale_id']}")

    return sales


def inject_master_duplicates(customers: pd.DataFrame,
                             products: pd.DataFrame,
                             inj: Injector) -> tuple[pd.DataFrame,
                                                     pd.DataFrame]:
    # UNI_002 — duplicate customer rows
    dup_c = customers.sample(n=ERROR_PLAN["UNI_002"], random_state=SEED)
    for _, row in dup_c.iterrows():
        inj.log("customers", row["customer_id"], "UNI_002", "customer_id",
                f"duplicate customer_id {row['customer_id']}")
    customers = pd.concat([customers, dup_c], ignore_index=True)
    customers = customers.sample(frac=1, random_state=SEED)\
                         .reset_index(drop=True)

    # UNI_003 — duplicate product rows (active ones, so the duplicate
    # itself triggers nothing else)
    active = products[products["active_status"] == "active"]
    dup_p = active.sample(n=ERROR_PLAN["UNI_003"], random_state=SEED)
    for _, row in dup_p.iterrows():
        inj.log("products", row["product_id"], "UNI_003", "product_id",
                f"duplicate product_id {row['product_id']}")
    products = pd.concat([products, dup_p], ignore_index=True)\
                 .reset_index(drop=True)
    return customers, products


# ---------------------------------------------------------------------------
# Self-check — the generator verifies its own bookkeeping before writing
# ---------------------------------------------------------------------------

def self_check(sales: list[dict], manifest: list[dict]) -> None:
    assert len(manifest) == EXPECTED_TOTAL, \
        f"manifest has {len(manifest)} entries, expected {EXPECTED_TOTAL}"

    counts = {}
    for e in manifest:
        counts[e["error_class"]] = counts.get(e["error_class"], 0) + 1
    assert counts == ERROR_PLAN, f"manifest counts deviate: {counts}"

    # spot checks against the actual data
    n_missing_cust = sum(1 for r in sales if r["customer_id"] == "")
    assert n_missing_cust == ERROR_PLAN["COM_001"]

    ids = [r["sale_id"] for r in sales]
    n_dupes = len(ids) - len(set(ids))
    assert n_dupes == ERROR_PLAN["UNI_001"]

    unknown_cust = sum(1 for r in sales
                       if str(r["customer_id"]).startswith("C-99"))
    assert unknown_cust == ERROR_PLAN["REL_001"]

    assert len(sales) == N_SALES + ERROR_PLAN["UNI_001"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(outdir: str = "data/raw") -> None:
    random.seed(SEED)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    # 1. clean baseline
    customers = generate_customers()
    products = generate_products()
    sales = generate_clean_sales(customers, products)
    targets = generate_targets()

    # 2. controlled injection
    inj = Injector(N_SALES)
    sales = inject_sales_errors(sales, inj)
    customers, products = inject_master_duplicates(customers, products, inj)

    # 3. verify bookkeeping, then write
    self_check(sales, inj.manifest)

    with open(out / "sales_raw.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SALES_COLUMNS)
        writer.writeheader()
        writer.writerows(sales)

    customers.to_excel(out / "customers_raw.xlsx", index=False)
    products.to_excel(out / "products_raw.xlsx", index=False)
    targets.to_excel(out / "monthly_targets.xlsx", index=False)

    manifest_doc = {
        "seed": SEED,
        "generated_for": "Data Quality Audit System V1 — demo dataset",
        "scope_note": ("Ground truth of INTENTIONALLY INJECTED demo errors. "
                       "Detection claims refer to this manifest only, not "
                       "to all possible data errors."),
        "total_injected_errors": len(inj.manifest),
        "counts_by_class": dict(sorted(
            ERROR_PLAN.items())),
        "errors": inj.manifest,
    }
    with open(out / "injected_errors.json", "w") as f:
        json.dump(manifest_doc, f, indent=2)

    # 4. summary
    print(f"Demo data written to {out.resolve()}")
    print(f"  sales_raw.csv          {len(sales):>6} rows "
          f"(= {N_SALES} clean + {ERROR_PLAN['UNI_001']} duplicates)")
    print(f"  customers_raw.xlsx     {len(customers):>6} rows")
    print(f"  products_raw.xlsx      {len(products):>6} rows")
    print(f"  monthly_targets.xlsx   {len(targets):>6} rows")
    print(f"  injected_errors.json   {len(inj.manifest):>6} entries "
          f"({len(ERROR_PLAN)} error classes)")
    print()
    print("Injected errors by class:")
    for check_id, n in sorted(ERROR_PLAN.items()):
        print(f"  {check_id}  {n:>3}")
    print(f"  TOTAL    {EXPECTED_TOTAL:>3}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate seeded demo data with an error manifest")
    parser.add_argument("--outdir", default="data/raw",
                        help="output directory (default: data/raw)")
    main(parser.parse_args().outdir)
