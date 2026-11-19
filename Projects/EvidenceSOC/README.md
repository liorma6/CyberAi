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

The next milestone adds reproducible labeled scenarios and chronological train, calibration and test periods. The ATT&CK sync, Isolation Forest comparison and analyst interface are planned independently of this smoke test.
