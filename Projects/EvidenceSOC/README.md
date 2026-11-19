# EvidenceSOC

EvidenceSOC investigates suspicious authentication activity and records the event IDs behind each observation. The five-event demo yields two investigation cases. For the full dataset, the historical rule engine detects suspicious patterns and measures alert workload on a separate calibration period.

See the [development history](HISTORY.md) for published commits and their CI results.

## Run

From the repository root:

```powershell
cd Projects/EvidenceSOC
uv sync --frozen
uv run --frozen python -m unittest -v
uv run --frozen python -m evidencesoc
```

With Python 3.13 or 3.14 installed, the same two Python commands also work without uv. To inspect another file, pass its path to `python -m evidencesoc`. Use the fields in `demo.jsonl`. Timestamps need a timezone offset, IDs must be unique, and each line represents one login result. Records are sorted by UTC time, with file order as the tiebreaker.

## What the demo checks

- `case-E04` links three failures to a subsequent success for the same account and IP within an inclusive five-minute window. Each success resets that sequence.
- `case-E05` records a successful sign-in in the 22:00–05:00 UTC window (end exclusive). Work schedules and local time zones are unknown, so this signal requires context.

Both demo cases retain the source events. The four rules used for the detector comparison are documented under [Historical features and rule baseline](#historical-features-and-rule-baseline).

## Try the local model

Start [Ollama for Windows](https://ollama.com/download/windows), then run:

```powershell
ollama pull llama3.1:8b-instruct-q4_K_M
uv run --frozen python -m evidencesoc --explain
ollama ps
```

The adapter sends each case to the loopback API. Llama selects a reason, evidence IDs and a follow-up from a constrained vocabulary. Python checks that the IDs and follow-up match the selected observation, then renders the factual sentence. This first integration tests grounding and runtime placement. Free-form explanation evaluation comes in a later milestone.

A successful response includes the model identifier, elapsed time, generated token count and available runtime placement data. A positive `vram_bytes` indicates some model memory was placed on the GPU. Missing placement data means placement is unknown. The CLI exits with status 2 if any requested explanation fails, while still printing the original case and its evidence. The default command does not call a model.

## Generate the experiment data

From this directory, run:

```powershell
python -m generate_dataset --seed 42
python -m dataset_profile runs/dataset-v1-seed-42
python -m evidencesoc runs/dataset-v1-seed-42/events/calibration.jsonl
```

The generator writes three chronological event streams, separate answer keys under `truth/`, and a manifest with UTC boundaries, counts and SHA-256 hashes. Repeating the command checks and reuses identical output. A different seed generates another sample in its own directory. Use `--out` to select the destination.

The first 28 days represent legitimate account history. The following 14 days support threshold calibration, and the final 14 days are reserved for evaluation after the thresholds are frozen. Entire scenarios stay within one period. The generator shares the same 48 synthetic account profiles across periods to model a continuing organization. Weekday and weekend activity volumes differ. Each source IP has one synthetic country and some accounts share gateways.

Each detector input contains a timestamp, account, IP, outcome, device and country. The random event ID links findings to source records and is excluded from model features. The original five-field demo remains supported. Each evaluation record maps one scenario ID to its family, synthetic label and constituent event IDs. The unit for scoring a detection will be a scenario. Feature extraction must use events available at that time. Use the truth files only for offline evaluation and calibration.

| Scenario family | Data-generation assumption |
| --- | --- |
| Routine login | The user signs in around their usual working hour. Some profiles work at night. |
| Password mistake | A legitimate user has one or more failures before a successful sign-in. |
| Approved travel | A legitimate user signs in through a remote IP in a different country, sometimes with a new device. |
| Shared gateway | Several users experience failures from the same egress IP before a successful sign-in. |
| Guess sequence | An injected suspicious sequence produces several failures for one account and may end in success. |
| Multi-account failures | An injected suspicious sequence produces failures for multiple accounts from one source. |
| Unusual account use | A simulated unauthorized sign-in uses the same remote-access distribution as approved travel. |

These are synthetic login records constructed offline. A scenario label records the simulator's intended context. The paired travel and unauthorized scenarios deliberately share the same observable pattern. An analyst would need additional evidence, such as a shift roster or account-owner confirmation, to resolve individual ambiguous cases.

The [generated dataset profile](DATASET-PROFILE.md) gives the canonical seed's fingerprint, class counts and overlapping patterns.

## Historical features and rule baseline

```powershell
python -m evidencesoc --rules --history runs/dataset-v1-seed-42/events/train.jsonl runs/dataset-v1-seed-42/events/calibration.jsonl
python -m rule_baseline runs/dataset-v1-seed-42
```

Add `--feature-rows` to the first command to export features for every scored record, or `--json` to the second for machine-readable metrics. The existing `--explain` command runs the two-case Llama integration.

| Rule | Trigger | Evidence |
| --- | --- | --- |
| R1 | Fifth failure for one account and IP within five minutes, or a success after at least three failures within that window | IDs of matching failures and the current event |
| R2 | A failure increases the source IP's distinct failed accounts from three to four in five minutes | IDs of failures from the IP and the current event |
| R3 | A success presents both an unseen device and an unseen country. The account must have at least five prior successes with device data and five with country data. | Current event, account history boundaries, sample counts and novelty flags |
| R4 | On a success after at least ten prior successes, fewer than 5% of prior successes occurred in the current UTC hour or either adjacent hour. The band wraps at midnight. | Current event, account history boundaries and hour-band counts |

Thresholds are fixed design choices for version `rules-v1`. The rolling failure windows include the five-minute boundary. Earlier input records break ties at the same timestamp. R1 counts failures throughout the window, including across intervening successes. R2 triggers on a fresh threshold crossing. History is updated after scoring each record. Missing device or country history yields an unknown novelty value. Historical rules use all prior successes for that account; a success establishes observed behavior, not an analyst verdict about legitimacy.

Each alert carries the triggering event ID, feature values, rule IDs and supporting references. To reproduce a historical claim, replay that account's successes from the beginning of the history up to the trigger, excluding the trigger. The alert includes the first and last contributing IDs. Event IDs are lookup keys and should be excluded from the model feature matrix.

The [calibration report](RULE-BASELINE.md) includes combined and individual rule metrics, scenario families and traceable examples. Evaluation attributes an alert to the scenario owning its trigger and counts repeated triggers separately when estimating analyst workload.

## Reproduce the held-out detector comparison

From the project directory, use Python 3.13 or 3.14. These commands install the pinned ML dependencies in the project environment and reproduce the [stage 3 report](MODEL-COMPARISON.md).

```powershell
uv sync --frozen
uv pip install --python .venv/Scripts/python.exe -r requirements-ml.txt
.venv/Scripts/python.exe -m generate_dataset --seed 42
.venv/Scripts/python.exe -m model_comparison runs/dataset-v1-seed-42
.venv/Scripts/python.exe -m unittest -v
```

On Linux, the environment interpreter is `.venv/bin/python`. For machine-readable metrics use `--json`. Use `--scores` to include every test event ID, its six input values, anomaly score, model decision and triggered rules.

The forest fits 200 trees on 256-event subsamples of the earlier benign period, with random seed 42. Its inputs are the login outcome, recent account/IP failures, distinct failed accounts on the IP, device novelty, country novelty and the account's historical share of successes around the current UTC hour. Unknown novelty is encoded as −1. The score is the negative of scikit-learn's `score_samples`, so a larger value is more anomalous. The threshold admits the largest top-scoring group of calibration events that fits within the rules' alert count, including ties as a group. It remains fixed during the test period. Only the historical login features continue to update as events arrive.

On the held-out period the forest halved the number of benign scenarios flagged (96 to 48). Password-mistake scenarios account for much of that improvement (54 to 11). It also missed 26 suspicious scenarios, compared with 12 for the rules. Both detectors flagged every shared-gateway scenario. The results support retaining the rules when coverage matters and evaluating the model score as a prioritization signal.

## Investigate a detection

Run `python -m casebook runs/dataset-v1-seed-42` to list the correlated cases. Pass `--case CASE_ID` for a UTC timeline with the original event fields and file lines, or `--replay EVENT_ID` to verify a trigger's rule evidence, model inputs, score and candidate mappings. Run `python -m attack_catalog` to refresh the two official MITRE ATT&CK STIX records for online or offline use.

The [worked investigation](EVIDENCE-CASE.md) follows two triggers for the same account through the original login records and documents the association criteria and the remaining uncertainty.

## Request an analyst briefing

Start the local Ollama service with the model listed above, then run either command from the project directory with the ML dependencies installed.

```powershell
python -m casebook runs/dataset-v1-seed-42 --case case-e-51d9170e7544d3e64f6f727a --explain
python -m casebook runs/dataset-v1-seed-42 --case case-e-51d9170e7544d3e64f6f727a --explain baseline
```

The first command asks Llama to prioritize evidence and choose a follow-up. The second uses a reproducible template offline. Both return facts with event IDs, ATT&CK hypotheses with alternatives, missing information and recommended checks. The full evidence case accompanies the briefing. An unavailable model or an invalid answer leaves the case in the JSON output, marks the explanation unavailable and returns exit code 2.

The [local Llama run](LLAMA-REVIEW.md) records the runtime, sample selection and a worked answer from the GPU.
