# Local Llama case review

On 19 November 2026, 15 of 15 live requests returned validated, cited briefings for the seed-42 test cases. The run used Ollama on the workstation's RTX 2070 and `llama3.1:8b-instruct-q4_K_M` (digest `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`). Ollama reported 5,280,104,447 model bytes in VRAM. With the model already loaded, the median chat request took 0.778 s (range 0.591–1.106 s). These timings exclude dataset loading, detector training and rendering.

## A review an analyst can trace

The [worked case](EVIDENCE-CASE.md) contains two triggers. In the live run Llama prioritized the successful login at line 96 of `events/test.jsonl` and selected two related lines of inquiry.

| Briefing section | Returned evidence or decision |
| --- | --- |
| Facts | The successful login followed four failures for the same account and IP. R1 cites five event IDs, including the successful login. R4 cites that login and the 82 historical successes, none of which fell within the relevant three-hour UTC band. The forest scored the login at 0.636677 against a threshold of 0.621293. |
| Hypotheses | T1110 and T1078 remain candidates for the cited successful login. Password retries and an unusual but legitimate work schedule remain plausible explanations. |
| Missing information | The login stream cannot establish who initiated the attempts or controlled the resulting session. |
| Recommended check | Inspect the identity-provider sign-in and MFA records for the cited time. |

The primary trigger is `e-9fdcf6ea0ac4a07c32742991`. Its detector score can be reproduced from 87 cited events with `--replay`. In the forest-only example below, the briefing describes the observed inputs and score, leaves the hypothesis list empty and asks for further evidence.

## What Llama decides

EvidenceSOC constructs possible lines of inquiry from each case's rule hits, model decision and existing ATT&CK candidates. It keeps the earliest occurrence of each combination of technique, supporting rules, login outcome and model decision. The prompt contains observations, uncertainty and available checks. The raw account strings, raw log lines, event IDs and simulator labels stay outside the model prompt.

Llama selects a primary lead, an optional additional lead and a verification step. Python validates the selection against that case, checks that the follow-up belongs to the primary lead, then expands each fact into text and exact event IDs. Hypotheses retain their supporting rules and alternative explanations. The original case accompanies every response. The deterministic baseline chooses the lead with the most supporting rules, breaks ties in input order and selects the first allowed check. Output records identify the source as `template` or `ollama`.

## Recorded requests

The synthetic dataset contains 192 cases. Starting with the worked case, then scanning in chronological order, this run selected one case for each distinct menu of candidate techniques, supporting signals and allowed checks, including repeated entries. This exercises output handling across 15 menu profiles. The model and baseline chose different follow-ups in six cases. Analyst usefulness and a matched CPU/GPU comparison are reserved for stage 7.

| Case ID | Llama follow-up | Template follow-up | Chat seconds |
| --- | --- | --- | ---: |
| case-e-51d9170e7544d3e64f6f727a | provider | provider | 1.106 |
| case-e-17f4f88cddfe9121c37b2471 | travel | travel | 0.776 |
| case-e-bc6037889442ae6b5b330f17 | provider | gateway | 0.759 |
| case-e-79fb464e10cff03f69f0517b | provider | owner | 0.778 |
| case-e-47a99b306b57abeceacf6180 | shift | shift | 0.628 |
| case-e-3ee373b4e88859ddc5dd5f8b | provider | provider | 0.740 |
| case-e-16a946ed6cb8fa646acaefa5 | provider | provider | 0.773 |
| case-e-59dd9452694e69c370709b65 | gateway | gateway | 0.802 |
| case-e-51e6361009f7689877ab5595 | provider | provider | 1.015 |
| case-e-61b0d81fb60c498a61d9e4fe | shift | provider | 0.591 |
| case-e-28f8344e21e5eed2a2ee459d | provider | gateway | 0.775 |
| case-e-3ef2c525bad79fa1529954a6 | provider | provider | 0.892 |
| case-e-7b4262f3c7adff652ab9ec20 | provider | provider | 0.939 |
| case-e-200976461f46a4555e3b89ce | provider | shift | 0.843 |
| case-e-84f20b1a7691ec41fe4e1e82 | provider | owner | 0.869 |

## Reproduce

Use the pinned project dependencies, generate seed 42 and start the local model as described in the [README](README.md). Substitute any case ID from the table in these commands.

```powershell
python -m casebook runs/dataset-v1-seed-42 --case case-e-51d9170e7544d3e64f6f727a --explain
python -m casebook runs/dataset-v1-seed-42 --case case-e-51d9170e7544d3e64f6f727a --explain baseline
python -m unittest -v test_case_review
```

The automated tests use a fixed local ATT&CK snapshot and controlled model responses. They check event citations, attribution to a trigger, unsupported checks, malformed output and service failure. The template is also exercised on all 192 cases. GPU timings and the live Llama selections above were collected separately on the workstation.
