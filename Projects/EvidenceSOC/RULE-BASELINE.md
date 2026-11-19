# Rule baseline on calibration

Rule set `rules-v1`, dataset seed 42. Manifest SHA-256 `c86e12989abd40d66c2ba17686a046215672887388c223af23d55c7fde15f9df`.

History contains 2877 training events. The next 1647 events belong to 1126 labeled scenarios. One alert is counted per trigger event. A scenario is flagged if it owns at least one trigger. Supporting records can belong to earlier scenarios and do not earn detection credit.

| Rule | TP | FP | FN | TN | Precision | Recall | F1 | Alerts | False alerts / 1k events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Union | 55 | 83 | 8 | 980 | 39.9% | 87.3% | 54.7% | 178 | 64.97 |
| R1 | 20 | 46 | 43 | 1017 | 30.3% | 31.7% | 31.0% | 91 | 35.82 |
| R2 | 14 | 13 | 49 | 1050 | 51.9% | 22.2% | 31.1% | 27 | 7.89 |
| R3 | 6 | 6 | 57 | 1057 | 50.0% | 9.5% | 16.0% | 12 | 3.64 |
| R4 | 37 | 34 | 26 | 1029 | 52.1% | 58.7% | 55.2% | 71 | 20.64 |

The union produced 107 false alerts across 83 benign scenarios. Individual rule rows overlap.

| Scenario family | Label | Flagged | Total |
| --- | --- | ---: | ---: |
| approved_travel | benign | 23 | 27 |
| password_mistake | benign | 46 | 87 |
| routine_login | benign | 0 | 935 |
| shared_gateway | benign | 14 | 14 |
| guess_sequence | suspicious | 21 | 22 |
| multi_account_failures | suspicious | 14 | 17 |
| unusual_account_use | suspicious | 20 | 24 |

## Audit examples

The first matching example in input order is shown for each available outcome.

- true_positive, multi_account_failures, scenario `s-3c6bad3494fc712b5567cd27`, events e-32fb59fd0c00f8ff2a314f1d, rules R2.
- false_positive, password_mistake, scenario `s-ee3c8687b704eced5b9df42d`, events e-506f6bc0ee6f5a9cf4460236, rules R1.
- false_negative, unusual_account_use, scenario `s-5fb56c40072a508767d9d83b`, events e-7fdfc5c0876cacddab204463.

These are descriptive calibration results for synthetic data. The test period remains reserved for the later comparison.
