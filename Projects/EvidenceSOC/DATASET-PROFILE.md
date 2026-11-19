# Authentication dataset profile

Generator version 1, seed 42. Manifest SHA-256: `c86e12989abd40d66c2ba17686a046215672887388c223af23d55c7fde15f9df`.

| Period | First day (UTC) | End (exclusive) | Events | Scenarios |
| --- | --- | --- | ---: | ---: |
| train | 2026-09-07 | 2026-10-05 | 2877 | 2210 |
| calibration | 2026-10-05 | 2026-10-19 | 1647 | 1126 |
| test | 2026-10-19 | 2026-11-02 | 1694 | 1150 |

| Measure | Train | Calibration |
| --- | ---: | ---: |
| Distinct accounts | 48 | 48 |
| Failed login events | 667 | 538 |
| routine_login scenarios | 1935 | 935 |
| password_mistake scenarios | 188 | 87 |
| approved_travel scenarios | 59 | 27 |
| shared_gateway scenarios | 28 | 14 |
| guess_sequence scenarios | 0 | 22 |
| multi_account_failures scenarios | 0 | 17 |
| unusual_account_use scenarios | 0 | 24 |

## Overlap in calibration

Counts are scenarios grouped using evaluation IDs. Rows can overlap. These counts describe the input before fitting detectors.

| Observed in a scenario | Benign | Suspicious |
| --- | ---: | ---: |
| Failures on at least three accounts | 14 | 17 |
| Overnight success (UTC) | 58 | 11 |
| Three or more failures then a success on one account | 46 | 16 |

Suspicious calibration scenarios: 63 of 1126 (5.6%). The test period contributes only its manifest counts and file-integrity checks to this report.
