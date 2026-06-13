Data Quality Audit System

A reproducible portfolio case study for auditing messy business data, detecting data quality issues, documenting cleaning decisions, and producing reporting-ready outputs.

Overview

This project simulates a common business problem:

A company exports sales, customer, product, and target data from different systems. The raw files contain missing IDs, duplicate records, invalid values, broken relationships, and inconsistent categories. These issues make reporting unreliable.

The pipeline answers one core question:

How reliable are the available business data, and which specific errors prevent accurate reporting?

Raw Business Data → Validation → Error Diagnosis → Documented Cleaning → Clean Output

This is not a dashboard, SaaS app, OCR tool, or machine learning model. It is a focused data quality audit demo.

Key Results
Metric	Result
Rows checked	2,323
Detected issues	142
Detection against error manifest	142 / 142
Quality score	63/100 🔴 → 98/100 🟢
Dropped records	88
Fixed records	29
Flagged records	35
Reporting-ready rows	1,925
Tests	33 / 33 passing

The system does not hide uncertainty:

invalid rows are dropped
repairable values are fixed and logged
suspicious but usable rows are flagged for review
Validation Layers

The audit runs five validation layers:

Layer	Purpose
Schema	Required columns and data types
Completeness	Missing required and optional values
Uniqueness	Duplicate IDs
Relationships	Sales records vs. customer/product master data
Business Rules	Invalid values, dates, discounts, categories, and outliers

All checks produce the same structured error-record format. This makes scoring, cleaning, and reporting consistent.

Input Data

The demo uses four synthetic input files:

data/raw/sales_raw.csv
data/raw/customers_raw.xlsx
data/raw/products_raw.xlsx
data/raw/monthly_targets.xlsx

The generator also creates:

data/raw/injected_errors.json

This file contains the known demo errors used to verify detection.

Outputs

After running the pipeline, the system creates:

Output	Description
before_after_summary.md	Business-facing summary of findings and score improvement
data_quality_score.md	Score, severity distribution, and top error classes
errors_report.xlsx	Full error report by validation layer
clean_master_dataset.xlsx	Reporting-ready dataset with revenue and quality flags
data_dictionary.md	Tables, fields, types, keys, and derived columns
processing_log.txt	Timestamped pipeline log
Example Result
Before: 63/100 🔴
After:  98/100 🟢

Detected issues: 142
Critical: 58
Major:    66
Minor:    18

Dropped: 88
Fixed:   29
Flagged: 35

After cleaning, the dataset contains 1,925 reporting-ready rows and no remaining critical issues.
