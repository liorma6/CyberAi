# Local GPU smoke test

On 19 November 2026 the CLI processed five synthetic log records and returned two validated reviews from a local Llama instance. One case required all four source IDs to support the observation. The overnight case required one.

| Environment | Recorded value |
| --- | --- |
| GPU | NVIDIA GeForce RTX 2070, 8192 MiB, driver 621.14 |
| Runtime | Ollama 0.40.16, llama.cpp, 4096-token context |
| Model | `llama3.1:8b-instruct-q4_K_M` |
| Model digest | `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` |
| Model memory reported in VRAM | 5,280,104,447 bytes (4.92 GiB) |
| Input SHA-256 | `b9e8320507564db75d02d08e977f5e91bc435702492524834f13620f7fe333f8` |

The first integration attempt rejected an incomplete set of citations for the sequence of failures. The adapter now supplies the supporting IDs for each candidate and bounds the output vocabulary and citation count for the case. An independent validator checks exact membership, duplicates and the follow-up before rendering a factual sentence.

Each column below is one invocation of `python -m evidencesoc --explain` with the final adapter. The model was already loaded. Times are wall seconds for the chat request on this workstation.

| Case | Evidence returned in every run | Run 1 | Run 2 | Run 3 | Run 4 |
| --- | --- | ---: | ---: | ---: | ---: |
| Three failures followed by success | E01, E02, E03, E04 | 1.184 | 1.090 | 0.910 | 0.918 |
| Overnight success | E05 | 0.641 | 0.655 | 0.647 | 0.661 |

The first review requested verification with the account owner. The second requested the user's shift and time zone. Both are investigation steps. These fixed examples exercise the integration. Detection accuracy, cold-start latency and a matched CPU comparison remain separate experiments.
