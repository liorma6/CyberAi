# EvidenceSOC

EvidenceSOC investigates suspicious authentication activity and records the event IDs behind each observation. This first milestone runs locally with the Python standard library. The demo contains five synthetic events and yields two investigation cases.

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

Both cases retain the source events. The two illustrative rules will serve as a baseline for the later detector comparison. Their thresholds have not been evaluated on a held-out dataset.

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

The [generated dataset profile](DATASET-PROFILE.md) gives the canonical seed's fingerprint, class counts and overlapping patterns. The next milestone implements historical features and rule evaluation before the Isolation Forest comparison.
