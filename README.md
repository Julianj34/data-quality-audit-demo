# Data Quality Audit System

A reproducible portfolio case study for auditing messy business data, detecting data quality issues, documenting cleaning decisions, and producing reporting-ready outputs.

## Overview

This project simulates a common business problem:

A company exports sales, customer, product, and target data from different systems. The raw files contain missing IDs, duplicate records, invalid values, broken relationships, and inconsistent categories. These issues make reporting unreliable.

The pipeline answers one core question:

> How reliable are the available business data, and which specific errors prevent accurate reporting?

```text
Raw Business Data → Validation → Error Diagnosis → Documented Cleaning → Clean Output
```

This is not a dashboard, SaaS app, OCR tool, or machine learning model. It is a focused data quality audit demo.

---

## Key Results

| Metric                           |          Result |
| -------------------------------- | --------------: |
| Rows checked                     |           2,323 |
| Detected issues                  |             142 |
| Detection against error manifest |       142 / 142 |
| Quality score                    | 63/100 → 98/100 |
| Dropped records                  |              88 |
| Fixed records                    |              29 |
| Flagged records                  |              35 |
| Reporting-ready rows             |           1,925 |

The system does not hide uncertainty:

* invalid rows are dropped
* repairable values are fixed and logged
* suspicious but usable rows are flagged for review

---

## Validation Layers

The audit runs five validation layers:

| Layer          | Purpose                                                    |
| -------------- | ---------------------------------------------------------- |
| Schema         | Required columns and data types                            |
| Completeness   | Missing required and optional values                       |
| Uniqueness     | Duplicate IDs                                              |
| Relationships  | Sales records vs. customer/product master data             |
| Business Rules | Invalid values, dates, discounts, categories, and outliers |

All checks produce the same structured error-record format. This makes scoring, cleaning, and reporting consistent.

---

## Input Data

The demo uses four synthetic input files:

```text
data/raw/sales_raw.csv
data/raw/customers_raw.xlsx
data/raw/products_raw.xlsx
data/raw/monthly_targets.xlsx
```

The generator also creates:

```text
data/raw/injected_errors.json
```

This file contains the known demo errors used to verify detection.

---

## Outputs

After running the pipeline, the system creates or updates:

| Output                                     | Description                                               |
| ------------------------------------------ | --------------------------------------------------------- |
| `reports/before_after_summary.md`          | Business-facing summary of findings and score improvement |
| `reports/data_quality_score.md`            | Score, severity distribution, and top error classes       |
| `reports/errors_report.xlsx`               | Full error report by validation layer                     |
| `data/processed/clean_master_dataset.xlsx` | Reporting-ready dataset with revenue and quality flags    |
| `reports/data_dictionary.md`               | Tables, fields, types, keys, and derived columns          |
| `reports/processing_log.txt`               | Timestamped pipeline log                                  |

---

## Example Result

```text
Before: 63/100
After:  98/100

Detected issues: 142
Critical: 58
Major:    66
Minor:    18

Dropped: 88
Fixed:   29
Flagged: 35
```

After cleaning, the dataset contains 1,925 reporting-ready rows and no remaining critical issues.

---

## Project Structure

```text
data-quality-audit-demo/
├── data/
│   ├── raw/
│   ├── processed/
│   └── reference/
├── notebooks/
├── reports/
├── src/
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
└── run_pipeline.py
```

## Folder Overview

* `src/` — Python source code for loading, validating, scoring, cleaning, exporting reports, generating demo data, and verification logic.
* `data/` — Raw demo data, processed clean data, and configuration files.
* `notebooks/` — Step-by-step walkthrough notebook for the portfolio case study.
* `reports/` — Generated audit reports and output summaries.

---


## Verification

The demo data contains intentionally injected errors in:

```text
data/raw/injected_errors.json
```

Expected result:

```text
Known injected demo errors detected: 142 / 142
```

This claim only applies to the controlled synthetic demo errors, not to every possible real-world data issue.

If needed, the standalone verification script is located in:

```text
src/verify_detection.py
```

---

## Notebook Walkthrough

A public walkthrough notebook is available in:

```text
notebooks/01_data_quality_walkthrough.ipynb
```

The notebook explains the audit process step by step and shows the result as a readable portfolio case study.

---

## Configuration

Business rules are stored in:

```text
data/reference/allowed_values.yaml
```

This file controls:

* allowed values
* severity mappings
* cleaning actions
* scoring weights
* traffic-light thresholds
* required columns

Core principle:

```text
Code = Measurement
Config = Rules
Reports = Interpretation
```

---

## Tech Stack

```text
Python
pandas
numpy
openpyxl
pyyaml
```

No dashboard framework, database, OCR, machine learning, or agent system is used.

The goal is transparent, deterministic data quality logic.

---

## License

MIT License.
