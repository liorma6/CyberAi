# Lab 2b — Reflection: evidence versus intuition

**Profile:** attack_surge (5000 events) vs normal (500 events)
**Run IDs:** attack_surge `4e981da1-06eb-445c-bf22-de1174241f08`, normal `881e71e6-07f1-4f14-9114-73c0ab292fe4`
**Environment check:** `python -m pytest -q` → 14 passed in 0.65 s

## What did the dashboard initially suggest?
The lab guide primes you to expect **orchestrator pressure** in attack_surge, because the orchestrator runs the
"agent" stage (XAI, RAI, Meta-AI) and does more work per alert. The mid-run dashboard (about 19 s in) pointed
elsewhere straight away. Status was **OVERLOADED**, ingress backlog was 2,620 / 500, detector queue wait was 12.6 s,
and the alert backlog was only 2 / 500. Some figures on screen were still misleading:
- **Single samples, not averages.** "Generated events/s 174.0" and "Detector events/s 19.7" are the latest samples,
  not run averages.
- **The snapshot depends on timing.** In an earlier attempt (run `dc6e32cf`), I captured the dashboard only after the
  queues had drained. It showed HIGH LOAD with 0 / 500 backlog, which looks calm for a run that had a 4,300-event
  backlog. That is why I reran the profile and took the screenshot while the backlog was above 425.

## What did the CSV confirm or contradict?
- **Contradicted** the orchestrator-pressure hypothesis. The alert backlog never went above 15 and orchestrator queue
  wait averaged 0.2 s. The **detector** was the stage that could not keep up.
- **Explained the backlog exactly.** Comparing all stages over the same window (0 s to the last generated event at
  31.8 s): the generator produced 157.3 events/s, while the detector and orchestrator completed 20.0 each. That gap
  of about 137 events/s matches the backlog's growth rate (4,363 ÷ 31.8 s). Whole-run rates (28.5 events/s over
  175 s) mix in the drain period and hide this.
- **Added the peak the dashboard cannot show.** Rebuilding the counters over time shows the ingress backlog peaked at
  **4,363 events**, 8.7× the 500-message reference value on the dashboard. That value is `high_load.queue_capacity`
  in `settings.yaml`. Only the dashboard's display and status rule use it; it is not a limit on the Kafka topic.
- **Confirmed** that latency was almost all queue waiting. Mean E2E was 78.3 s, against about 61 ms of real processing.
- **Confirmed** that the backlog drained only after the generator stopped. It fell linearly at 30.3 events/s, so
  32 s of traffic took 175 s to process.
- **Revealed the offered load was below target.** The profile requests 500 events/s, but the generator delivered
  157.3 events/s, about 31.5 % of target. What happens at a real 500 events/s was not measured in this experiment.

The conclusion that relied most on quantitative evidence was **which stage is the bottleneck**. The detector and the
orchestrator have nearly the same processing time (31.1 ms vs 29.6 ms). From the architecture alone, either could
have been the bottleneck. Only the per-queue backlog and queue-wait series separate them.

## What uncertainty remains in the bottleneck diagnosis?
- **The orchestrator is close behind.** Its processing time is only about 5 % shorter than the detector's. With the
  detector scaled out, the orchestrator could become the bottleneck almost immediately. Its saturated rate was never
  measured, because the detector always limited its input.
- **CPU contention, which the CSV measures directly.** Every process (generator, detector, orchestrator, dashboard,
  Redpanda in Docker) ran on one Windows laptop:
  - **While the generator ran (0–31.8 s):** the detector completed 637 events, 20.0 events/s at 43.7 ms per event.
    The mid-run screenshot agrees: 380 detected at about 19 s.
  - **After the generator stopped:** the same detector drained at 30.3 events/s and 29.3 ms per event.
  - **Orchestrator:** it slowed the same way, 36.6 ms vs 28.6 ms per event.

  So the detector lost about a third of its throughput while it competed with the generator. The generator was
  probably limited by the same contention. The diagnosis describes this machine and setup, not a fixed property of
  the design.
- **Utilization is an estimate.** I compute it from processing times, splitting each operation's duration across
  the seconds it spans and averaging over complete seconds only. It counts only the timed stage, not Kafka polling or
  metric writes, so it understates true busy time. It averaged 87.9 % for the detector and was at or above 90 % in
  only 25 of 174 seconds, even though the queue was saturated throughout. It also stayed flat when contention
  changed (86.5 % vs 88.1 %), because longer processing offset the lower throughput.
- **Measurements are not complete.** Every metric is missing about 1 % of its records. For example, there are 4,963
  E2E samples and 4,961 detector-processing samples for 5,000 events. 378 of 74,647 lines (0.5 %) in the internal
  metrics log are unparseable, which fits three processes appending to one file at the same time. The cumulative
  counters still reach 5,000, so this doesn't show that events were lost. Latency means are computed over the
  records available for each metric.
- **The sizing is a first estimate.** The recommendation's figures (about 24 detector instances for 500 events/s)
  assume linear scaling. That fails if Redpanda, the shared fingerprint state, or host CPU becomes the limit first.
- **One run per profile.** There are no repetitions and no confidence intervals.

## What would I change in the architecture, and why?
1. **Partition the telemetry topic and run several detector consumers** in one consumer group, keyed by user/host so
   per-user fingerprints stay consistent. As a first estimate for 500 events/s: about 24 instances to stay under
   70 % utilization at the uncontended 30.3 events/s, or about 36 at the contended 20 events/s. So keep detectors on
   hosts separate from the producers. The orchestrator would need about 15–21 instances, a figure based on its
   processing time, not on a measured saturated rate. Both figures need a test at the higher rate.
2. **Alert on queue wait and backlog growth rate, not utilization.** Queue wait passed 1 s at t = 1.3 s and rose
   steadily. Estimated utilization stayed between 74 % and 91 % in the same period and missed the contention change.
3. **Show peak backlog and peak E2E latency on the dashboard**, not only the current values. A screenshot taken after
   drainage gives a misleadingly healthy picture of an overload event.
4. **Write metrics without corruption.** Use one file per process or a locked writer, so the evidence log doesn't
   lose records under exactly the load it is meant to measure.
5. Possibly add **risk-based prioritisation**, so high-risk events skip ahead in the queue during a surge. The
   trade-off is that low-priority telemetry, which may still carry early signs of an attack, is delayed further.
