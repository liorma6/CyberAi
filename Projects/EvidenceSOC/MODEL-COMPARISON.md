# Isolation Forest and login rules on the held-out period

Dataset seed 42, manifest SHA-256 `c86e12989abd40d66c2ba17686a046215672887388c223af23d55c7fde15f9df`. Compared `iforest-v1` (scikit-learn 1.8.0) with `rules-v1`.

The forest fitted 2877 earlier events. On the next 1647 events the rules raised 178 alerts. The model admitted 177 events at a threshold of 0.621292575388. Equal scores stay together. Both cutoffs were frozen before test scoring.

The test period contains 1694 events in 1150 scenarios. TP, FP, FN and TN count scenarios. Workload counts individual triggering events.

| Detector | TP | FP | FN | TN | Precision | Recall | F1 | Event alerts | False event alerts | False alerts / 1k events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Rules | 54 | 96 | 12 | 988 | 36.0% | 81.8% | 50.0% | 187 | 118 | 69.66 |
| Isolation Forest | 40 | 48 | 26 | 1036 | 45.5% | 60.6% | 51.9% | 157 | 63 | 37.19 |

## Scenarios flagged by family

| Scenario family | Total | Rules | Isolation Forest |
| --- | ---: | ---: | ---: |
| approved_travel | 30 | 27 | 23 |
| guess_sequence | 23 | 18 | 15 |
| multi_account_failures | 20 | 18 | 14 |
| password_mistake | 92 | 54 | 11 |
| routine_login | 948 | 1 | 0 |
| shared_gateway | 14 | 14 | 14 |
| unusual_account_use | 23 | 18 | 11 |

## Cases for analyst review

One example per available outcome. Each event ID resolves to a source login in the test stream. For a missed scenario the table shows its highest model score.

| Finding | Scenario family | Scenario | Event | Model score | Rules at event |
| --- | --- | --- | --- | ---: | --- |
| rules only, benign | password_mistake | s-89b21c3bc099739c91de413f | e-3ee373b4e88859ddc5dd5f8b | 0.544443 | R1 |
| model only, suspicious | guess_sequence | s-67a0deec1a4b0992a834f352 | e-e379cc86279edbac09860e01 | 0.628822 | None |
| both missed, suspicious | multi_account_failures | s-e7f6dec2615b9d20acf70176 | e-2624054343a21d52d12e73a1 | 0.582454 | None |
| rules only, suspicious | guess_sequence | s-a9f99d4f9545201e6ecad0f5 | e-61b0d81fb60c498a61d9e4fe | 0.618342 | R1, R4 |
| model only, benign | password_mistake | s-ba2c132986b9956c14e4790d | e-c02ac9eb369c540869210f59 | 0.636045 | None |

These results describe one synthetic organization and seed. Approved travel and unusual account use intentionally share observable patterns. Travel approval or user confirmation can help resolve those cases.
