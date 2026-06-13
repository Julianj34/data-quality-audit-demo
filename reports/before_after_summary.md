# Before / After Summary

_Generated: 2026-06-13 12:53:04_

## 1. Starting point

Sales, customer and product data exported from several systems. Missing and unknown IDs, duplicates, invalid amounts, wrong date formats and inconsistent categories make reliable reporting impossible.

Total rows checked: 2323.

## 2. Validation

Five read-only validation layers sharing one error-record format:

Schema · Completeness · Uniqueness · Relationships · Business Rules.

## 3. Findings (raw)

**Quality Score: 63/100 🔴** — 142 issues (58 critical, 66 major, 18 minor).

| Check | Found | Action |
|---|---|---|
| BIZ_001 | 8 | DROP |
| BIZ_002 | 7 | DROP |
| BIZ_003 | 10 | FIX |
| BIZ_004 | 6 | DROP |
| BIZ_005 | 8 | FIX |
| BIZ_006 | 7 | FIX |
| BIZ_007 | 5 | FLAG |
| COM_001 | 8 | DROP |
| COM_002 | 8 | DROP |
| COM_003 | 6 | DROP |
| COM_004 | 8 | DROP |
| COM_005 | 13 | FLAG |
| REL_001 | 11 | DROP |
| REL_002 | 8 | DROP |
| REL_003 | 7 | FLAG |
| SCH_002 | 9 | FIX |
| UNI_001 | 6 | DROP |
| UNI_002 | 4 | DROP |
| UNI_003 | 3 | DROP |

## 4. Cleaning

- **Fixed:** 29 (date format, discount capping, region/channel mapping)
- **Dropped:** 88 (missing/invalid mandatory data, duplicates, broken FKs)
- **Flagged:** 35 (kept, but marked)

- Of these, 5 FIX attempts escalated to DROP (unrepairable).

Drop distribution: BIZ_001 8, BIZ_002 7, BIZ_004 6, BIZ_005 3, BIZ_006 2, COM_001 8, COM_002 8, COM_003 6, COM_004 8, REL_001 11, REL_002 8, UNI_001 6, UNI_002 4, UNI_003 3.

## 5. Residual uncertainty

**Documented fix notes** (repaired and marked, no open uncertainty):

- BIZ_003: 10 discount values capped to the maximum

**Remaining residual uncertainty** (kept on purpose, marked in `quality_flag`):

- BIZ_007: 5 revenue outliers
- COM_005: 13 optional fields missing
- REL_003: 7 inactive products sold

After cleaning, 25 documented notes remain (7 major, 18 minor) — no critical errors.

## 6. Result

### Before: 63/100 🔴  →  After: 98/100 🟢

The cleaned master dataset holds 1925 reporting-ready rows with computed revenue (gross/net) and quality flags. Reports on revenue, customers and products are now reliable.

Dropped rows are excluded from reporting; flagged rows remain visible and reviewable — not hidden, but consciously decided.

## Verifiability

Known injected demo errors detected: 142 / 142.

_This claim refers only to the controlled, known demo errors — not to all possible data errors._
