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

## Publishing and verification

Stage 3 trained Isolation Forest on the earlier benign period and froze its threshold before scoring the held-out period. The [comparison report](MODEL-COMPARISON.md) includes false alerts, misses and traceable examples. The [report's commit history](https://github.com/liorma6/CyberAi/commits/feature/evidencesoc/Projects/EvidenceSOC/MODEL-COMPARISON.md) links to the implementation and its checks.

Publish each local commit to the feature branch with `git push origin feature/evidencesoc`. A commit made directly on GitHub is already published. In that case synchronize the local feature branch with `git pull --ff-only origin feature/evidencesoc`. Compare the local and remote revisions after publication using the commands below from the feature branch.

```bash
git fetch origin
git rev-list --left-right --count HEAD...origin/feature/evidencesoc
```

Two zeroes mean both sides contain exactly the same commits. Open the [branch workflow runs](https://github.com/liorma6/CyberAi/actions/workflows/evidencesoc.yml?query=branch%3Afeature%2Fevidencesoc) to verify the checks for the exact commit. When adding a milestone to the table, include its commit and workflow run. The [history of this file](https://github.com/liorma6/CyberAi/commits/feature/evidencesoc/Projects/EvidenceSOC/HISTORY.md) records publication and subsequent changes to the log itself.
