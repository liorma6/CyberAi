# Replaying a login investigation

In the seed-42 test stream, 261 distinct login events triggered a rule, the forest, or both. Correlation grouped them into 192 cases. Eighty-seven cases had insufficient evidence for an ATT&CK candidate under the project mapping criteria.

## One account, two triggers

Case `case-e-51d9170e7544d3e64f6f727a` concerns account `acct-025` at `203.0.113.14` on 19 October 2026. The five timeline entries below come from the generated `events/test.jsonl` file. Line numbers are one-based. The case JSON also includes the account's historical source records.

| File line | UTC | Login | Event ID | Detector decision |
| ---: | --- | --- | --- | --- |
| 92 | 18:31:51 | Failure | e-30e0ee795486334bd5694a38 | Supporting event |
| 93 | 18:32:12 | Failure | e-1a600807a78f49f2a261d6dc | Supporting event |
| 94 | 18:32:25 | Failure | e-379d2349a54e507383da6bc6 | Supporting event |
| 95 | 18:32:45 | Failure | e-51d9170e7544d3e64f6f727a | Forest score 0.628822, above threshold 0.621293 |
| 96 | 18:33:01 | Success | e-9fdcf6ea0ac4a07c32742991 | R1, R4 and forest score 0.636677 |

**R1** fired on the success because the same account and IP produced four failures within the preceding five minutes. **R4** fired because none of the account's 82 earlier successes occurred in the 17:00–19:59 UTC band around the current hour. The model used the smoothed hour share `(0 + 3/24) / (82 + 1)`. The four failures, 82 successes and current login make up the 87 source records needed to replay this decision with the frozen forest.

The failure sequence supports a **Brute Force (T1110)** hypothesis. The success after that sequence, at a historically rare hour, also supports a **Valid Accounts (T1078)** hypothesis. A legitimate user retrying a password outside their usual hours could produce this sequence. The analyst needs identity-provider details and independent confirmation of who controlled the successful session. [MITRE T1110](https://attack.mitre.org/techniques/T1110/) · [MITRE T1078](https://attack.mitre.org/techniques/T1078/)

## Reproduce the case

Run from the project directory using the Python environment with `requirements-ml.txt` installed.

```powershell
python -m generate_dataset --seed 42
python -m casebook runs/dataset-v1-seed-42
python -m casebook runs/dataset-v1-seed-42 --case case-e-51d9170e7544d3e64f6f727a
python -m casebook runs/dataset-v1-seed-42 --replay e-9fdcf6ea0ac4a07c32742991
```

The default view lists case IDs, time ranges, accounts and candidate techniques. The detail view includes raw source fields, file and line, a timeline ordered by UTC and input order, rule evidence, features, the forest score and its threshold. The replay command extracts the cited raw records and checks all six fields of its verification result. A mismatch produces a nonzero exit code. The pinned detector is reconstructed from the checksummed training and calibration streams. Case generation and replay read only event data and the manifest.

## Correlation and mapping policy

Two successive triggers for the same account and IP can join a case when separated by at most five minutes. Triggers also join when they cite a common direct rule event, including an earlier trigger. These links can form a chain longer than five minutes. Shared IP alone or shared long-term account history does not join cases. Historical successes stay available as evidence separately from the incident timeline.

| Observation at the trigger | Candidate | Additional evidence to seek |
| --- | --- | --- |
| R1 or R2 | T1110 | Authentication details and user context to distinguish retries and shared infrastructure |
| Successful login with at least two of R1, R3 and R4 | T1078 | Owner confirmation, MFA or independent session evidence |
| Model score alone, or only a novelty or rare-hour rule | Insufficient support for a candidate | More context about the account or session |

Each candidate identifies its supporting rules and the evidence is attached to that trigger. Mapping criteria are EvidenceSOC's investigative decisions. The official technique names, versions, STIX identifiers and source links come from MITRE.

## Official ATT&CK data and offline use

`python -m attack_catalog` resolves the official MITRE CTI repository revision, downloads the two Enterprise ATT&CK STIX objects at that exact revision, validates them and atomically updates `runs/attack-cache.json`. The request contains only public catalog identifiers. Subsequent casebook runs use this cache. A failed refresh exits with an error and preserves the previous complete cache.

A clean checkout includes a [versioned snapshot](attack-snapshot.json) with T1110 v2.8 and T1078 v3.0 for offline runs. Every casebook records the chosen source revision and the event-file checksums. For exact reproduction use `--attack-cache attack-snapshot.json`. [Official MITRE source revision](https://github.com/mitre/cti/tree/e79c7c53d13c08cc21ba3ad77d4f8f49bf64ff07)
