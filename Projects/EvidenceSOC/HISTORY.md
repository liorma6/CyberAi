# EvidenceSOC development history

Work is published to `liorma6/CyberAi` on `feature/evidencesoc`. GitHub's [branch history](https://github.com/liorma6/CyberAi/commits/feature/evidencesoc) lists every published commit, including documentation changes. Each commit page shows its parent, diff and check status.

## Milestones

| Date | Commit | Change | GitHub Actions |
| --- | --- | --- | --- |
| 2026-11-19 | [b3986ea](https://github.com/liorma6/CyberAi/commit/b3986ea2c9166723bb96c8c0ac380b5da3e2a80c) | Created the EvidenceSOC project directory. | Workflow introduced later. |
| 2026-11-19 | [2d12ac1](https://github.com/liorma6/CyberAi/commit/2d12ac13bf50d7037fb254993602d17ea2e884e0) | Stage 0. Linked login alerts to source events and validated local model reviews. | Workflow introduced later. |
| 2026-11-19 | [d63a759](https://github.com/liorma6/CyberAi/commit/d63a7596e8534a7e677addb4215ad20e75e37624) | Added the CI matrix and command-line demo check. | [Passed on Python 3.13 and 3.14](https://github.com/liorma6/CyberAi/actions/runs/44501328412) |
| 2026-11-19 | [ebdd5c4](https://github.com/liorma6/CyberAi/commit/ebdd5c4d6f2c3db7a9fe153107528828dac34505) | Constrained model citations and recorded the local RTX 2070 smoke test. | [Passed on both versions](https://github.com/liorma6/CyberAi/actions/runs/44502563935) |
| 2026-11-19 | [32368e1](https://github.com/liorma6/CyberAi/commit/32368e154c015963b4e8dbf16a9cca7fa88fff46) | Stage 1. Generated reproducible synthetic scenarios and chronological dataset splits. | [Passed on both versions](https://github.com/liorma6/CyberAi/actions/runs/44503994434) |
| 2026-11-19 | [bf2c644](https://github.com/liorma6/CyberAi/commit/bf2c6445774464361a0cd3eee4446cf0456336a7) | Stage 2. Added historical features, four detection rules and a reproducible [calibration report](RULE-BASELINE.md). | [Passed on both versions](https://github.com/liorma6/CyberAi/actions/runs/44505418141) |

## Stage 3

| Date | Commit | Change | Verification |
| --- | --- | --- | --- |
| 2026-11-19 | [b28a6a5](https://github.com/liorma6/CyberAi/commit/b28a6a569d7994a7410434a6ebb7de790640525f) | Trained Isolation Forest, froze the calibration threshold and published the [held-out comparison](MODEL-COMPARISON.md). | All 18 tests passed locally. The [existing CI workflow](https://github.com/liorma6/CyberAi/actions/runs/44508878099) also passed. |
| 2026-11-19 | [f3fd46a](https://github.com/liorma6/CyberAi/commit/f3fd46acdd90732f43a6371f0c2797d3eda21717) | Installed the pinned model dependencies in CI so both Python versions exercise the forest and reproduce the published report. | [Passed on Python 3.13 and 3.14](https://github.com/liorma6/CyberAi/actions/runs/44508935352) |

[Stage 3 pull request and checks](https://github.com/liorma6/CyberAi/pull/2)

## Stage 4

| Date | Commit | Change | Verification |
| --- | --- | --- | --- |
| 2026-11-19 | [96fb5ac](https://github.com/liorma6/CyberAi/commit/96fb5acb5b6d506ff09f651933ec7f14c40817ae) | Correlated rule and model triggers, retained original login lines and replayed each finding. Added conditional ATT&CK candidates and a versioned STIX cache. | [22 tests on both Python versions](https://github.com/liorma6/CyberAi/actions/runs/44510922690) |
| 2026-11-19 | [4414d71](https://github.com/liorma6/CyberAi/commit/4414d711f02bff999628b822dc5b81b206830b70) | Added a live check of the official MITRE STIX refresh on Python 3.13. | [Live refresh and regression tests passed](https://github.com/liorma6/CyberAi/actions/runs/44510991335) |

The [worked investigation](EVIDENCE-CASE.md) lists the five source log lines for a two-trigger case. [Stage 4 pull request and checks](https://github.com/liorma6/CyberAi/pull/3)

## Stage 5

| Date | Commit | Change | Verification |
| --- | --- | --- | --- |
| 2026-11-19 | [a77065e](https://github.com/liorma6/CyberAi/commit/a77065e21bf34c7d8445fd315269a2fafe885384) | Added evidence-linked Llama briefings and a deterministic comparison to the casebook. | 27 tests passed locally. [CI passed on Python 3.13 and 3.14](https://github.com/liorma6/CyberAi/actions/runs/44513035755). |

A local RTX 2070 produced valid briefings for all 15 distinct review menus in the 192-case synthetic test set. The [run report](LLAMA-REVIEW.md) includes the selection method, timings and a worked investigation. [Stage 5 pull request and checks](https://github.com/liorma6/CyberAi/pull/4)

## Stage 6

| Date | Commit | Change | Verification |
| --- | --- | --- | --- |
| 2026-11-19 | [227903c](https://github.com/liorma6/CyberAi/commit/227903c5a15fadfb25420ae0956f71c923eb3ea2) | Connected the EvidenceSOC queue, raw source inspector, case briefings and analyst assessments to the local casebook. | 29 tests passed locally. [CI passed on Python 3.13 and 3.14](https://github.com/liorma6/CyberAi/actions/runs/44515984660). |

The seed-42 desk listed 192 cases and 261 triggers. In file 011, the browser opened lines 92 and 96 of the test stream, obtained a live local Llama briefing, filed a cited assessment and restored it after refresh. The filed filter isolated the case, and reopening allowed revision. Narrow-screen navigation was checked at a 390-pixel viewport. See the [launch instructions](README.md#open-evidencesoc) and [stage 6 pull request](https://github.com/liorma6/CyberAi/pull/5).

## Stage 7

| Date | Commit | Change | Verification |
| --- | --- | --- | --- |
| 2026-11-19 | [59e2476](https://github.com/liorma6/CyberAi/commit/59e2476d4f4e51ca3c51055cab1c9a0bc7b1c485) | Published detector, paired briefing and matched hardware experiments. Added verified dataset import and documented the browser restart test. | 32 tests passed locally. [CI reproduced the detector results on Python 3.13 and 3.14](https://github.com/liorma6/CyberAi/actions/runs/44518561571). |

The [experiment report](EXPERIMENTS.md) links the raw results, figure and two independent rating packets. Human ratings and an independent teammate rerun await sign-off. [Stage 7 pull request](https://github.com/liorma6/CyberAi/pull/6)

## Publishing and verification

Publish each local commit to the feature branch with `git push origin feature/evidencesoc`. A commit made directly on GitHub is already published. In that case synchronize the local feature branch with `git pull --ff-only origin feature/evidencesoc`. Compare the local and remote revisions after publication using the commands below from the feature branch.

```bash
git fetch origin
git rev-list --left-right --count HEAD...origin/feature/evidencesoc
```

Two zeroes mean both sides contain exactly the same commits. Open the [branch workflow runs](https://github.com/liorma6/CyberAi/actions/workflows/evidencesoc.yml?query=branch%3Afeature%2Fevidencesoc) to verify the checks for the exact commit. When adding a milestone to the table, include its commit and workflow run. The [history of this file](https://github.com/liorma6/CyberAi/commits/feature/evidencesoc/Projects/EvidenceSOC/HISTORY.md) records publication and subsequent changes to the log itself.
