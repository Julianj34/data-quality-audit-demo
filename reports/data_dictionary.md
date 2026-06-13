# Data Dictionary

_Generated: 2026-06-13 12:53:04_

Single source of truth for all rules: `data/reference/allowed_values.yaml`.

## sales  (`sales_raw.csv`)

| Column | Type | Req. | Description |
|---|---|---|---|
| sale_id | string | required | Primary key of a sale |
| sale_date | date | required | Date of the sale (ISO 8601 after cleaning) |
| customer_id | string | required | FK -> customers.customer_id |
| product_id | string | required | FK -> products.product_id |
| quantity | numeric | required | Units sold (> 0) |
| unit_price | numeric | required | Price per unit (> 0) |
| discount | numeric | optional | Fractional discount in [0, max_discount] |
| region | string | optional | Sales region (allowed list) |
| sales_channel | string | optional | Channel (allowed list) |

## customers  (`customers_raw.xlsx`)

| Column | Type | Req. | Description |
|---|---|---|---|
| customer_id | string | required | Primary key of a customer |
| customer_name | string | required | Customer display name |
| customer_segment | string | optional | Allowed values: `B2B`, `B2C`, `Enterprise` |
| country | string | optional | Customer country |
| signup_date | date | optional | Customer signup date |

## products  (`products_raw.xlsx`)

| Column | Type | Req. | Description |
|---|---|---|---|
| product_id | string | required | Primary key of a product |
| product_name | string | required | Product display name |
| standard_price | numeric | required | Catalogue price |
| active_status | string | required | Allowed values: `active`, `inactive` |
| category | string | optional | Product category |

## targets  (`monthly_targets.xlsx`)

| Column | Type | Req. | Description |
|---|---|---|---|
| month | string | required | Target month (YYYY-MM) |
| region | string | required | Sales region (allowed list) |
| target_revenue | numeric | required | Monthly revenue target per region |

## Derived columns (clean_master_dataset)

| Column | Definition |
|---|---|
| gross_revenue | quantity × unit_price |
| net_revenue | gross_revenue × (1 − discount) |
| quality_flag | semicolon-separated flag codes (e.g. REL_003, BIZ_007) |

