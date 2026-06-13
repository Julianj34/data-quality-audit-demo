# Data Quality Score

_Generated: 2026-06-13 12:53:04_

## Audit result (raw data)

**Overall Quality Score: 63/100 🔴**

| Severity | Count | Action |
|---|---|---|
| Critical | 58 | ACT |
| Major | 66 | CHECK |
| Minor | 18 | OBSERVE |
| **Total** | **142** | |

Weighted error points: 86.2 (37.1 per 1000 rows, 2323 rows checked).

## Top error classes (raw)

| Check | Count |
|---|---|
| COM_005 | 13 |
| REL_001 | 11 |
| BIZ_003 | 10 |
| SCH_002 | 9 |
| COM_001 | 8 |

## After cleaning

**Overall Quality Score: 98/100 🟢**

Before: 63/100 🔴  →  After: 98/100 🟢

Residual issues are documented (kept & flagged), not hidden: 7 major, 18 minor.

## Traffic light thresholds (config)

- 🟢 green: score >= 90
- 🟡 yellow: 70–89
- 🔴 red: < 70
